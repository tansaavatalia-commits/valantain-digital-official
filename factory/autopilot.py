"""Pilota automatico: vendite -> idee -> produzione -> pubblicazione -> report.

Ogni fase è indipendente: se manca una credenziale la fase viene saltata con un avviso,
le altre proseguono. L'esito finisce in un riepilogo Markdown (Job Summary su GitHub).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .build import build_all
from .config import Config
from .export import export_catalog
from .spec import load_catalog

log = logging.getLogger(__name__)


@dataclass
class Paths:
    catalog: Path = Path("catalog")
    dist: Path = Path("dist")
    state: Path = Path("state")
    reports: Path = Path("reports")


@dataclass
class Outcome:
    lines: list[str] = field(default_factory=list)
    failed: bool = False

    def add(self, text: str) -> None:
        log.info(text)
        self.lines.append(f"- {text}")


def has_claude() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def etsy_from_env(state_dir: Path):
    """Client Etsy da secret + token cifrato in state/ (o ETSY_REFRESH_TOKEN, se impostato)."""
    from .etsy import Etsy
    from .vault import TOKEN_FILE, unseal

    key, secret = os.environ.get("ETSY_KEYSTRING"), os.environ.get("ETSY_SHARED_SECRET")
    if not (key and secret):
        return None
    token = os.environ.get("ETSY_REFRESH_TOKEN") or unseal(state_dir / TOKEN_FILE, secret)
    return Etsy(key, secret, token) if token else None


def run(cfg: Config, paths: Paths, refresh_token_out: Path | None = None) -> Outcome:
    from .vault import TOKEN_FILE, seal

    out = Outcome()
    client = None
    if cfg.etsy.enabled:
        try:
            client = etsy_from_env(paths.state)
        except RuntimeError as exc:
            out.add(f"⚠️ {exc}")
            out.failed = True
    shop_id = None

    # 1. Etsy: rinnovo token (salvato SUBITO: il vecchio potrebbe non valere più) e vendite
    if client:
        from .publish import load_state
        from .report import sales_report

        try:
            new_token = client.refresh()
            # salvato SUBITO, cifrato: il vecchio token potrebbe non valere più
            seal(paths.state / TOKEN_FILE, new_token, os.environ["ETSY_SHARED_SECRET"])
            if refresh_token_out:
                refresh_token_out.write_text(new_token)
            me = client.me()
            shop_id = me["shop_id"]
            report = sales_report(client, shop_id, load_state(paths.state / "etsy.json"),
                                  paths.reports, paths.state / "sales.json")
            out.add(f"Report vendite: `{report}`")
        except Exception as exc:  # noqa: BLE001
            out.add(f"⚠️ Etsy non raggiungibile ({exc}): niente report né pubblicazione")
            out.failed = True
            client = None
    elif cfg.etsy.enabled:
        out.add("Etsy non ancora collegato: esegui il workflow «Collega Etsy»")

    # 2. Nuove idee
    if cfg.ideas.enabled and cfg.ideas.lines_per_run:
        auto = list((paths.catalog / "auto").glob("*.yaml"))
        if len(auto) >= cfg.ideas.max_auto_lines:
            out.add(f"Idee: raggiunto il tetto di {cfg.ideas.max_auto_lines} linee automatiche")
        elif not has_claude():
            out.add("Idee: manca ANTHROPIC_API_KEY, nessuna nuova linea")
        else:
            from .ideas import generate_ideas

            try:
                new = generate_ideas(cfg.ideas.lines_per_run, paths.catalog, paths.state / "sales.json")
                out.add("Nuove linee: " + (", ".join(f"`{p.stem}`" for p in new) or "nessuna valida"))
            except Exception as exc:  # noqa: BLE001
                out.add(f"⚠️ Generazione idee fallita: {exc}")

    # 3. Produzione
    engine = cfg.copy_engine if has_claude() else "template"
    results = build_all(load_catalog([paths.catalog]), paths.dist, copy_engine=engine)
    export_catalog(paths.dist)
    built = sum(r.status == "built" for r in results)
    bad = [r for r in results if r.status == "failed"]
    out.add(f"Produzione: {built} prodotti nuovi o aggiornati, {len(results)} in totale, {len(bad)} con errori")
    for r in bad:
        out.add(f"⚠️ `{r.sku}`: {'; '.join(r.errors)}")
    out.failed |= bool(bad)

    # 4. Pubblicazione
    if client and shop_id:
        from .publish import publish

        try:
            shop = client.shop(shop_id)
            taxonomy = client.taxonomy_id(cfg.etsy.taxonomy_name)
            rep = publish(paths.dist, client, cfg.etsy, paths.state / "etsy.json",
                          shop_id=shop_id, currency=shop.get("currency_code", "EUR"), taxonomy_id=taxonomy)
            verb = "pubblicate" if cfg.etsy.mode == "active" else "create come bozze"
            out.add(f"Etsy: {len(rep.published)} inserzioni {verb}, {len(rep.resumed)} completate, "
                    f"{rep.pending} in coda per le prossime esecuzioni")
            for url in rep.published:
                out.add(f"  {url}")
            for k, e in rep.failed.items():
                out.add(f"⚠️ `{k}`: {e}")
            out.failed |= bool(rep.failed)
        except Exception as exc:  # noqa: BLE001
            out.add(f"⚠️ Pubblicazione interrotta: {exc}")
            out.failed = True
    return out

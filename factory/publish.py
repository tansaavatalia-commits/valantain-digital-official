"""Pubblicazione su Etsy dei prodotti costruiti in dist/.

Un'inserzione Etsy = una linea in un tema. Dentro ci sono i file di tutte le lingue
(fino a 5) e le traduzioni di titolo, descrizione e tag.

Lo stato vive in `state/etsy.json` (versionato nel repository): ogni passaggio completato
viene salvato subito, così un'esecuzione interrotta riprende senza creare doppioni.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import EtsyConfig
from .etsy import Etsy, EtsyError, clean_tag, clean_title
from .export import load_manifests

log = logging.getLogger(__name__)

LANG_NAMES = {"it": "Italiano", "en": "English", "es": "Español"}
INCLUDED = {
    "en": "Included languages", "it": "Lingue incluse", "es": "Idiomas incluidos",
}
STEPS = ["created", "images", "files", "translations", "done"]


@dataclass
class Group:
    key: str
    manifests: dict[str, dict]  # lang -> manifest

    def primary(self, lang: str) -> tuple[str, dict]:
        if lang in self.manifests:
            return lang, self.manifests[lang]
        first = min(self.manifests)
        return first, self.manifests[first]

    @property
    def ok(self) -> bool:
        return all(not m["qa_errors"] for m in self.manifests.values())


@dataclass
class PublishReport:
    published: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    pending: int = 0


def group_manifests(dist: Path) -> list[Group]:
    groups: dict[str, dict[str, dict]] = {}
    for m in load_manifests(dist):
        key = m["sku"].removesuffix(f"-{m['lang']}")
        groups.setdefault(key, {})[m["lang"]] = m
    return [Group(k, v) for k, v in sorted(groups.items())]


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def listing_text(m: dict, langs: list[str], lang: str) -> tuple[str, str, list[str]]:
    names = ", ".join(LANG_NAMES.get(x, x) for x in langs)
    desc = m["description"]
    if len(langs) > 1:
        desc += f"\n\n{INCLUDED.get(lang, INCLUDED['en'])}: {names}."
    tags = []
    for t in m["tags"]:
        t = clean_tag(t)
        if t and t not in tags:
            tags.append(t)
    return clean_title(m["title"])[:140], desc, tags[:13]


def publish(dist: Path, client: Etsy, cfg: EtsyConfig, state_path: Path,
            *, shop_id: int, currency: str, taxonomy_id: int) -> PublishReport:
    state = load_state(state_path)
    report = PublishReport()
    groups = [g for g in group_manifests(dist) if g.ok]
    new_budget = cfg.max_new_listings_per_run

    for g in groups:
        entry = state.get(g.key)
        if entry and entry.get("step") == "done":
            continue
        if entry is None:
            if new_budget <= 0:
                report.pending += 1
                continue
            new_budget -= 1
        try:
            resumed = entry is not None
            entry = _publish_group(dist, g, client, cfg, shop_id, currency, taxonomy_id, entry or {},
                                   lambda e, k=g.key: (state.__setitem__(k, e), save_state(state_path, state)))
            (report.resumed if resumed else report.published).append(entry.get("url") or g.key)
        except EtsyError as exc:
            log.error("pubblicazione fallita per %s: %s", g.key, exc)
            report.failed[g.key] = str(exc)
            if exc.status in (401, 403):  # credenziali o permessi: inutile proseguire
                break
    return report


def _publish_group(dist: Path, g: Group, client: Etsy, cfg: EtsyConfig, shop_id: int, currency: str,
                   taxonomy_id: int, entry: dict, persist) -> dict:
    langs = sorted(g.manifests)
    lang, m = g.primary(cfg.language)
    title, desc, tags = listing_text(m, langs, lang)
    step = entry.get("step")

    def done(s: str, **extra) -> None:
        entry.update(step=s, **extra)
        persist(entry)

    if step is None:
        price = m["price"].get("usd") if currency == "USD" and m["price"].get("usd") else m["price"]["eur"]
        if currency not in ("EUR", "USD"):
            log.warning("valuta del negozio %s: uso il prezzo in EUR (%s) come numero", currency, price)
        listing = client.create_draft(shop_id, {
            "quantity": cfg.quantity, "title": title, "description": desc, "price": price,
            "who_made": "i_did", "when_made": "made_to_order", "taxonomy_id": taxonomy_id,
            "type": "download", "tags": tags, "is_supply": "false", "should_auto_renew": "true",
        })
        done("created", listing_id=listing["listing_id"], url=listing.get("url", ""),
             langs=langs, primary=lang)
        step = "created"

    lid = entry["listing_id"]
    if STEPS.index(step) < STEPS.index("images"):
        for rank, img in enumerate(m["images"][:10], start=1):
            client.upload_image(shop_id, lid, dist / img, rank, f"{title} - {rank}")
        done("images")

    if STEPS.index(entry["step"]) < STEPS.index("files"):
        files = [f for x in langs for f in g.manifests[x]["files"]]
        if len(files) > 5:
            log.warning("%s: %d file, Etsy ne accetta 5: carico solo la lingua %s", g.key, len(files), lang)
            files = m["files"][:5]
        for rank, f in enumerate(files, start=1):
            client.upload_file(shop_id, lid, dist / f, rank)
        done("files")

    if STEPS.index(entry["step"]) < STEPS.index("translations"):
        for other in langs:
            if other == lang:
                continue
            t, d, tg = listing_text(g.manifests[other], langs, other)
            try:
                client.translate(shop_id, lid, other, t, d, tg)
            except EtsyError as exc:  # una traduzione rifiutata non blocca la vendita
                log.warning("traduzione %s non accettata per %s: %s", other, g.key, exc)
        done("translations")

    if cfg.mode == "active":
        client.update(shop_id, lid, {"state": "active"})
    done("done", mode=cfg.mode)
    return entry

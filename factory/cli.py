"""Riga di comando: `python -m factory <comando>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .spec import load_catalog


def cmd_validate(args: argparse.Namespace) -> int:
    specs = load_catalog(args.catalog)
    total = 0
    for s in specs:
        n = len(s.variants())
        total += n
        print(f"OK  {s.line:<20} {len(s.themes)} temi x {len(s.langs)} lingue = {n} prodotti, "
              f"formati {', '.join(s.sizes)}")
    print(f"\nCatalogo valido: {len(specs)} linee, {total} prodotti.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for s in load_catalog(args.catalog):
        for v in s.variants():
            print(v.sku)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build_all
    from .export import export_catalog

    specs = load_catalog(args.catalog)
    dist = Path(args.out)
    results = build_all(specs, dist, copy_engine=args.copy, force=args.force,
                        only=args.only, workers=args.workers)
    files = export_catalog(dist)
    counts = {k: sum(r.status == k for r in results) for k in ("built", "skipped", "failed")}
    print(f"\nCostruiti {counts['built']}, invariati {counts['skipped']}, falliti {counts['failed']}.")
    for r in results:
        for e in r.errors:
            print(f"  ERRORE {r.sku}: {e}")
    print("Esportati: " + ", ".join(str(f) for f in files))
    return 1 if counts["failed"] else 0


def cmd_preview(args: argparse.Namespace) -> int:
    """Scrive l'HTML di una variante: si apre nel browser per ritoccare il design al volo."""
    from .render import render_html

    for s in load_catalog(args.catalog):
        for v in s.variants():
            if v.sku == args.sku:
                out = Path(args.out) / f"{v.sku}-{args.size}.html"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(render_html(v, args.size), encoding="utf-8")
                print(out)
                return 0
    print(f"SKU non trovato: {args.sku}", file=sys.stderr)
    return 2


def cmd_etsy_start(args: argparse.Namespace) -> int:
    """Passo 1 del collegamento: crea il link di autorizzazione e il verificatore PKCE."""
    import json
    import os
    import secrets

    from .etsy import authorize_url, make_pkce

    verifier, challenge = make_pkce()
    url = authorize_url(os.environ["ETSY_KEYSTRING"], args.redirect_uri, challenge,
                        secrets.token_urlsafe(16))
    Path(args.out).write_text(json.dumps({"verifier": verifier, "url": url}))
    print(url)
    return 0


def cmd_etsy_finish(args: argparse.Namespace) -> int:
    """Passo 2: scambia il codice ricevuto da Etsy con un refresh token."""
    import os

    from .etsy import Etsy, code_from_redirect, exchange_code

    tokens = exchange_code(os.environ["ETSY_KEYSTRING"], args.redirect_uri,
                           code_from_redirect(args.response), os.environ["ETSY_PKCE_VERIFIER"])
    Path(args.out).write_text(tokens["refresh_token"])
    client = Etsy(os.environ["ETSY_KEYSTRING"], os.environ["ETSY_SHARED_SECRET"], tokens["refresh_token"])
    client.access_token = tokens["access_token"]
    me = client.me()
    shop = client.shop(me["shop_id"])
    print(f"Collegato al negozio «{shop.get('shop_name')}» (id {me['shop_id']}, valuta "
          f"{shop.get('currency_code')}). Permessi: {tokens.get('scope')}")
    return 0


def cmd_autopilot(args: argparse.Namespace) -> int:
    from .autopilot import Paths, run
    from .config import load_config

    out = run(load_config(args.config), Paths(dist=Path(args.out)),
              Path(args.refresh_token_out) if args.refresh_token_out else None)
    text = "## Pilota automatico\n\n" + "\n".join(out.lines) + "\n"
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if out.failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory", description="Fabbrica di prodotti digitali stampabili")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_catalog(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("catalog", nargs="*", default=["catalog"],
                        help="file YAML o cartelle (predefinito: catalog/)")
        return sp

    with_catalog(sub.add_parser("validate", help="controlla le specifiche")).set_defaults(fn=cmd_validate)
    with_catalog(sub.add_parser("list", help="elenca gli SKU")).set_defaults(fn=cmd_list)

    b = with_catalog(sub.add_parser("build", help="genera PDF, mockup, testi e ZIP"))
    b.add_argument("--out", default="dist")
    b.add_argument("--copy", choices=["template", "claude"], default="template",
                   help="motore per i testi delle inserzioni")
    b.add_argument("--only", help="costruisci solo gli SKU che contengono questo testo")
    b.add_argument("--force", action="store_true", help="ricostruisci anche se invariato")
    b.add_argument("--workers", type=int, default=None, help="processi in parallelo")
    b.set_defaults(fn=cmd_build)

    pv = with_catalog(sub.add_parser("preview", help="esporta l'HTML di una variante"))
    pv.add_argument("--sku", required=True)
    pv.add_argument("--size", default="A4")
    pv.add_argument("--out", default="dist/preview")
    pv.set_defaults(fn=cmd_preview)

    es = sub.add_parser("etsy-start", help="collegamento Etsy, passo 1: link di autorizzazione")
    es.add_argument("--redirect-uri", required=True)
    es.add_argument("--out", required=True, help="file JSON con verificatore e link")
    es.set_defaults(fn=cmd_etsy_start)

    ef = sub.add_parser("etsy-finish", help="collegamento Etsy, passo 2: ottieni il refresh token")
    ef.add_argument("--redirect-uri", required=True)
    ef.add_argument("--response", required=True, help="URL completo su cui Etsy ti ha rimandato")
    ef.add_argument("--out", required=True, help="file in cui scrivere il refresh token")
    ef.set_defaults(fn=cmd_etsy_finish)

    ap = sub.add_parser("autopilot", help="vendite, idee, produzione e pubblicazione in un colpo")
    ap.add_argument("--config", default="autopilot.yaml")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--refresh-token-out", help="dove salvare il nuovo refresh token Etsy")
    ap.add_argument("--summary", help="file Markdown a cui aggiungere il riepilogo")
    ap.set_defaults(fn=cmd_autopilot)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

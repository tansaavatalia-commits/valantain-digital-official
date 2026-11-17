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

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

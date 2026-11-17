"""Rendering HTML -> PDF con Jinja2 + WeasyPrint."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .i18n import labels
from .pages import expand_pages
from .spec import Variant
from .themes import THEMES

PKG = Path(__file__).parent
FONTS = (PKG / "assets" / "fonts").resolve().as_uri()
BRAND = "Valantain Digital"

# larghezza x altezza in mm, margine, corpo del testo
PAPER = {
    "A4": (210.0, 297.0, 12.0, 9.5),
    "Letter": (215.9, 279.4, 12.0, 9.5),
    "A5": (148.0, 210.0, 9.0, 7.5),
}


def geometry(size: str) -> dict:
    w, h, m, fs = PAPER[size]
    cw, ch = w - 2 * m, h - 2 * m
    hd = 13.0 if size != "A5" else 10.0
    usable = ch - hd - 10  # sotto l'intestazione, meno il piè di pagina
    row = 7.0 if size != "A5" else 5.6
    day_h = (ch - hd - 6 - 9) / 4
    return {
        "w": w, "h": h, "m": m, "cw": cw, "ch": ch, "hd": hd, "fs": fs, "row": row,
        "day_lines": max(2, int((day_h - 10) / 6.2)),
        "note_lines": int((ch - hd - 8) / 7.5),
        "habit_rows": int((usable - 8) / row),
        "check_rows": int((usable - 2) / (row + 1.5)),
        "budget_rows": max(6, int((usable - 100) / row)),
        "goal_steps": 3 if size != "A5" else 2,
        "todo_rows": 7 if size != "A5" else 4,
    }


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(PKG / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(variant: Variant, size: str) -> str:
    pages = expand_pages(variant)
    index = next((p for p in pages if p["type"] == "index"), None)
    return _env().get_template("document.html.j2").render(
        pages=pages,
        lab=labels(variant.lang, variant.spec.week_start),
        lang=variant.lang,
        name=variant.name,
        t=THEMES[variant.theme],
        g=geometry(size),
        fonts=FONTS,
        brand=BRAND,
        year=variant.spec.year,
        has_index=index is not None,
        index_id=index["id"] if index else "",
    )


def render_pdf(variant: Variant, size: str, out: Path) -> Path:
    from weasyprint import HTML  # import lento: solo quando serve

    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=render_html(variant, size), base_url=str(PKG)).write_pdf(out)
    return out

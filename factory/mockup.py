"""Immagini di presentazione per le inserzioni (4:3, 2400x1800 px, come consigliato da Etsy)."""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .i18n import SHOP
from .render import PKG
from .spec import Variant
from .themes import THEMES

W, H = 2400, 1800
FONT_DIR = PKG / "assets" / "fonts"


def _font(name: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / f"{name}-Variable.ttf"), size)
    try:
        axes = f.get_variation_axes()
        values = []
        for a in axes:
            tag = a.get("name", b"")
            tag = tag.decode() if isinstance(tag, bytes) else str(tag)
            if "eight" in tag:  # "Weight"
                values.append(weight)
            elif "ptical" in tag:  # "Optical size": il massimo è il taglio per titoli
                values.append(a["maximum"])
            else:
                values.append(a["default"])
        f.set_variation_by_axes(values)
    except (OSError, ValueError, KeyError):
        pass  # font statico: si usa così com'è
    return f


def _pages(pdf: Path, indexes: list[int], height: int) -> list[Image.Image]:
    doc = pdfium.PdfDocument(str(pdf))
    out = []
    for i in indexes:
        page = doc[min(i, len(doc) - 1)]
        scale = height / page.get_height()
        out.append(page.render(scale=scale).to_pil().convert("RGB"))
    doc.close()
    return out


def _shadowed(canvas: Image.Image, img: Image.Image, xy: tuple[int, int], angle: float = 0) -> None:
    img = img.convert("RGBA")
    if angle:
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
    pad = 60
    shadow = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    mask = img.split()[3].point(lambda a: 70 if a else 0)
    shadow.paste((40, 30, 30, 255), (pad, pad + 18), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    canvas.alpha_composite(shadow, (xy[0] - pad, xy[1] - pad))
    canvas.alpha_composite(img, xy)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _pick(pages: list[dict], *types: str) -> list[int]:
    """Indici della prima pagina di ciascun tipo richiesto (se presente)."""
    idx = []
    for t in types:
        i = next((n for n, p in enumerate(pages) if p["type"] == t), None)
        if i is not None:
            idx.append(i)
    return idx


def make_mockups(variant: Variant, pdf: Path, pages: list[dict], out_dir: Path,
                 sizes: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = THEMES[variant.theme]
    shop = SHOP[variant.lang]
    bg, ink, accent = _hex(t["backdrop"]), _hex(t["ink"]), _hex(t["accent"])
    written: list[Path] = []

    def save(img: Image.Image, n: int, slug: str) -> None:
        p = out_dir / f"{n:02d}-{slug}.jpg"
        img.convert("RGB").save(p, quality=90, optimize=True)
        written.append(p)

    # 1. Copertina: tre pagine a ventaglio + titolo
    hero = _pick(pages, "cover", "weekly", "monthly") or [0]
    imgs = _pages(pdf, hero, 1250)
    c = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(c)
    positions = [(1150, 330, 7), (1500, 300, -4), (1820, 360, -11)][: len(imgs)]
    for img, (x, y, a) in reversed(list(zip(imgs, positions))):
        _shadowed(c, img, (x - img.width // 2, y), a)
    d.text((130, 470), variant.name, font=_font("Fraunces", 150, 500), fill=ink)
    if variant.subtitle:
        d.text((135, 660), variant.subtitle, font=_font("Inter", 54), fill=ink)
    y = 820
    for line in (f"{len(pages)} {shop['pages']}", " · ".join(sizes), shop["download"]):
        d.rounded_rectangle((130, y, 130 + 560, y + 96), 48, fill=accent)
        d.text((410, y + 48), line, font=_font("Inter", 42, 600), fill="white", anchor="mm")
        y += 130
    save(c, 1, "copertina")

    # 2. Cosa c'è dentro: griglia di miniature
    inside = _pick(pages, "index", "year", "monthly", "weekly", "habit", "goals",
                   "budget", "daily", "checklist", "notes")[:6]
    if inside:
        thumbs = _pages(pdf, inside, 690)
        c = Image.new("RGBA", (W, H), bg + (255,))
        d = ImageDraw.Draw(c)
        d.text((W // 2, 120), shop["inside"], font=_font("Fraunces", 110, 500), fill=ink, anchor="mm")
        cols = 3
        cw = W // cols
        for k, img in enumerate(thumbs):
            x = (k % cols) * cw + (cw - img.width) // 2
            y = 250 + (k // cols) * 770
            _shadowed(c, img, (x, y))
        save(c, 2, "contenuto")

    # 3-5. Primi piani delle pagine principali
    for n, i in enumerate(_pick(pages, "weekly", "monthly", "habit"), start=3):
        (img,) = _pages(pdf, [i], 1600)
        c = Image.new("RGBA", (W, H), bg + (255,))
        d = ImageDraw.Draw(c)
        _shadowed(c, img, (W - img.width - 240, 100))
        d.text((150, 700), pages[i]["title"], font=_font("Fraunces", 120, 500), fill=ink)
        d.text((155, 870), shop["printable"], font=_font("Inter", 56), fill=accent)
        save(c, n, pages[i]["type"])

    # 6. Formati e caratteristiche
    c = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(c)
    d.text((W // 2, 260), shop["sizes"], font=_font("Fraunces", 120, 500), fill=ink, anchor="mm")
    box_w = 520
    x0 = (W - len(sizes) * box_w - (len(sizes) - 1) * 80) // 2
    for k, s in enumerate(sizes):
        x = x0 + k * (box_w + 80)
        d.rounded_rectangle((x, 520, x + box_w, 1140), 40, fill="white", outline=accent, width=8)
        d.text((x + box_w // 2, 830), s, font=_font("Fraunces", 130, 500), fill=accent, anchor="mm")
    if variant.spec.has_links:
        d.text((W // 2, 1350), shop["linked"], font=_font("Inter", 60, 500), fill=ink, anchor="mm")
    d.text((W // 2, 1470), shop["download"] + " · PDF", font=_font("Inter", 52), fill=ink, anchor="mm")
    save(c, 6, "formati")
    return written

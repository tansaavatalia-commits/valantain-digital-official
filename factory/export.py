"""Esporta il catalogo costruito in CSV per caricamento e contabilità."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def load_manifests(dist: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(dist.glob("*/*/manifest.json"))]


def export_catalog(dist: Path) -> list[Path]:
    rows = load_manifests(dist)
    written = []

    # Catalogo completo: una riga per prodotto, utile anche come foglio di controllo.
    cat = dist / "catalog.csv"
    with cat.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "line", "theme", "lang", "pages", "price_eur", "price_usd",
                    "title", "tags", "files", "images", "qa_errors"])
        for m in rows:
            w.writerow([m["sku"], m["line"], m["theme"], m["lang"], m["pages"],
                        m["price"]["eur"], m["price"].get("usd") or "", m["title"],
                        ", ".join(m["tags"]), " ".join(m["files"]), " ".join(m["images"]),
                        "; ".join(m["qa_errors"])])
    written.append(cat)

    # Gumroad / Payhip: non hanno un import CSV ufficiale, questo file serve da
    # scheda di caricamento (nome, prezzo, descrizione, file da allegare).
    gp = dist / "gumroad-payhip.csv"
    with gp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "price_eur", "price_usd", "summary", "description", "file", "cover_image"])
        for m in rows:
            w.writerow([m["title"], m["price"]["eur"], m["price"].get("usd") or "",
                        m["description"].split("\n", 1)[0], m["description"],
                        m["files"][0] if m["files"] else "", m["images"][0] if m["images"] else ""])
    written.append(gp)
    return written

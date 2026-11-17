"""Specifiche di catalogo: un file YAML descrive una *linea* di prodotti.

Una linea si espande in tante *varianti* (tema x lingua). Ogni variante è
un prodotto in vendita (un'inserzione Etsy / un prodotto Gumroad) e contiene
un PDF per ogni formato carta richiesto.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .i18n import LANGS
from .themes import THEMES

PageType = Literal[
    "cover", "index", "year", "monthly", "weekly", "daily",
    "habit", "budget", "checklist", "goals", "notes",
]

SIZES = {
    "A4": ("210mm", "297mm"),
    "Letter": ("8.5in", "11in"),
    "A5": ("148mm", "210mm"),
}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PageSpec(BaseModel):
    type: PageType
    repeat: int = Field(1, ge=1, le=400)
    options: dict = Field(default_factory=dict)


class Price(BaseModel):
    eur: float = Field(gt=0)
    usd: float | None = Field(default=None, gt=0)


class EtsyOptions(BaseModel):
    taxonomy_id: int | None = None
    who_made: Literal["i_did", "someone_else", "collective"] = "i_did"
    when_made: str = "made_to_order"
    shop_section_id: int | None = None


class LineSpec(BaseModel):
    line: str
    category: str
    name: dict[str, str]
    subtitle: dict[str, str] = Field(default_factory=dict)
    audience: dict[str, str] = Field(default_factory=dict)
    keywords: dict[str, list[str]] = Field(default_factory=dict)
    year: int | None = None
    week_start: Literal["monday", "sunday"] = "monday"
    pages: list[PageSpec]
    themes: list[str]
    langs: list[str]
    sizes: list[str] = Field(default_factory=lambda: ["A4", "Letter"])
    price: Price
    etsy: EtsyOptions = Field(default_factory=EtsyOptions)

    @field_validator("line")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(f"'line' deve essere uno slug minuscolo con trattini, non {v!r}")
        return v

    @field_validator("themes")
    @classmethod
    def _themes(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in THEMES]
        if unknown:
            raise ValueError(f"temi sconosciuti {unknown}; disponibili: {sorted(THEMES)}")
        return v

    @field_validator("langs")
    @classmethod
    def _langs(cls, v: list[str]) -> list[str]:
        unknown = [lang for lang in v if lang not in LANGS]
        if unknown:
            raise ValueError(f"lingue sconosciute {unknown}; disponibili: {sorted(LANGS)}")
        return v

    @field_validator("sizes")
    @classmethod
    def _sizes(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in SIZES]
        if unknown:
            raise ValueError(f"formati sconosciuti {unknown}; disponibili: {sorted(SIZES)}")
        return v

    @model_validator(mode="after")
    def _per_lang_texts(self) -> LineSpec:
        missing = [lang for lang in self.langs if lang not in self.name]
        if missing:
            raise ValueError(f"manca 'name' per le lingue {missing}")
        return self

    @property
    def has_links(self) -> bool:
        """Con una pagina indice il PDF ha link interni (utile su GoodNotes / Notability)."""
        return any(p.type == "index" for p in self.pages)

    def variants(self) -> list[Variant]:
        return [Variant(spec=self, theme=t, lang=lang)
                for t, lang in itertools.product(self.themes, self.langs)]

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()[:16]


class Variant(BaseModel):
    spec: LineSpec
    theme: str
    lang: str

    @property
    def sku(self) -> str:
        year = f"-{self.spec.year}" if self.spec.year else ""
        return f"{self.spec.line}{year}-{self.theme}-{self.lang}"

    @property
    def name(self) -> str:
        return self.spec.name[self.lang]

    @property
    def subtitle(self) -> str:
        return self.spec.subtitle.get(self.lang, "")

    @property
    def keywords(self) -> list[str]:
        return self.spec.keywords.get(self.lang, [])


def load_spec(path: str | Path) -> LineSpec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return LineSpec.model_validate(data)


def load_catalog(paths: list[str | Path]) -> list[LineSpec]:
    files: list[Path] = []
    for p in map(Path, paths):
        files.extend(sorted(p.glob("*.y*ml")) if p.is_dir() else [p])
    specs = [load_spec(f) for f in files]
    seen: set[str] = set()
    for s in specs:
        if s.line in seen:
            raise ValueError(f"linea duplicata nel catalogo: {s.line}")
        seen.add(s.line)
    return specs

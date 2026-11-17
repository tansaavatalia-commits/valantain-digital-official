"""Nuove linee di prodotto inventate da Claude, guidate dalle vendite reali.

Claude riceve: il catalogo esistente, le vendite per linea/tema/lingua, la data di oggi.
Restituisce specifiche strutturate che vengono convalidate con lo stesso schema dei YAML
scritti a mano e salvate in `catalog/auto/`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .spec import LineSpec, load_catalog
from .themes import THEMES

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
AUTO_DIR = Path("catalog/auto")
LANGS = ["it", "en", "es"]

ThemeName = Literal["minimal", "sage", "blush", "ocean", "terracotta", "lavender"]
assert set(ThemeName.__args__) == set(THEMES), "aggiorna ThemeName quando aggiungi un tema"


class Localized(BaseModel):
    it: str
    en: str
    es: str


class LocalizedKeywords(BaseModel):
    it: list[str]
    en: list[str]
    es: list[str]


class PageIdea(BaseModel):
    type: Literal["year", "monthly", "weekly", "daily", "habit", "budget", "checklist", "goals", "notes"]
    repeat: int = Field(description="numero di copie della pagina (ignorato per monthly/weekly se c'è l'anno)")
    notes_style: Literal["lines", "dots", "squares"] | None = Field(
        default=None, description="solo per type=notes")
    title: Localized | None = Field(
        default=None, description="titolo personalizzato della pagina (es. 'Lista della spesa' su una checklist)")
    budget_categories: LocalizedKeywords | None = Field(
        default=None, description="solo per type=budget: categorie di spesa precompilate")


class LineIdea(BaseModel):
    line: str = Field(description="slug minuscolo con trattini, es. 'meal-planner'")
    category: str
    rationale: str = Field(description="perché questa linea dovrebbe vendere ora, in 2-3 frasi")
    name: Localized
    subtitle: Localized
    audience: Localized
    keywords: LocalizedKeywords = Field(description="6-8 ricerche reali per lingua, max 20 caratteri l'una")
    year: int | None = Field(default=None, description="anno per un prodotto datato, altrimenti null")
    week_start: Literal["monday", "sunday"] = "monday"
    pages: list[PageIdea]
    themes: list[ThemeName]
    sizes: list[Literal["A4", "Letter", "A5"]]
    price_eur: float
    price_usd: float


class IdeaBatch(BaseModel):
    lines: list[LineIdea]


def to_spec(idea: LineIdea) -> LineSpec:
    pages: list[dict] = [{"type": "cover"}, {"type": "index"}]
    for p in idea.pages:
        opts: dict = {}
        if p.notes_style and p.type == "notes":
            opts["style"] = p.notes_style
        if p.title:
            opts["title"] = p.title.model_dump()
        if p.budget_categories and p.type == "budget":
            opts["categories"] = p.budget_categories.model_dump()
        pages.append({"type": p.type, "repeat": max(1, min(p.repeat, 60)), "options": opts})
    return LineSpec.model_validate({
        "line": idea.line, "category": idea.category,
        "name": idea.name.model_dump(), "subtitle": idea.subtitle.model_dump(),
        "audience": idea.audience.model_dump(), "keywords": idea.keywords.model_dump(),
        "year": idea.year if idea.year and idea.year >= dt.date.today().year else None,
        "week_start": idea.week_start, "pages": pages,
        "themes": list(dict.fromkeys(idea.themes))[:4] or ["minimal"],
        "langs": LANGS, "sizes": list(dict.fromkeys(idea.sizes)) or ["A4", "Letter"],
        "price": {"eur": round(min(max(idea.price_eur, 1.9), 19.9), 2),
                  "usd": round(min(max(idea.price_usd, 1.9), 21.9), 2)},
    })


def _prompt(existing: list[LineSpec], sales: dict, n: int, today: dt.date) -> str:
    catalog = "\n".join(
        f"- {s.line}: {s.name.get('en', next(iter(s.name.values())))} "
        f"({s.category}; pagine: {', '.join(p.type for p in s.pages)}; anno: {s.year or 'senza date'})"
        for s in existing)
    return f"""Gestisci un negozio Etsy di prodotti digitali stampabili (PDF) venduti in inglese, italiano e spagnolo.
Oggi è il {today.isoformat()}. Proponi {n} nuova/e linea/e di prodotto da aggiungere al catalogo.

CATALOGO ATTUALE (non duplicarlo; varianti chiaramente diverse vanno bene):
{catalog}

VENDITE FINORA (per linea, tema e lingua; vuoto = ancora nessuna vendita):
{json.dumps(sales, ensure_ascii=False) if sales else "nessuna vendita registrata"}

COSA PUÒ PRODURRE LA FABBRICA
Tipi di pagina: year (panoramica annuale), monthly (calendario mensile), weekly (settimana su una pagina),
daily (pagina giornaliera con orari, priorità, to-do, gratitudine, acqua), habit (tracker 31 giorni),
budget (entrate/uscite con categorie), checklist (righe con caselle, titolo personalizzabile),
goals (3 obiettivi con passi e scadenze), notes (righe, puntini o quadretti).
Copertina e indice cliccabile vengono aggiunti automaticamente.
Con `year` impostato, monthly genera i 12 mesi e weekly tutte le settimane dell'anno, con le date.
Temi: {', '.join(THEMES)}. Formati: A4, Letter, A5.

CRITERI
- Scegli nicchie con domanda reale su Etsy e poca concorrenza diretta; sfrutta la stagionalità
  (es. planner dell'anno successivo da settembre a gennaio, rientro a scuola in estate).
- Se ci sono vendite, punta su ciò che vende (stesse nicchie o temi) prima di esplorare.
- Usa titoli di pagina personalizzati per rendere il prodotto specifico (es. una checklist intitolata
  "Lista della spesa" in un meal planner), non generico.
- Prezzi realistici per stampabili: 2,90–9,90 EUR; i bundle grandi possono arrivare a 12,90 EUR.
- 2–4 temi per linea; parole chiave che un acquirente scriverebbe davvero, max 20 caratteri,
  solo lettere, numeri, spazi e trattini.
- Testi naturali in ciascuna lingua (non traduzioni letterali)."""


def generate_ideas(n: int, catalog_dir: Path = Path("catalog"),
                   sales_path: Path = Path("state/sales.json"),
                   today: dt.date | None = None) -> list[Path]:
    import anthropic

    existing = load_catalog([catalog_dir])
    sales = json.loads(sales_path.read_text()) if sales_path.exists() else {}
    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": _prompt(existing, sales, n, today or dt.date.today())}],
        output_format=IdeaBatch,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"nessuna idea utilizzabile (stop_reason={response.stop_reason})")

    taken = {s.line for s in existing}
    written = []
    out_dir = catalog_dir / "auto"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idea in response.parsed_output.lines[:n]:
        base = idea.line
        k = 2
        while idea.line in taken:
            idea.line = f"{base}-{k}"
            k += 1
        try:
            spec = to_spec(idea)
        except ValueError as exc:
            log.warning("idea scartata (%s): %s", idea.line, exc)
            continue
        taken.add(spec.line)
        path = out_dir / f"{spec.line}.yaml"
        header = (f"# Generata automaticamente il {dt.date.today().isoformat()}.\n"
                  f"# Motivazione: {idea.rationale}\n")
        body = yaml.safe_dump(spec.model_dump(mode="json", exclude_defaults=False),
                              allow_unicode=True, sort_keys=False)
        path.write_text(header + body, encoding="utf-8")
        written.append(path)
    return written

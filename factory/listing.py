"""Testi delle inserzioni: titolo, tag e descrizione.

Due motori:
- `template` (predefinito): deterministico, gratuito, offline.
- `claude`: testi scritti da Claude via API Anthropic (serve ANTHROPIC_API_KEY o `ant auth login`).
  Se la chiamata fallisce si torna al template, così la build non si blocca mai.

In entrambi i casi l'output passa da `enforce_limits`, che applica i limiti Etsy.
"""

from __future__ import annotations

import logging
import os

from pydantic import BaseModel, Field

from .i18n import SHOP
from .spec import Variant
from .themes import THEMES

log = logging.getLogger(__name__)

ETSY_TITLE_MAX = 140
ETSY_TAG_MAX = 20
ETSY_TAGS = 13
CLAUDE_MODEL = "claude-opus-5-5"


class ListingCopy(BaseModel):
    title: str
    tags: list[str] = Field(default_factory=list)
    description: str
    engine: str = "template"


INTRO = {
    "it": "{name} in stile {theme}: {subtitle}. Pensato per {audience}.",
    "en": "{name} in a {theme} style: {subtitle}. Made for {audience}.",
    "es": "{name} en estilo {theme}: {subtitle}. Pensada para {audience}.",
}
BODY = {
    "it": ("COSA RICEVI\n• {pages} pagine in PDF\n• Formati: {sizes}\n{linked}\n"
           "COME FUNZIONA\n1. Acquista e scarica subito i file\n2. Stampa a casa o in copisteria, "
           "oppure importa il PDF in GoodNotes / Notability\n3. Usa le pagine tutte le volte che vuoi\n\n"
           "NOTA: prodotto digitale, nessun articolo fisico verrà spedito. Solo per uso personale."),
    "en": ("WHAT YOU GET\n• {pages} PDF pages\n• Sizes: {sizes}\n{linked}\n"
           "HOW IT WORKS\n1. Purchase and download the files instantly\n2. Print at home or at a print shop, "
           "or import the PDF into GoodNotes / Notability\n3. Reprint pages as often as you like\n\n"
           "NOTE: this is a digital product, no physical item will be shipped. Personal use only."),
    "es": ("QUÉ RECIBES\n• {pages} páginas en PDF\n• Formatos: {sizes}\n{linked}\n"
           "CÓMO FUNCIONA\n1. Compra y descarga los archivos al instante\n2. Imprime en casa o en una imprenta, "
           "o importa el PDF en GoodNotes / Notability\n3. Reimprime las páginas cuantas veces quieras\n\n"
           "NOTA: producto digital, no se enviará ningún artículo físico. Solo para uso personal."),
}


def _clip_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,|-·")


def enforce_limits(copy: ListingCopy) -> ListingCopy:
    """Applica i limiti di Etsy: titolo <= 140, max 13 tag unici, ognuno <= 20 caratteri."""
    tags: list[str] = []
    for t in copy.tags:
        t = " ".join(t.lower().replace(",", " ").split())
        t = _clip_words(t, ETSY_TAG_MAX)
        if t and t not in tags:
            tags.append(t)
    return ListingCopy(
        title=_clip_words(" ".join(copy.title.split()), ETSY_TITLE_MAX),
        tags=tags[:ETSY_TAGS],
        description=copy.description.strip(),
        engine=copy.engine,
    )


def template_copy(variant: Variant, page_count: int) -> ListingCopy:
    lang = variant.lang
    theme = THEMES[variant.theme]["label"]
    shop = SHOP[lang]
    kw = variant.keywords
    title = " | ".join([f"{variant.name} {theme}", *kw[:4], shop["printable"] + " PDF"])
    audience = variant.spec.audience.get(lang, "")
    tpl = INTRO[lang] if audience else INTRO[lang].split(". ")[0] + "."
    intro = tpl.format(name=variant.name, theme=theme,
                       subtitle=variant.subtitle or shop["printable"], audience=audience)
    body = BODY[lang].format(pages=page_count, sizes=", ".join(variant.spec.sizes),
                             linked=f"• {shop['linked']}\n" if variant.spec.has_links else "")
    tags = [*kw, theme.lower(), shop["printable"].lower(), "pdf"]
    return enforce_limits(ListingCopy(title=title, tags=tags, description=f"{intro}\n\n{body}"))


def claude_copy(variant: Variant, page_count: int) -> ListingCopy:
    import anthropic

    base = template_copy(variant, page_count)
    prompt = f"""Scrivi il testo di un'inserzione Etsy per un prodotto digitale stampabile.
Lingua dell'inserzione: {variant.lang} (scrivi tutto in questa lingua).

Prodotto: {variant.name}
Sottotitolo: {variant.subtitle}
Tema grafico: {THEMES[variant.theme]['label']}
Pubblico: {variant.spec.audience.get(variant.lang, '')}
Pagine: {page_count}; formati: {', '.join(variant.spec.sizes)}
Parole chiave di partenza: {', '.join(variant.keywords)}

Bozza attuale da migliorare (mantieni tutti i fatti, non inventarne di nuovi):
TITOLO: {base.title}
DESCRIZIONE:
{base.description}

Regole:
- titolo massimo 140 caratteri, le parole chiave più cercate all'inizio, niente maiuscolo urlato
- esattamente 13 tag, ciascuno massimo 20 caratteri, ricerche reali che farebbe un acquirente
- descrizione: prima frase che venda il beneficio, poi le sezioni della bozza; testo semplice, niente markdown
- non promettere cose che il prodotto non ha (es. niente "modificabile" o "Canva")"""

    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
        output_format=ListingCopy,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"risposta non utilizzabile (stop_reason={response.stop_reason})")
    out = response.parsed_output
    out.engine = "claude"
    return enforce_limits(out)


def make_copy(variant: Variant, page_count: int, engine: str = "template") -> ListingCopy:
    if engine == "claude":
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.path.isdir(os.path.expanduser("~/.config/anthropic"))):
            log.warning("Nessuna credenziale Anthropic trovata: uso i testi da template")
        else:
            try:
                return claude_copy(variant, page_count)
            except Exception as exc:  # noqa: BLE001 - la build non deve fermarsi per un testo
                log.warning("Claude non disponibile per %s (%s): uso il template", variant.sku, exc)
    return template_copy(variant, page_count)

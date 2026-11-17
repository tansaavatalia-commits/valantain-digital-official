"""Pipeline completa per variante: PDF -> controlli -> mockup -> testi -> ZIP -> manifest.

È incrementale: se né la specifica né il codice sono cambiati, la variante viene saltata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium

from .listing import make_copy
from .mockup import make_mockups
from .pages import expand_pages
from .render import PKG, render_pdf
from .spec import LineSpec, Variant

log = logging.getLogger(__name__)

ETSY_FILE_MAX = 20 * 1024 * 1024  # 20 MB per file digitale su Etsy

LICENSE_TXT = {
    "it": "Grazie per l'acquisto!\n\nQuesti file sono per uso personale. Puoi stamparli tutte le volte "
          "che vuoi per te. Non è consentito rivenderli o condividerli.\n\n{brand}\n",
    "en": "Thank you for your purchase!\n\nThese files are for personal use. You may print them as often "
          "as you like for yourself. Reselling or sharing the files is not allowed.\n\n{brand}\n",
    "es": "¡Gracias por tu compra!\n\nEstos archivos son para uso personal. Puedes imprimirlos tantas veces "
          "como quieras para ti. No está permitido revenderlos ni compartirlos.\n\n{brand}\n",
}


def code_fingerprint() -> str:
    h = hashlib.sha256()
    for p in sorted(PKG.rglob("*")):
        if p.is_file() and p.suffix in {".py", ".j2"}:
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


@dataclass
class Result:
    sku: str
    status: str  # built | skipped | failed
    manifest: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def qa_pdf(pdf: Path, expected_pages: int) -> list[str]:
    problems = []
    doc = pdfium.PdfDocument(str(pdf))
    if len(doc) != expected_pages:
        problems.append(f"{pdf.name}: {len(doc)} pagine invece di {expected_pages}")
    doc.close()
    if pdf.stat().st_size > ETSY_FILE_MAX:
        problems.append(f"{pdf.name}: supera i 20 MB consentiti da Etsy")
    return problems


def build_variant(variant: Variant, dist: Path, copy_engine: str, force: bool,
                  stamp: str) -> Result:
    sku = variant.sku
    out = dist / variant.spec.line / sku
    stamp_file = out / ".stamp"
    manifest_file = out / "manifest.json"
    if not force and stamp_file.exists() and stamp_file.read_text() == stamp and manifest_file.exists():
        return Result(sku, "skipped", json.loads(manifest_file.read_text()))

    pages = expand_pages(variant)
    errors: list[str] = []
    pdfs: list[Path] = []
    for size in variant.spec.sizes:
        pdf = render_pdf(variant, size, out / "files" / f"{sku}-{size}.pdf")
        errors += qa_pdf(pdf, len(pages))
        pdfs.append(pdf)

    images = make_mockups(variant, pdfs[0], pages, out / "images", variant.spec.sizes)
    copy = make_copy(variant, len(pages), copy_engine)
    (out / "listing.txt").write_text(
        f"{copy.title}\n\nTAG: {', '.join(copy.tags)}\n\n{copy.description}\n", encoding="utf-8")

    bundle = out / f"{sku}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for pdf in pdfs:
            z.write(pdf, pdf.name)
        z.writestr("LEGGIMI-README.txt", LICENSE_TXT[variant.lang].format(brand="Valantain Digital"))

    # Su Etsy si caricano fino a 5 file da 20 MB: lo ZIP se ci sta, altrimenti i PDF singoli.
    deliver = [bundle] if bundle.stat().st_size <= ETSY_FILE_MAX else pdfs
    if len(deliver) > 5:
        errors.append("più di 5 file da consegnare: riduci i formati o le pagine")

    rel = lambda p: str(p.relative_to(dist))
    manifest = {
        "sku": sku, "line": variant.spec.line, "category": variant.spec.category,
        "theme": variant.theme, "lang": variant.lang, "year": variant.spec.year,
        "pages": len(pages), "sizes": variant.spec.sizes,
        "price": variant.spec.price.model_dump(),
        "etsy": variant.spec.etsy.model_dump(),
        "title": copy.title, "tags": copy.tags, "description": copy.description,
        "copy_engine": copy.engine,
        "files": [rel(p) for p in deliver], "pdfs": [rel(p) for p in pdfs],
        "images": [rel(p) for p in images],
        "qa_errors": errors,
    }
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not errors:
        stamp_file.write_text(stamp)
    return Result(sku, "failed" if errors else "built", manifest, errors)


def _job(args: tuple) -> Result:
    spec_json, theme, lang, dist, engine, force, stamp = args
    variant = Variant(spec=LineSpec.model_validate(spec_json), theme=theme, lang=lang)
    try:
        return build_variant(variant, Path(dist), engine, force, stamp)
    except Exception as exc:  # una variante rotta non ferma le altre
        logging.getLogger(__name__).exception("errore su %s", variant.sku)
        return Result(variant.sku, "failed", errors=[repr(exc)])


def build_all(specs: list[LineSpec], dist: Path, *, copy_engine: str = "template",
              force: bool = False, only: str | None = None, workers: int | None = None
              ) -> list[Result]:
    code = code_fingerprint()
    jobs = []
    for spec in specs:
        stamp = f"{spec.fingerprint()}-{code}-{copy_engine}"
        for v in spec.variants():
            if only and only not in v.sku:
                continue
            jobs.append((spec.model_dump(mode="json"), v.theme, v.lang, str(dist),
                         copy_engine, force, stamp))
    results: list[Result] = []
    if workers == 1 or len(jobs) <= 1:
        results = [_job(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_job, j) for j in jobs]
            for f in as_completed(futures):
                r = f.result()
                log.info("%-8s %s", r.status, r.sku)
                results.append(r)
    return sorted(results, key=lambda r: r.sku)

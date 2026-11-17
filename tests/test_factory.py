import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from factory.cli import main
from factory.listing import ListingCopy, enforce_limits, template_copy
from factory.pages import expand_pages, year_weeks
from factory.spec import LineSpec, load_catalog

ROOT = Path(__file__).resolve().parents[1]


def small_spec(**over) -> LineSpec:
    data = {
        "line": "test-kit", "category": "tracker",
        "name": {"it": "Kit Test", "en": "Test Kit"},
        "keywords": {"it": ["habit tracker", "budget"], "en": ["habit tracker", "budget"]},
        "pages": [{"type": "cover"}, {"type": "index"}, {"type": "habit"},
                  {"type": "notes", "repeat": 2}],
        "themes": ["sage"], "langs": ["it", "en"], "sizes": ["A4"],
        "price": {"eur": 3.9},
    }
    data.update(over)
    return LineSpec.model_validate(data)


def test_catalog_is_valid():
    specs = load_catalog([ROOT / "catalog"])
    assert specs and all(s.variants() for s in specs)


def test_variants_and_skus_are_unique():
    skus = [v.sku for s in load_catalog([ROOT / "catalog"]) for v in s.variants()]
    assert len(skus) == len(set(skus))


def test_invalid_theme_rejected():
    with pytest.raises(ValidationError):
        small_spec(themes=["neon"])


def test_missing_name_for_lang_rejected():
    with pytest.raises(ValidationError):
        small_spec(langs=["it", "es"])


def test_year_weeks_cover_whole_year():
    weeks = year_weeks(2027, "monday")
    assert weeks[0][0].weekday() == 0
    assert weeks[0][0].year == 2026 and weeks[-1][-1].year in (2027, 2028)
    assert all(len(w) == 7 for w in weeks)


def test_dated_planner_page_count():
    spec = small_spec(year=2027, pages=[{"type": "monthly"}, {"type": "weekly"}])
    pages = expand_pages(spec.variants()[0])
    assert sum(p["type"] == "monthly" for p in pages) == 12
    assert sum(p["type"] == "weekly" for p in pages) == len(year_weeks(2027, "monday"))


def test_index_links_point_to_existing_pages():
    pages = expand_pages(small_spec().variants()[0])
    ids = {p["id"] for p in pages}
    index = next(p for p in pages if p["type"] == "index")
    assert index["sections"] and all(s["id"] in ids for s in index["sections"])


def test_etsy_limits_enforced():
    copy = enforce_limits(ListingCopy(
        title="parola " * 40, description=" ok ",
        tags=["Un tag davvero molto lungo oltre venti", "a", "A", *[f"tag{i}" for i in range(20)]]))
    assert len(copy.title) <= 140
    assert len(copy.tags) == 13 and len(set(copy.tags)) == 13
    assert all(len(t) <= 20 for t in copy.tags)


def test_template_copy_mentions_links_only_with_index():
    with_index = template_copy(small_spec().variants()[0], 5)
    without = template_copy(small_spec(pages=[{"type": "habit"}]).variants()[0], 1)
    assert "GoodNotes e Notability" in with_index.description
    assert "Link interni" not in without.description


def test_build_end_to_end(tmp_path):
    spec_file = tmp_path / "kit.yaml"
    spec_file.write_text(json.dumps(small_spec(langs=["it"], name={"it": "Kit Test"}).model_dump(mode="json")))
    out = tmp_path / "dist"
    assert main(["build", str(spec_file), "--out", str(out), "--workers", "1"]) == 0
    m = json.loads((out / "test-kit" / "test-kit-sage-it" / "manifest.json").read_text())
    assert m["pages"] == 5 and not m["qa_errors"]
    assert all((out / f).exists() for f in m["files"] + m["images"])
    assert (out / "catalog.csv").exists()
    # seconda esecuzione: nulla da rifare
    assert main(["build", str(spec_file), "--out", str(out), "--workers", "1"]) == 0

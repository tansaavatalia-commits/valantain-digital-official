import json

import httpx
import pytest

from factory.build import build_all
from factory.config import Config, EtsyConfig
from factory.etsy import Etsy, EtsyError, clean_tag, clean_title, code_from_redirect, make_pkce
from factory.ideas import LineIdea, to_spec
from factory.publish import group_manifests, load_state, publish
from factory.spec import LineSpec


def tiny_spec(langs=("it", "en")) -> LineSpec:
    return LineSpec.model_validate({
        "line": "mini", "category": "tracker",
        "name": {lang: f"Mini {lang}" for lang in langs},
        "keywords": {lang: ["habit tracker", "printable & pdf"] for lang in langs},
        "pages": [{"type": "cover"}, {"type": "index"}, {"type": "checklist"}],
        "themes": ["sage"], "langs": list(langs), "sizes": ["A4"], "price": {"eur": 2.5, "usd": 2.9},
    })


class FakeEtsy:
    """Finto server Etsy: registra le chiamate e può fallire su un percorso."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[str, str]] = []
        self.fail_on = fail_on
        self.next_id = 1000

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        assert request.url.path.endswith("/oauth/token") or \
            request.headers["x-api-key"] == "key:secret"
        if self.fail_on and self.fail_on in path:
            return httpx.Response(400, text="rifiutato")
        if path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "1.a", "refresh_token": "1.r-new",
                                             "expires_in": 3600})
        if request.method == "POST" and path.endswith("/listings"):
            body = dict(httpx.QueryParams(request.content.decode()))
            assert body["type"] == "download" and body["taxonomy_id"] == "77"
            assert len(body["title"]) <= 140 and "&" not in body["tags"]
            self.next_id += 1
            return httpx.Response(201, json={"listing_id": self.next_id, "url": f"https://etsy.test/{self.next_id}"})
        return httpx.Response(200, json={"ok": True})


def make_client(fake) -> Etsy:
    return Etsy("key", "secret", "1.r-old", http=httpx.Client(transport=httpx.MockTransport(fake)))


@pytest.fixture
def built(tmp_path):
    dist = tmp_path / "dist"
    results = build_all([tiny_spec()], dist, workers=1)
    assert all(r.status == "built" for r in results)
    return dist


def test_sanitizers():
    assert clean_title("A & B & C: x: 50% 50%") == "A & B C: x 50% 50"
    assert clean_tag("printable & pdf!") == "printable pdf"
    assert len(clean_tag("a" * 40)) == 20


def test_pkce_and_redirect():
    verifier, challenge = make_pkce()
    assert 43 <= len(verifier) <= 128 and challenge and "=" not in challenge
    assert code_from_redirect("https://github.com/x/y?code=abc&state=s") == "abc"
    assert code_from_redirect(" abc ") == "abc"
    with pytest.raises(RuntimeError):
        code_from_redirect("https://github.com/x/y?code=&error=access_denied&error_description=no")


def test_refresh_returns_new_token():
    client = make_client(FakeEtsy())
    assert client.refresh() == "1.r-new"


def test_groups_merge_languages(built):
    (g,) = group_manifests(built)
    assert g.key == "mini-sage" and sorted(g.manifests) == ["en", "it"]


def test_publish_full_flow_and_idempotency(built, tmp_path):
    fake = FakeEtsy()
    state_path = tmp_path / "state" / "etsy.json"
    rep = publish(built, make_client(fake), EtsyConfig(), state_path,
                  shop_id=5, currency="EUR", taxonomy_id=77)
    assert len(rep.published) == 1 and not rep.failed
    entry = load_state(state_path)["mini-sage"]
    assert entry["step"] == "done" and entry["primary"] == "en"
    methods = [c for c in fake.calls if "oauth" not in c[1]]
    assert methods[0] == ("POST", "/v3/application/shops/5/listings")
    (group,) = group_manifests(built)
    n_images = len(group.manifests["en"]["images"])
    assert n_images >= 3 and sum(p.endswith("/images") for _, p in methods) == n_images
    assert sum(p.endswith("/files") for _, p in methods) == 2      # un file per lingua
    assert sum("/translations/it" in p for _, p in methods) == 1
    assert methods[-1][0] == "PATCH"                                  # attivazione
    # seconda esecuzione: nessuna nuova chiamata di scrittura
    fake2 = FakeEtsy()
    rep2 = publish(built, make_client(fake2), EtsyConfig(), state_path,
                   shop_id=5, currency="EUR", taxonomy_id=77)
    assert not rep2.published and not [c for c in fake2.calls if "oauth" not in c[1]]


def test_publish_resumes_after_failure(built, tmp_path):
    state_path = tmp_path / "etsy.json"
    rep = publish(built, make_client(FakeEtsy(fail_on="/files")), EtsyConfig(), state_path,
                  shop_id=5, currency="EUR", taxonomy_id=77)
    assert rep.failed and load_state(state_path)["mini-sage"]["step"] == "images"
    fake = FakeEtsy()
    rep = publish(built, make_client(fake), EtsyConfig(), state_path,
                  shop_id=5, currency="EUR", taxonomy_id=77)
    assert rep.resumed and load_state(state_path)["mini-sage"]["step"] == "done"
    assert not any(m == "POST" and p.endswith("/listings") for m, p in fake.calls)  # niente doppioni


def test_publish_respects_budget_and_draft_mode(built, tmp_path):
    fake = FakeEtsy()
    rep = publish(built, make_client(fake), EtsyConfig(max_new_listings_per_run=0), tmp_path / "s.json",
                  shop_id=5, currency="EUR", taxonomy_id=77)
    assert rep.pending == 1 and not rep.published
    fake = FakeEtsy()
    publish(built, make_client(fake), EtsyConfig(mode="draft"), tmp_path / "s2.json",
            shop_id=5, currency="EUR", taxonomy_id=77)
    assert not any(m == "PATCH" for m, _ in fake.calls)


def test_auth_error_stops_publishing(built, tmp_path):
    def deny(request):
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "1.a", "refresh_token": "1.b"})
        return httpx.Response(403, text="app non approvata")
    rep = publish(built, make_client(deny), EtsyConfig(), tmp_path / "s.json",
                  shop_id=5, currency="EUR", taxonomy_id=77)
    assert "mini-sage" in rep.failed
    with pytest.raises(EtsyError):
        make_client(deny).me()


def test_idea_becomes_valid_spec():
    loc = {"it": "Spesa", "en": "Groceries", "es": "Compra"}
    idea = LineIdea.model_validate({
        "line": "meal-planner", "category": "planner", "rationale": "test",
        "name": loc, "subtitle": loc, "audience": loc,
        "keywords": {"it": ["menu"], "en": ["meal plan"], "es": ["menu"]},
        "year": 1999, "pages": [{"type": "weekly", "repeat": 500},
                                {"type": "checklist", "repeat": 2, "title": loc},
                                {"type": "notes", "repeat": 1, "notes_style": "dots"}],
        "themes": ["sage", "sage", "blush"], "sizes": ["A4"], "price_eur": 99, "price_usd": 0.5,
    })
    spec = to_spec(idea)
    assert spec.year is None                          # anno passato scartato
    assert spec.pages[0].type == "cover" and spec.pages[1].type == "index"
    assert spec.pages[2].repeat == 60                 # repeat limitato
    assert spec.themes == ["sage", "blush"]
    assert spec.price.eur == 19.9 and spec.price.usd == 1.9


def test_autopilot_without_credentials_still_builds(tmp_path, monkeypatch):
    from factory.autopilot import Paths, run

    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ETSY_KEYSTRING", "ETSY_SHARED_SECRET",
              "ETSY_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    cat = tmp_path / "catalog"
    cat.mkdir()
    (cat / "mini.yaml").write_text(json.dumps(tiny_spec(("it",)).model_dump(mode="json")))
    out = run(Config(), Paths(catalog=cat, dist=tmp_path / "dist", state=tmp_path / "state",
                              reports=tmp_path / "reports"), None)
    text = "\n".join(out.lines)
    assert not out.failed
    assert "Etsy non ancora collegato" in text and "manca ANTHROPIC_API_KEY" in text
    assert (tmp_path / "dist" / "catalog.csv").exists()


def test_sales_report(tmp_path):
    import time

    from factory.report import sales_report

    now = int(time.time())

    def shop(request):
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "1.a", "refresh_token": "1.b"})
        money = {"amount": 690, "divisor": 100, "currency_code": "EUR"}
        return httpx.Response(200, json={"count": 2, "results": [
            {"created_timestamp": now, "grandtotal": money,
             "transactions": [{"listing_id": 11, "quantity": 1, "price": money}]},
            {"created_timestamp": now - 60 * 86400, "grandtotal": money,
             "transactions": [{"listing_id": 11, "quantity": 2, "price": money}]},
        ]})

    path = sales_report(make_client(shop), 5, {"planner-sage": {"listing_id": 11, "step": "done"}},
                        tmp_path / "reports", tmp_path / "sales.json")
    sales = json.loads((tmp_path / "sales.json").read_text())
    assert sales == {"planner-sage": {"orders": 3, "revenue": 20.7}}
    text = path.read_text()
    assert "ultimi 7 giorni: **1**" in text and "6.90 EUR" in text


def test_vault_roundtrip_and_wrong_key(tmp_path):
    from factory.vault import seal, unseal

    f = tmp_path / "t.enc"
    seal(f, "1.segreto", "chiave")
    assert b"segreto" not in f.read_bytes()
    assert unseal(f, "chiave") == "1.segreto"
    assert unseal(tmp_path / "manca.enc", "chiave") is None
    with pytest.raises(RuntimeError):
        unseal(f, "altra-chiave")


def test_autopilot_rotates_token_into_vault(tmp_path, monkeypatch):
    import factory.etsy as etsy_mod
    from factory.autopilot import Paths, run
    from factory.vault import TOKEN_FILE, seal, unseal

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_REFRESH_TOKEN", raising=False)
    monkeypatch.setenv("ETSY_KEYSTRING", "key")
    monkeypatch.setenv("ETSY_SHARED_SECRET", "secret")
    state = tmp_path / "state"
    seal(state / TOKEN_FILE, "1.r-old", "secret")

    def shop(request):
        p = request.url.path
        if p.endswith("/oauth/token"):
            assert b"1.r-old" in request.content
            return httpx.Response(200, json={"access_token": "1.a", "refresh_token": "1.r-rotated"})
        if p.endswith("/users/me"):
            return httpx.Response(200, json={"user_id": 1, "shop_id": 5})
        if p.endswith("/receipts"):
            return httpx.Response(200, json={"count": 0, "results": []})
        if p.endswith("/seller-taxonomy/nodes"):
            return httpx.Response(200, json={"results": [{"id": 77, "name": "Calendars & Planners"}]})
        if p.endswith("/shops/5"):
            return httpx.Response(200, json={"currency_code": "EUR"})
        return FakeEtsy()(request)

    real_client = httpx.Client
    monkeypatch.setattr(etsy_mod.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(shop)))
    cat = tmp_path / "catalog"
    cat.mkdir()
    (cat / "mini.yaml").write_text(json.dumps(tiny_spec().model_dump(mode="json")))
    out = run(Config(), Paths(catalog=cat, dist=tmp_path / "dist", state=state,
                              reports=tmp_path / "reports"))
    assert not out.failed, out.lines
    assert unseal(state / TOKEN_FILE, "secret") == "1.r-rotated"
    assert load_state(state / "etsy.json")["mini-sage"]["step"] == "done"

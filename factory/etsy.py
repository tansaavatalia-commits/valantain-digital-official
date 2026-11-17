"""Client minimo per Etsy Open API v3 (https://developers.etsy.com/documentation).

Autenticazione: header `x-api-key: <keystring>:<shared_secret>` + OAuth 2.0 con PKCE.
Il token di accesso dura 1 ora, il refresh token 90 giorni; ogni refresh ne restituisce uno nuovo,
che va salvato (in CI lo fa il workflow, aggiornando il secret su GitHub).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

log = logging.getLogger(__name__)

API = "https://api.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
CONNECT_URL = "https://www.etsy.com/oauth/connect"
SCOPES = "listings_r listings_w shops_r transactions_r"

# Regole Etsy (dalle specifiche OpenAPI):
#   titolo: lettere, cifre, punteggiatura, simboli matematici, spazi, ™©®; %, :, &, + una volta sola
#   tag:    lettere, cifre, spazi, - e ', ™©®; massimo 20 caratteri


def clean_title(title: str) -> str:
    out, seen = [], set()
    for ch in title:
        cat = unicodedata.category(ch)
        ok = cat.startswith(("L", "P")) or cat == "Nd" or cat == "Sm" or cat == "Zs" or ch in "™©®"
        if not ok:
            continue
        if ch in "%:&+":
            if ch in seen:
                continue
            seen.add(ch)
        out.append(ch)
    return " ".join("".join(out).split())


def clean_tag(tag: str) -> str:
    kept = "".join(ch if (unicodedata.category(ch)[0] == "L" or unicodedata.category(ch) == "Nd"
                          or ch in " -'™©®") else " " for ch in tag)
    return " ".join(kept.split())[:20].strip()


# ---------------------------------------------------------------- OAuth / PKCE

def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(keystring: str, redirect_uri: str, challenge: str, state: str) -> str:
    return CONNECT_URL + "?" + urlencode({
        "response_type": "code", "client_id": keystring, "redirect_uri": redirect_uri,
        "scope": SCOPES, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def code_from_redirect(url_or_code: str) -> str:
    """Accetta l'URL completo su cui Etsy ha rimandato l'utente, oppure il solo codice."""
    if "code=" not in url_or_code:
        return url_or_code.strip()
    q = parse_qs(urlparse(url_or_code.strip()).query)
    if "error" in q:
        raise RuntimeError(f"Etsy ha rifiutato l'autorizzazione: {q.get('error_description', q['error'])}")
    return q["code"][0]


def exchange_code(keystring: str, redirect_uri: str, code: str, verifier: str) -> dict:
    r = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code", "client_id": keystring,
        "redirect_uri": redirect_uri, "code": code, "code_verifier": verifier,
    }, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"scambio del codice fallito ({r.status_code}): {r.text[:300]}")
    return r.json()


# ---------------------------------------------------------------- client

class EtsyError(RuntimeError):
    def __init__(self, status: int, body: str, what: str):
        super().__init__(f"{what}: HTTP {status} {body[:400]}")
        self.status = status


class Etsy:
    def __init__(self, keystring: str, shared_secret: str, refresh_token: str,
                 http: httpx.Client | None = None):
        self.keystring = keystring
        self.api_key = f"{keystring}:{shared_secret}"
        self.refresh_token = refresh_token
        self.access_token: str | None = None
        self.http = http or httpx.Client(timeout=120)

    def refresh(self) -> str:
        """Rinnova il token di accesso. Restituisce il NUOVO refresh token, da salvare."""
        r = self.http.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "client_id": self.keystring,
            "refresh_token": self.refresh_token,
        })
        if r.status_code != 200:
            raise EtsyError(r.status_code, r.text, "rinnovo token")
        data = r.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return self.refresh_token

    def _call(self, method: str, path: str, what: str, **kw) -> dict:
        if self.access_token is None:
            self.refresh()
        headers = {"x-api-key": self.api_key, "Authorization": f"Bearer {self.access_token}"}
        for attempt in range(6):
            r = self.http.request(method, API + path, headers=headers, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after") or 2 ** attempt)
                log.warning("%s: HTTP %s, riprovo tra %.0fs", what, r.status_code, wait)
                time.sleep(min(wait, 60))
                continue
            if r.status_code >= 400:
                raise EtsyError(r.status_code, r.text, what)
            return r.json() if r.content else {}
        raise EtsyError(r.status_code, r.text, what)

    # --- lettura
    def me(self) -> dict:
        return self._call("GET", "/users/me", "utente")

    def shop(self, shop_id: int) -> dict:
        return self._call("GET", f"/shops/{shop_id}", "negozio")

    def taxonomy_id(self, name: str) -> int:
        """ID della categoria con questo nome; se non c'è, la prima che lo contiene."""
        nodes = self._call("GET", "/seller-taxonomy/nodes", "categorie")["results"]
        flat, stack = [], list(nodes)
        while stack:
            n = stack.pop()
            flat.append(n)
            stack.extend(n.get("children") or [])
        wanted = name.lower()
        for match in (lambda n: n["name"].lower() == wanted, lambda n: wanted in n["name"].lower()):
            found = sorted((n for n in flat if match(n)), key=lambda n: n.get("level", 0))
            if found:
                return int(found[0]["id"])
        raise RuntimeError(f"categoria Etsy non trovata: {name!r}; cambia taxonomy_name in autopilot.yaml")

    def receipts(self, shop_id: int, min_created: int | None = None) -> list[dict]:
        out, offset = [], 0
        while True:
            params = {"limit": 100, "offset": offset, "was_paid": "true"}
            if min_created:
                params["min_created"] = min_created
            page = self._call("GET", f"/shops/{shop_id}/receipts", "ricevute", params=params)
            out += page.get("results", [])
            offset += 100
            if offset >= page.get("count", 0):
                return out

    # --- scrittura
    def create_draft(self, shop_id: int, fields: dict) -> dict:
        data = {k: (",".join(map(str, v)) if isinstance(v, list) else v) for k, v in fields.items()}
        return self._call("POST", f"/shops/{shop_id}/listings", "bozza inserzione", data=data)

    def upload_image(self, shop_id: int, listing_id: int, path: Path, rank: int, alt: str) -> dict:
        with path.open("rb") as f:
            return self._call("POST", f"/shops/{shop_id}/listings/{listing_id}/images", "immagine",
                              files={"image": (path.name, f, "image/jpeg")},
                              data={"rank": str(rank), "alt_text": alt[:500]})

    def upload_file(self, shop_id: int, listing_id: int, path: Path, rank: int) -> dict:
        with path.open("rb") as f:
            return self._call("POST", f"/shops/{shop_id}/listings/{listing_id}/files", "file digitale",
                              files={"file": (path.name, f, "application/octet-stream")},
                              data={"name": path.name, "rank": str(rank)})

    def translate(self, shop_id: int, listing_id: int, lang: str, title: str, description: str,
                  tags: list[str]) -> dict:
        return self._call("POST", f"/shops/{shop_id}/listings/{listing_id}/translations/{lang}",
                          f"traduzione {lang}",
                          data={"title": title, "description": description, "tags": ",".join(tags)})

    def update(self, shop_id: int, listing_id: int, fields: dict) -> dict:
        return self._call("PATCH", f"/shops/{shop_id}/listings/{listing_id}", "aggiornamento inserzione",
                          data=fields)

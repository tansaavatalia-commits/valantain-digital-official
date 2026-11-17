"""Cassaforte per i token Etsy, salvata cifrata nel repository (`state/*.enc`).

La chiave deriva dal secret ETSY_SHARED_SECRET, che esiste solo nei secret di GitHub:
chi legge il repository vede solo testo cifrato. Così il pilota può salvare da solo il
refresh token che Etsy rinnova a ogni uso, senza un token GitHub aggiuntivo.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

TOKEN_FILE = "etsy-token.enc"
PKCE_FILE = "etsy-pkce.enc"


def _fernet(shared_secret: str) -> Fernet:
    digest = hashlib.sha256(b"valantain-vault:" + shared_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(path: Path, value: str, shared_secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet(shared_secret).encrypt(value.encode()) + b"\n")


def unseal(path: Path, shared_secret: str) -> str | None:
    if not path.exists():
        return None
    try:
        return _fernet(shared_secret).decrypt(path.read_bytes().strip()).decode()
    except InvalidToken as exc:
        raise RuntimeError(f"{path} non si decifra: ETSY_SHARED_SECRET è cambiato? "
                           "Rifai il collegamento Etsy.") from exc

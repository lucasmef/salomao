from __future__ import annotations

import base64
import hashlib
import os

from app.core.config import get_settings


class CryptoUnavailableError(RuntimeError):
    pass


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise CryptoUnavailableError(
            "Pacote 'cryptography' nao esta instalado. Instale as dependencias do backend antes de usar criptografia."
        ) from exc
    return AESGCM


def _key_bytes() -> bytes:
    settings = get_settings()
    return hashlib.sha256(settings.field_encryption_key.encode("utf-8")).digest()


def encrypt_bytes(payload: bytes) -> bytes:
    aesgcm = _aesgcm()(_key_bytes())
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, payload, b"gestor-financeiro")
    return nonce + encrypted


def decrypt_bytes(payload: bytes) -> bytes:
    aesgcm = _aesgcm()(_key_bytes())
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aesgcm.decrypt(nonce, ciphertext, b"gestor-financeiro")


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    encrypted = encrypt_bytes(value.encode("utf-8"))
    token = base64.urlsafe_b64encode(encrypted).decode("ascii")
    return f"enc:v1:{token}"


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith("enc:v1:"):
        return value
    raw = base64.urlsafe_b64decode(value.split(":", 2)[2].encode("ascii"))
    return decrypt_bytes(raw).decode("utf-8")


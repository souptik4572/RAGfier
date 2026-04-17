from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from cryptography.fernet import Fernet

from app.config import get_settings


def generate_api_key(prefix: str | None = None) -> tuple[str, str]:
    settings = get_settings()
    key_prefix = prefix or f"{settings.platform_api_key_prefix}_{secrets.token_hex(4)}"
    secret = secrets.token_urlsafe(24)
    return key_prefix, f"{key_prefix}.{secret}"


def hash_api_key(secret: str) -> str:
    key = get_settings().platform_api_key_secret.encode("utf-8")
    return hmac.new(key, secret.encode("utf-8"), hashlib.sha256).hexdigest()


def derive_api_key_prefix(secret: str) -> str:
    if "." not in secret:
        raise ValueError("API key is malformed.")
    return secret.split(".", 1)[0]


def encrypt_connector_config(config: dict[str, Any]) -> str:
    token = _fernet().encrypt(json.dumps(config, separators=(",", ":")).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_connector_config(payload: str) -> dict[str, Any]:
    raw = _fernet().decrypt(payload.encode("utf-8"))
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.platform_encryption_key.strip()
    if raw:
        return Fernet(raw.encode("utf-8"))
    digest = hashlib.sha256(settings.platform_api_key_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

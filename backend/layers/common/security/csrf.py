from __future__ import annotations

import hashlib
import hmac
import secrets


class CsrfError(ValueError):
    code = "CSRF_INVALID"

    def __init__(self, message: str = "CSRF Token 无效或已缺失") -> None:
        super().__init__(message)


def generate_csrf_token(secret_key: str) -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(secret_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def validate_csrf_token(provided: str | None, expected: str | None) -> None:
    if not provided or not expected or not hmac.compare_digest(provided, expected):
        raise CsrfError()

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{8,128}")


def request_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_key(value: str) -> str:
    if not KEY_PATTERN.fullmatch(value.strip()):
        raise DomainError("INVALID_IDEMPOTENCY_KEY", "幂等键格式无效", 400)
    return value.strip()


def key_hash(value: str) -> str:
    return hashlib.sha256(validate_key(value).encode("utf-8")).hexdigest()


def validate_replay(*, stored_request_hash: str, incoming_request_hash: str) -> None:
    if stored_request_hash != incoming_request_hash:
        raise DomainError("IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求", 409)


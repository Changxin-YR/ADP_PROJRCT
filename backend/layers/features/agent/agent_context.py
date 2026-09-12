"""Short-lived encrypted context delegated from the logged-in web session."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError

_AGENT_CONTEXT_TTL_SECONDS = 180


def _context_cipher(settings: Settings) -> Fernet:
    material = f"adp-agent-context-v1:{settings.flask_secret_key}".encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def _issue_context(
    settings: Settings,
    session_token: str,
    *,
    raw_instruction: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
) -> str:
    if not session_token:
        raise AgentGatewayError("UNAUTHENTICATED", "当前会话不能委托给智能体", 401)
    claims: dict[str, str] = {"session_token": session_token}
    for name, value in (("raw_instruction", raw_instruction), ("conversation_id", conversation_id), ("request_id", request_id)):
        if value is not None and str(value).strip():
            claims[name] = str(value)
    payload = json.dumps(claims, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _context_cipher(settings).encrypt(payload).decode("ascii")


def _decode_context_claims(settings: Settings, token: str) -> dict[str, str] | None:
    if not token:
        return None
    try:
        value = _context_cipher(settings).decrypt(token.encode("ascii"), ttl=_AGENT_CONTEXT_TTL_SECONDS).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError):
        return None
    try:
        claims: Any = json.loads(value)
    except (TypeError, ValueError):
        return {"session_token": value} if value else None
    if not isinstance(claims, dict) or not isinstance(claims.get("session_token"), str) or not claims["session_token"]:
        return None
    return {str(key): str(item) for key, item in claims.items() if item is not None}


def _decode_context_token(settings: Settings, token: str) -> str | None:
    claims = _decode_context_claims(settings, token)
    return claims.get("session_token") if claims else None

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol

ConfirmationStatus = Literal["pending", "confirmed", "cancelled", "expired"]


@dataclass(frozen=True)
class AgentConfirmation:
    id: int
    idempotency_key: str
    token_hash: str
    user_id: int
    session_hash: str
    conversation_id: str
    request_id: str
    tool_name: str
    payload: Mapping[str, Any]
    status: ConfirmationStatus
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime | None = None


class AgentConfirmationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentConfirmationStore(Protocol):
    def create(self, confirmation: AgentConfirmation, token: str) -> AgentConfirmation: ...
    def find(self, *, token: str, user_id: int, session_hash: str) -> AgentConfirmation | None: ...
    def claim(self, *, token: str, user_id: int, session_hash: str, now: datetime | None = None) -> AgentConfirmation | None: ...
    def mark_cancelled(self, confirmation_id: int, *, user_id: int) -> bool: ...
    def mark_expired(self, *, now: datetime | None = None) -> int: ...

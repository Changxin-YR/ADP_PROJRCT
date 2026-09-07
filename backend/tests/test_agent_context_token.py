from __future__ import annotations

import pytest

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.product.agent.routes import _decode_context_token, _issue_context


def _settings(secret: str) -> Settings:
    return Settings.from_env({"APP_ENV": "test", "FLASK_SECRET_KEY": secret})


def test_agent_context_is_stateless_across_workers_and_hides_session_token() -> None:
    settings = _settings("shared-worker-secret")
    session_token = "session-secret-that-must-not-be-visible"

    # Issue and decode do not share mutable process memory. A different worker
    # with the same deployment secret can decrypt the short-lived delegation.
    delegated = _issue_context(settings, session_token)
    assert session_token not in delegated
    assert _decode_context_token(_settings("shared-worker-secret"), delegated) == session_token


def test_agent_context_rejects_wrong_deployment_key_and_tampering() -> None:
    delegated = _issue_context(_settings("worker-a-secret"), "session-token")
    assert _decode_context_token(_settings("worker-b-secret"), delegated) is None

    replacement = "A" if delegated[-1] != "A" else "B"
    assert _decode_context_token(_settings("worker-a-secret"), delegated[:-1] + replacement) is None


def test_agent_context_cannot_be_issued_without_authenticated_session() -> None:
    with pytest.raises(AgentGatewayError) as exc:
        _issue_context(_settings("shared-worker-secret"), "")
    assert exc.value.code == "UNAUTHENTICATED"

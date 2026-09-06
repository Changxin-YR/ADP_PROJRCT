from pathlib import Path

import pytest

from backend.config.settings import ConfigError, Settings
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
import backend.layers.features.agent.agent_confirmation_store as confirmation_store_module
from datetime import datetime, timedelta


def test_agent_settings_defaults_and_sidecar_paths() -> None:
    settings = Settings.from_env({"APP_ENV": "test"})
    assert settings.agent_request_timeout_seconds == 30
    assert settings.agent_confirmation_ttl_seconds == 120
    assert settings.agent_sidecar_home
    assert settings.agent_sidecar_cwd
    assert settings.agent_sidecar_command


@pytest.mark.parametrize(
    ("name", "value"),
    [("AGENT_REQUEST_TIMEOUT_SECONDS", "61"), ("AGENT_CONFIRMATION_TTL_SECONDS", "601")],
)
def test_agent_settings_enforce_upper_bounds(name: str, value: str) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env({"APP_ENV": "test", name: value})


def test_production_requires_agent_sidecar_home() -> None:
    with pytest.raises(ConfigError, match="AGENT_SIDECAR_HOME"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "FLASK_SECRET_KEY": "flask",
                "CSRF_SECRET_KEY": "csrf",
                "MYSQL_PASSWORD": "mysql",
                "SESSION_COOKIE_SECURE": "true",
            }
        )


def test_agent_confirmation_migration_declares_atomic_claim_contract() -> None:
    sql = (Path(__file__).parents[2] / "database/migrations/031_agent_confirmations.sql").read_text().lower()
    for field in ("token_hash char(64)", "user_id", "session_hash char(64)", "conversation_id varchar(64)", "request_id varchar(64)", "tool_name", "payload_json json", "expires_at datetime(6)", "used_at datetime(6)", "created_at datetime(6)", "current_timestamp(6)", "idx_agent_confirmations_user_status"):
        assert field in sql
    assert "status enum('pending','confirmed','cancelled','expired')" in sql
    assert "unique" in sql
    assert "default 'pending'" in sql


def _confirmation(status="pending", expires_at=None):
    return AgentConfirmation(0, "key", "", 1, "session", "conversation", "request", "tool", {}, status, expires_at or datetime.now() + timedelta(minutes=1))


def test_create_rejects_non_pending_confirmation() -> None:
    with pytest.raises(AgentConfirmationError):
        MySqlAgentConfirmationStore().create(_confirmation("confirmed"), "token")


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.rowcount = 0
        self.statements = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql.startswith("SELECT") and self.row and (params[1] != self.row["user_id"] or params[2] != self.row["session_hash"]):
            self._selected = None
        elif sql.startswith("SELECT"):
            self._selected = self.row
        if sql.startswith("UPDATE"):
            self.rowcount = 1 if self.row and self.row.get("status") == "pending" else 0
            if self.rowcount:
                self.row["status"] = "confirmed"
        return self.rowcount
    def fetchone(self): return getattr(self, "_selected", self.row)


class _FakeConnection:
    def __init__(self, row): self.cursor_obj = _FakeCursor(row)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cursor_obj


def test_claim_is_single_use_and_rejects_expired_or_mismatched(monkeypatch) -> None:
    now = datetime.now()
    row = {"id": 3, "token_hash": "x", "user_id": 1, "session_hash": "s", "conversation_id": "c", "request_id": "r", "tool_name": "t", "payload_json": "{}", "status": "pending", "expires_at": now + timedelta(seconds=5), "used_at": None, "created_at": now}
    fake = _FakeConnection(row)
    monkeypatch.setattr(confirmation_store_module, "get_connection", lambda: fake)
    store = MySqlAgentConfirmationStore()
    assert store.claim(token="token", user_id=1, session_hash="s", now=now).status == "confirmed"
    assert store.claim(token="token", user_id=1, session_hash="s", now=now) is None
    assert store.claim(token="token", user_id=2, session_hash="s", now=now) is None
    assert store.claim(token="token", user_id=1, session_hash="wrong", now=now) is None


def test_claim_rejects_expired_and_cancel_only_pending(monkeypatch) -> None:
    now = datetime.now()
    row = {"id": 4, "token_hash": "x", "user_id": 1, "session_hash": "s", "conversation_id": "c", "request_id": "r", "tool_name": "t", "payload_json": "{}", "status": "pending", "expires_at": now - timedelta(seconds=1), "used_at": None, "created_at": now}
    fake = _FakeConnection(row)
    monkeypatch.setattr(confirmation_store_module, "get_connection", lambda: fake)
    store = MySqlAgentConfirmationStore()
    assert store.claim(token="token", user_id=1, session_hash="s", now=now) is None
    assert store.mark_cancelled(4, user_id=1) is True
    assert store.mark_cancelled(4, user_id=1) is False

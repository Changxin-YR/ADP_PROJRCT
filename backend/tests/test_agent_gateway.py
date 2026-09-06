from pathlib import Path

import pytest

from backend.config.settings import ConfigError, Settings
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_tool_registry import build_registry
import backend.layers.features.agent.agent_confirmation_store as confirmation_store_module
from datetime import datetime, timedelta, timezone

from backend.layers.features.agent.agent_gateway_service import AgentGatewayError, AgentGatewayService


class _MemoryConfirmationStore:
    def __init__(self):
        self.rows = {}
        self.next_id = 1
    def create(self, confirmation, token):
        row = AgentConfirmation(self.next_id, f"agent-confirmation:{self.next_id}", confirmation.token_hash, confirmation.user_id, confirmation.session_hash, confirmation.conversation_id, confirmation.request_id, confirmation.tool_name, confirmation.payload, "pending", confirmation.expires_at)
        self.next_id += 1
        self.rows[token] = row
        return row
    def find(self, *, token, user_id, session_hash):
        row = self.rows.get(token)
        if not row or row.user_id != user_id or row.session_hash != session_hash:
            return None
        return row
    def claim(self, *, token, user_id, session_hash, now=None):
        row = self.rows.get(token)
        if not row or row.status != "pending" or row.user_id != user_id or row.session_hash != session_hash or row.expires_at <= (now or datetime.now(timezone.utc).replace(tzinfo=None)):
            return None
        claimed = AgentConfirmation(row.id, row.idempotency_key, row.token_hash, row.user_id, row.session_hash, row.conversation_id, row.request_id, row.tool_name, row.payload, "confirmed", row.expires_at, datetime.now(timezone.utc).replace(tzinfo=None))
        self.rows[token] = claimed
        return claimed
    def mark_cancelled(self, confirmation_id, *, user_id):
        return False
    def mark_expired(self, *, now=None):
        return 0


def _gateway(executor=None):
    registry = build_registry()
    if executor:
        original = registry.get("master_data.create_record")
        replacement = type(original)(original.name, original.description, original.method, original.path_template, original.parameters, "master_data.manage", "write", executor)
        registry = type(registry)(tuple(replacement if item.name == original.name else item for item in registry.tools))
    settings = Settings.from_env({"APP_ENV": "test"})
    def idempotent(_settings, *, user_id, action_code, key, payload, operation):
        body, status = operation()
        return body, status
    return AgentGatewayService(settings, registry=registry, confirmations=_MemoryConfirmationStore(), idempotent=idempotent)


def _active_user(*permissions):
    return {"id": 7, "status": "active", "permissions": list(permissions), "roles": [{"code": "operator"}], "data_scopes": [{"scope_type": "area", "area_id": 1}]}


def test_agent_write_returns_pending_without_executing():
    called = []
    gateway = _gateway(lambda args, context: called.append(args) or {"id": 1})
    result = gateway.prepare_tool(_active_user("master_data.manage"), "master_data.create_record", {"resource": "ponds", "name": "一号塘"}, conversation_id="c-1", request_id="r-1")
    assert result["kind"] == "confirmation_required"
    assert result["confirmation"]["tool_name"] == "master_data.create_record"
    assert called == []


def test_agent_confirmation_is_single_use_and_rechecks_identity():
    gateway = _gateway(lambda args, context: {"record": args})
    user = _active_user("master_data.manage")
    pending = gateway.prepare_tool(user, "master_data.create_record", {"resource": "ponds"}, conversation_id="c-1", request_id="r-1")
    token = pending["confirmation"]["token"]
    assert gateway.confirm(user, token, request_id="r-2")["kind"] == "success"
    with pytest.raises(AgentGatewayError, match="确认令牌无效"):
        gateway.confirm(user, token, request_id="r-3")


def test_agent_human_only_permission_change_is_rejected():
    gateway = _gateway()
    result = gateway.prepare_tool(_active_user("auth.role.manage"), "admin.update_role_permissions", {"role_id": 1}, conversation_id="c-1", request_id="r-1")
    assert result["kind"] == "human_only"


def test_agent_permission_denial_fails_closed():
    gateway = _gateway()
    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(_active_user("production.view"), "master_data.create_record", {"resource": "ponds"}, conversation_id="c-1", request_id="r-1")
    assert exc.value.code == "FORBIDDEN"


def test_agent_data_scope_denial_fails_closed():
    gateway = _gateway()
    user = _active_user("master_data.view")
    user["data_scopes"] = []
    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(user, "master_data.list_records", {"resource": "ponds"}, conversation_id="c-1", request_id="r-1")
    assert exc.value.code == "DATA_SCOPE_REQUIRED"


def test_agent_read_uses_registered_executor():
    executor = lambda args, context: {"rows": [args["resource"]]}
    registry = build_registry(lambda _tool: executor)
    gateway = AgentGatewayService(Settings.from_env({"APP_ENV": "test"}), registry=registry, confirmations=_MemoryConfirmationStore())
    result = gateway.prepare_tool(_active_user("master_data.view"), "master_data.list_records", {"resource": "ponds"}, conversation_id="c-1", request_id="r-1")
    assert result["kind"] == "success"
    assert result["data"]["rows"] == ["ponds"]


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

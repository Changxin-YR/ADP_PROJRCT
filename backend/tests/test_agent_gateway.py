from pathlib import Path
import os

import pytest

from backend.config.settings import ConfigError, Settings
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_tool_registry import build_registry
import backend.layers.features.agent.agent_confirmation_store as confirmation_store_module
from datetime import datetime, timedelta, timezone
import sys
import types

from backend.layers.features.agent.agent_gateway_service import AgentGatewayError, AgentGatewayService
from backend.layers.features.agent.harness_sidecar import HarnessSidecar
from backend.layers.features.agent.harness_sidecar import _bounded_query_prompt, _runtime_environment
from backend.layers.common.db.query_guard import select_from, sql_identifier


class _MemoryConfirmationStore:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def create(self, confirmation, token):
        row = AgentConfirmation(
            self.next_id,
            f"agent-confirmation:{self.next_id}",
            confirmation.token_hash,
            confirmation.user_id,
            confirmation.session_hash,
            confirmation.conversation_id,
            confirmation.request_id,
            confirmation.tool_name,
            confirmation.payload,
            "pending",
            confirmation.expires_at,
        )
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
        claimed = AgentConfirmation(
            row.id,
            row.idempotency_key,
            row.token_hash,
            row.user_id,
            row.session_hash,
            row.conversation_id,
            row.request_id,
            row.tool_name,
            row.payload,
            "confirmed",
            row.expires_at,
            datetime.now(timezone.utc).replace(tzinfo=None),
        )
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
        replacement = type(original)(
            original.name,
            original.description,
            original.method,
            original.path_template,
            original.parameters,
            "master_data.manage",
            "write",
            executor,
            original.required_role,
            original.permission_namespace,
            original.permission_action,
            original.resource_argument,
            original.requires_data_scope,
        )
        registry = type(registry)(tuple(replacement if item.name == original.name else item for item in registry.tools))
    settings = Settings.from_env({"APP_ENV": "test"})

    def idempotent(_settings, *, user_id, action_code, key, payload, operation):
        body, status = operation()
        return body, status

    return AgentGatewayService(settings, registry=registry, confirmations=_MemoryConfirmationStore(), idempotent=idempotent)


def _active_user(*permissions, roles=("operator",), data_scopes=None):
    return {
        "id": 7,
        "status": "active",
        "permissions": list(permissions),
        "roles": [{"code": code} for code in roles],
        "data_scopes": [{"scope_type": "area", "area_id": 1}] if data_scopes is None else data_scopes,
    }


def test_agent_write_returns_pending_without_executing():
    called = []
    gateway = _gateway(lambda args, context: called.append(args) or {"id": 1})
    result = gateway.prepare_tool(
        _active_user("master_data.manage"),
        "master_data.create_record",
        {"resource": "ponds", "name": "一号塘"},
        conversation_id="c-1",
        request_id="r-1",
    )
    assert result["kind"] == "confirmation_required"
    assert result["confirmation"]["tool_name"] == "master_data.create_record"
    assert called == []


def test_agent_confirmation_is_single_use_and_rechecks_identity():
    gateway = _gateway(lambda args, context: {"record": args})
    user = _active_user("master_data.manage")
    pending = gateway.prepare_tool(
        user,
        "master_data.create_record",
        {"resource": "ponds"},
        conversation_id="c-1",
        request_id="r-1",
    )
    token = pending["confirmation"]["token"]
    assert gateway.confirm(user, token, request_id="r-2")["kind"] == "success"
    with pytest.raises(AgentGatewayError, match="确认令牌无效"):
        gateway.confirm(user, token, request_id="r-3")


def test_agent_audit_event_contains_authorization_and_business_trace_fields():
    events = []
    registry = build_registry(lambda _tool: lambda _args, _context: {"before": {"status": "active"}, "after": {"status": "inactive"}})
    gateway = AgentGatewayService(
        Settings.from_env({"APP_ENV": "test"}),
        registry=registry,
        confirmations=_MemoryConfirmationStore(),
        audit=events.append,
        idempotent=lambda _settings, **kwargs: kwargs["operation"](),
    )
    user = _active_user("master_data.manage")
    pending = gateway.prepare_tool(
        user,
        "master_data.create_record",
        {"resource": "ponds", "token": "secret"},
        conversation_id="c-trace",
        request_id="r-trace",
    )
    gateway.confirm(user, pending["confirmation"]["token"], request_id="r-trace-confirm")

    success = events[-1]
    assert success["authenticated_user_id"] == user["id"]
    assert success["intent"] == "master_data.create_record"
    assert success["required_permission"] == "master_data.manage"
    assert success["data_scope"] == user["data_scopes"]
    assert success["confirmation_id"] == pending["confirmation"]["id"]
    assert success["before"] == {"status": "active"}
    assert success["after"] == {"status": "inactive"}
    assert success["tool_arguments"]["token"] == "[REDACTED]"


def test_agent_admin_write_is_delegable_for_authorized_super_admin():
    gateway = _gateway()
    user = _active_user("auth.role.manage", roles=("super_admin",), data_scopes=[])
    result = gateway.prepare_tool(
        user,
        "admin.update_role_permissions",
        {"role_id": 1, "payload": {"permission_ids": [1, 2]}},
        conversation_id="c-1",
        request_id="r-1",
    )
    assert result["kind"] == "confirmation_required"
    assert result["confirmation"]["risk_level"] == "high"


def test_agent_admin_write_requires_super_admin_role():
    gateway = _gateway()
    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(
            _active_user("auth.role.manage"),
            "admin.update_role_permissions",
            {"role_id": 1, "payload": {"permission_ids": [1]}},
            conversation_id="c-1",
            request_id="r-1",
        )
    assert exc.value.code == "FORBIDDEN"


def test_agent_resource_specific_permission_is_accepted():
    executor = lambda args, context: {"rows": [args["resource"]]}
    registry = build_registry(lambda _tool: executor)
    gateway = AgentGatewayService(
        Settings.from_env({"APP_ENV": "test"}),
        registry=registry,
        confirmations=_MemoryConfirmationStore(),
    )
    result = gateway.prepare_tool(
        _active_user("production.feed_logs.view"),
        "production.list_records",
        {"resource": "feed-logs"},
        conversation_id="c-1",
        request_id="r-1",
    )
    assert result["kind"] == "success"
    assert result["data"]["rows"] == ["feed-logs"]


def test_agent_permission_denial_fails_closed():
    gateway = _gateway()
    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(
            _active_user("production.view"),
            "master_data.create_record",
            {"resource": "ponds"},
            conversation_id="c-1",
            request_id="r-1",
        )
    assert exc.value.code == "FORBIDDEN"


def test_agent_data_scope_denial_fails_closed():
    gateway = _gateway()
    user = _active_user("master_data.view", data_scopes=[])
    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(
            user,
            "master_data.list_records",
            {"resource": "ponds"},
            conversation_id="c-1",
            request_id="r-1",
        )
    assert exc.value.code == "DATA_SCOPE_REQUIRED"


def test_agent_read_uses_registered_executor():
    executor = lambda args, context: {"rows": [args["resource"]]}
    registry = build_registry(lambda _tool: executor)
    gateway = AgentGatewayService(
        Settings.from_env({"APP_ENV": "test"}),
        registry=registry,
        confirmations=_MemoryConfirmationStore(),
    )
    result = gateway.prepare_tool(
        _active_user("master_data.view"),
        "master_data.list_records",
        {"resource": "ponds"},
        conversation_id="c-1",
        request_id="r-1",
    )
    assert result["kind"] == "success"
    assert result["data"]["rows"] == ["ponds"]


def test_agent_registry_excludes_gateway_endpoints() -> None:
    registry = build_registry()
    assert all(not tool.path_template.startswith("/api/v1/agent/") for tool in registry.tools)


def test_agent_settings_defaults_and_sidecar_paths() -> None:
    settings = Settings.from_env({"APP_ENV": "test"})
    assert settings.agent_request_timeout_seconds == 30
    assert settings.agent_confirmation_ttl_seconds == 120
    assert settings.agent_sidecar_home
    assert settings.agent_sidecar_cwd
    assert settings.agent_sidecar_command == "dsh"
    assert settings.agent_sidecar_patch.endswith("agent-restricted.patch.yml")
    assert settings.agent_model_provider == "deepseek-official"
    assert settings.agent_model == "deepseek-v4-flash"
    assert settings.agent_model_max_tokens == 32768


def test_agent_restricted_patch_disables_host_native_modules() -> None:
    patch = (Path(__file__).parents[2] / "backend/layers/features/agent/agent-restricted.patch.yml").read_text()
    assert "- id: subprocess\n  disabled: true" in patch
    assert "- id: sandbox\n  disabled: true" in patch
    assert "- id: permission\n  disabled: true" in patch
    assert "- id: command-compact\n  disabled: true" in patch


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
    for field in (
        "token_hash char(64)",
        "user_id",
        "session_hash char(64)",
        "conversation_id varchar(64)",
        "request_id varchar(64)",
        "tool_name",
        "payload_json json",
        "expires_at datetime(6)",
        "used_at datetime(6)",
        "created_at datetime(6)",
        "current_timestamp(6)",
        "idx_agent_confirmations_user_status",
    ):
        assert field in sql
    assert "status enum('pending','confirmed','cancelled','expired')" in sql
    assert "unique" in sql
    assert "default 'pending'" in sql


def _confirmation(status="pending", expires_at=None):
    return AgentConfirmation(
        0,
        "key",
        "",
        1,
        "session",
        "conversation",
        "request",
        "tool",
        {},
        status,
        expires_at or datetime.now() + timedelta(minutes=1),
    )


def test_create_rejects_non_pending_confirmation() -> None:
    with pytest.raises(AgentConfirmationError):
        MySqlAgentConfirmationStore().create(_confirmation("confirmed"), "token")


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.rowcount = 0
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

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

    def fetchone(self):
        return getattr(self, "_selected", self.row)


class _FakeConnection:
    def __init__(self, row):
        self.cursor_obj = _FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj


def test_claim_is_single_use_and_rejects_expired_or_mismatched(monkeypatch) -> None:
    now = datetime.now()
    row = {
        "id": 3,
        "token_hash": "x",
        "user_id": 1,
        "session_hash": "s",
        "conversation_id": "c",
        "request_id": "r",
        "tool_name": "t",
        "payload_json": "{}",
        "status": "pending",
        "expires_at": now + timedelta(seconds=5),
        "used_at": None,
        "created_at": now,
    }
    fake = _FakeConnection(row)
    monkeypatch.setattr(confirmation_store_module, "get_connection", lambda: fake)
    store = MySqlAgentConfirmationStore()
    assert store.claim(token="token", user_id=1, session_hash="s", now=now).status == "confirmed"
    assert store.claim(token="token", user_id=1, session_hash="s", now=now) is None
    assert store.claim(token="token", user_id=2, session_hash="s", now=now) is None
    assert store.claim(token="token", user_id=1, session_hash="wrong", now=now) is None


def test_claim_rejects_expired_and_cancel_only_pending(monkeypatch) -> None:
    now = datetime.now()
    row = {
        "id": 4,
        "token_hash": "x",
        "user_id": 1,
        "session_hash": "s",
        "conversation_id": "c",
        "request_id": "r",
        "tool_name": "t",
        "payload_json": "{}",
        "status": "pending",
        "expires_at": now - timedelta(seconds=1),
        "used_at": None,
        "created_at": now,
    }
    fake = _FakeConnection(row)
    monkeypatch.setattr(confirmation_store_module, "get_connection", lambda: fake)
    store = MySqlAgentConfirmationStore()
    assert store.claim(token="token", user_id=1, session_hash="s", now=now) is None
    assert store.mark_cancelled(4, user_id=1) is True
    assert store.mark_cancelled(4, user_id=1) is False


def test_sidecar_passes_ephemeral_context_without_cookie(monkeypatch) -> None:
    captured = {}

    class FakeHarness:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            captured["environment"] = dict(os.environ)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def run(self, prompt, *, session_id):
            captured["prompt"] = prompt
            captured["session_id"] = session_id
            return {"kind": "assistant", "message": "ok"}

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=FakeHarness))
    result = HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run(
        "查询塘口",
        context={
            "conversation_id": "c-1",
            "request_id": "r-1",
            "gateway_url": "http://127.0.0.1",
            "context_token": "short-lived",
            "user_namespace": "session-a",
            "adp_session": "secret",
        },
    )
    assert result["kind"] == "assistant"
    assert "adp_session" not in captured["prompt"]
    assert captured["session_id"] == "session-a:c-1"
    assert captured["kwargs"]["env"]["ADP_AGENT_GATEWAY_URL"] == "http://127.0.0.1"
    assert captured["kwargs"]["env"]["ADP_AGENT_CONTEXT_TOKEN"] == "short-lived"
    assert "master_data.list_records" in captured["kwargs"]["env"]["ADP_AGENT_TOOL_CATALOG"]
    assert captured["kwargs"]["profile"] == "sdk"
    assert captured["kwargs"]["patches"]
    assert captured["environment"].get("MYSQL_PASSWORD") is None
    assert captured["environment"].get("FLASK_SECRET_KEY") is None


def test_sidecar_passes_configured_provider_and_model(monkeypatch) -> None:
    captured = {}

    class FakeHarness:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def run(self, prompt, *, session_id):
            return {"kind": "assistant", "message": "ok"}

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=FakeHarness))
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "AGENT_MODEL_PROVIDER": "deepseek-official",
            "AGENT_MODEL": "qwen-plus",
            "AGENT_MODEL_MAX_TOKENS": "32768",
        }
    )
    HarnessSidecar(settings).run("查询", context={"conversation_id": "c-1"})
    assert captured["kwargs"]["provider"] == "deepseek-official"
    assert captured["kwargs"]["model"] == "qwen-plus"
    assert captured["kwargs"]["max_tokens"] == 32768


def test_sidecar_maps_timeout(monkeypatch) -> None:
    class TimeoutHarness:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def run(self, *args, **kwargs):
            raise TimeoutError()

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=TimeoutHarness))
    with pytest.raises(AgentGatewayError) as exc:
        HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run("查询", context={"conversation_id": "c-1"})
    assert exc.value.code == "AGENT_TIMEOUT"


def test_sidecar_reuses_runtime_for_conversation_namespace(monkeypatch) -> None:
    created = []

    class FakeHarness:
        def __init__(self, **kwargs):
            created.append(self)
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def run(self, prompt, *, session_id):
            return {"kind": "assistant", "message": f"{prompt}:{session_id}"}

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=FakeHarness))
    sidecar = HarnessSidecar(Settings.from_env({"APP_ENV": "test"}))
    first = sidecar.run("第一轮", context={"conversation_id": "c-1", "user_namespace": "user-a"})
    second = sidecar.run("第二轮", context={"conversation_id": "c-1", "user_namespace": "user-a"})
    other = sidecar.run("另一用户", context={"conversation_id": "c-1", "user_namespace": "user-b"})

    assert len(created) == 2
    assert first["message"].endswith("user-a:c-1")
    assert second["message"].startswith("第二轮")
    assert other["message"].endswith("user-b:c-1")
    sidecar.close()
    assert all(item.closed for item in created)


def test_sidecar_adds_payload_free_latency_diagnostics(monkeypatch) -> None:
    class FakeHarness:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def run(self, *_args, **_kwargs):
            return {"kind": "assistant", "message": "ok"}

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=FakeHarness))
    result = HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run("查询", context={"conversation_id": "c-1"})
    diagnostics = result["diagnostics"]
    assert set(diagnostics) == {"request_received_ms", "harness_request_start_ms", "harness_response_ms", "total_ms"}
    assert all(isinstance(value, (int, float)) and value >= 0 for value in diagnostics.values())


def test_sidecar_rejects_missing_conversation_and_invalid_harness_result(monkeypatch) -> None:
    sidecar = HarnessSidecar(Settings.from_env({"APP_ENV": "test"}))
    with pytest.raises(AgentGatewayError) as missing:
        sidecar.run("查询", context={})
    assert missing.value.code == "VALIDATION_ERROR"

    class InvalidHarness:
        def __init__(self, **_kwargs):
            pass

        def run(self, *_args, **_kwargs):
            return object()

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=InvalidHarness))
    with pytest.raises(AgentGatewayError) as invalid:
        sidecar.run("查询", context={"conversation_id": "invalid-result"})
    assert invalid.value.code == "AGENT_PROTOCOL_ERROR"


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [(TimeoutError, "AGENT_TIMEOUT"), (ConnectionError, "AGENT_UNAVAILABLE"), (RuntimeError, "AGENT_UNAVAILABLE")],
)
def test_sidecar_maps_runtime_failures(monkeypatch, error_type, expected) -> None:
    class FailingHarness:
        def __init__(self, **_kwargs):
            pass

        def run(self, *_args, **_kwargs):
            raise error_type("failure")

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=FailingHarness))
    with pytest.raises(AgentGatewayError) as error:
        HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run("查询", context={"conversation_id": "failure"})
    assert error.value.code == expected


def test_sidecar_maps_protocol_failures_and_final_response_object(monkeypatch) -> None:
    class JsonRpcError(Exception):
        pass

    class ProtocolHarness:
        def __init__(self, **_kwargs):
            pass

        def run(self, *_args, **_kwargs):
            raise JsonRpcError("protocol failure")

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=ProtocolHarness))
    with pytest.raises(AgentGatewayError) as error:
        HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run("查询", context={"conversation_id": "protocol"})
    assert error.value.code == "AGENT_PROTOCOL_ERROR"

    class Response:
        final_response = "完成"
        session_id = "session-1"

    class ResponseHarness(ProtocolHarness):
        def run(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=ResponseHarness))
    result = HarnessSidecar(Settings.from_env({"APP_ENV": "test"})).run("查询", context={"conversation_id": "response"})
    assert result["message"] == "完成"
    assert result["session_id"] == "session-1"


def test_sidecar_bounds_uninspected_query_and_filters_runtime_environment(monkeypatch) -> None:
    bounded = _bounded_query_prompt("今天还有哪些鱼塘没有巡检？")
    assert "只调用一次 adp_query" in bounded
    assert "page_size: 20" in bounded
    assert _bounded_query_prompt("查询 3 号塘") == "查询 3 号塘"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-but-never-printed")
    monkeypatch.setenv("MYSQL_PASSWORD", "must-not-pass")
    environment = _runtime_environment(Settings.from_env({"APP_ENV": "test"}), {"gateway_url": "http://gateway", "context_token": "ctx"})
    assert environment["DEEPSEEK_API_KEY"] == "configured-but-never-printed"
    assert "MYSQL_PASSWORD" not in environment
    assert environment["ADP_AGENT_GATEWAY_URL"] == "http://gateway"


def test_query_guard_rejects_dynamic_identifiers() -> None:
    assert select_from("ponds", columns="id,name", suffix=" WHERE status=%s") == "SELECT id,name FROM ponds WHERE status=%s"
    with pytest.raises(ValueError):
        sql_identifier("ponds;DROP TABLE users")

"""HTTP 层验证：智能体写操作经脚本网关直接落库（不依赖子进程 / LLM）。

覆盖用户提出的核心诉求「智能体不能只能查，要能按自然语言直接增删改」：
登录 → /api/v1/agent/prepare（POST）→ 断言业务 store 真的被调用一次、返回 executed 人话。
"""

from __future__ import annotations

from typing import Any

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_gateway_service import AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import build_registry
from backend.layers.product.agent.agent_dispatch import dispatch_fixed_tool
from backend.layers.product.production import routes as production_routes
from fake_auth_store import FakeAuthStore


class _FakeProductionStore:
    """只实现被测调用路径；未实现的方法抛错，保证 fake 不会悄悄吞掉调用。"""

    def __init__(self, created: list[dict[str, Any]]) -> None:
        self.created = created

    def create_record(self, resource: str, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        self.created.append({"resource": resource, "payload": payload, "user_id": user_id})
        return {
            "id": 7, "code": payload.get("code"), "name": payload.get("name"),
            "status": "draft", "row_version": 1, "quantity": payload.get("quantity"),
            "weight_kg": payload.get("weight_kg"),
        }

    def __getattr__(self, name: str) -> Any:
        def _missing(*_args: Any, **_kwargs: Any) -> Any:
            raise DomainError("NOT_IMPLEMENTED", f"{name} 未在 fake store 中实现", 400)

        return _missing


def _route(kind: str, resource: str) -> Any:
    permissions = {
        "view": ["master_data.view", "production.view"],
        "manage": ["master_data.manage", "production.manage"],
        "verify": ["master_data.verify"],
    }[kind]
    return type(
        "Route",
        (),
        {
            "resource": resource,
            "resource_code": resource,
            "view_permission": permissions[0],
            "manage_permission": permissions[-1],
            "verify_permission": permissions[-1],
            "entry_requires_submit": False,
            "fields": {},
            "defaults": {},
            "option_fields": (),
            "payload_aliases": {},
        },
    )()


def _client(*, created: list[dict[str, Any]], monkeypatch: Any, idempotency_keys: list[str] | None = None) -> Any:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000901", login_name="agent-writer", password="Correct9!", status="active")
    account["permissions"] = ["master_data.view", "master_data.manage", "production.view", "production.manage"]
    account["data_scopes"] = [{"scope_type": "area", "area_id": 1}]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "agent-write-test", "CSRF_SECRET_KEY": "agent-write-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false", "AGENT_WRITE_MODE": "direct",
    })
    store = _FakeProductionStore(created)
    gateway = AgentGatewayService(
        settings,
        registry=build_registry(lambda tool: lambda arguments, context: dispatch_fixed_tool(tool, arguments, context, settings)),
        confirmations=MySqlAgentConfirmationStore(settings),
    )
    # 两层幂等表都要落 MySQL；本用例只验证 agent 执行链，替换成等价的「执行一次」。
    def _idempotent(_settings: Any, **kwargs: Any) -> tuple[dict[str, Any], int]:
        if idempotency_keys is not None:
            idempotency_keys.append(str(kwargs["key"]))
        return kwargs["operation"]()[0], 200

    gateway._idempotent = _idempotent
    monkeypatch.setattr(production_routes, "execute_idempotent", lambda _s, **kwargs: (kwargs["operation"]()[0], kwargs["operation"]()[1]))
    client = create_app(settings, store=auth, production_store=store, agent_gateway=gateway).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "agent-writer", "password": "Correct9!"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.get_json()
    return client


def test_agent_prepare_forwards_client_idempotency_key_to_write_executor(monkeypatch: Any) -> None:
    created: list[dict[str, Any]] = []
    keys: list[str] = []
    client = _client(created=created, monkeypatch=monkeypatch, idempotency_keys=keys)
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    response = client.post(
        "/api/v1/agent/prepare",
        json={
            "operation": "api.production_create_post_api_v1_production_resource",
            "arguments": {"resource": "feed-logs", "payload": {
                "code": "FL-IDEMPOTENCY-1", "name": "幂等验证", "pond_id": 3,
                "batch_id": 1, "material_id": 1, "quantity": 20,
            }},
            "conversation_id": "c-http-idempotency",
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "agent-http-key-1"},
    )

    assert response.status_code == 200, response.get_json()
    assert created
    assert keys == ["agent-http-key-1"]


def test_agent_prepare_executes_a_write_and_returns_plain_language(monkeypatch: Any) -> None:
    created: list[dict[str, Any]] = []
    client = _client(created=created, monkeypatch=monkeypatch)
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    response = client.post(
        "/api/v1/agent/prepare",
        json={
            "operation": "api.production_create_post_api_v1_production_resource",
            "arguments": {"resource": "feed-logs", "payload": {
                "code": "FL-HTTP-1", "name": "HTTP 落库验证", "pond_id": 3,
                "batch_id": 1, "material_id": 1, "quantity": 20,
            }},
            "conversation_id": "c-http-1",
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "http-write-1"},
    )

    assert response.status_code == 200, response.get_json()
    body = response.get_json()["data"]
    assert body["kind"] == "executed"
    assert body["execution"]["title"] == "新增投喂记录"
    assert "投喂记录" in body["message"]
    assert created, "写操作必须真的落到业务 store"
    assert all(token not in body["message"] for token in ("api.", "POST", "{", "request_id", "tool_name"))


def test_agent_prepare_rejects_unknown_operation_without_touching_business_data(monkeypatch: Any) -> None:
    created: list[dict[str, Any]] = []
    client = _client(created=created, monkeypatch=monkeypatch)
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    response = client.post(
        "/api/v1/agent/prepare",
        json={"operation": "not.a.registered.tool", "arguments": {}, "conversation_id": "c-http-2"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "TOOL_NOT_FOUND"
    assert created == []

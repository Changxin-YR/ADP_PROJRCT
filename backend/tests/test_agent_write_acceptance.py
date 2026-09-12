"""智能体写操作的端到端验收 + 防回归。

线上真事故（2026-09-11 21:10）：智能体用只有 `X-Agent-Context` 的回调给成本模块写数据，
全部返回 403 CSRF_INVALID —— 因为成本路由直接调 `validate_csrf_token`，绕过了
`require_csrf()` 里「带 Authorization: Bearer 就放行」的旁路（内层业务调用正是靠这个头
继承登录者身份）。后果：智能体“查询没问题、写入全失败”。

本文件两层保障：
1. 回调形态（无 Cookie / 无 CSRF 头）能到达网关，且高风险费用写入不能绕过确认；
2. 全量扫描：所有 mutating 路由都必须走 `require_csrf()`，不许再直接调 `validate_csrf_token`。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from backend.layers.product.cost import enterprise_routes as enterprise_routes_module
from backend.layers.product.cost import routes as cost_routes_module
from backend.layers.features.agent.agent_contracts import AgentConfirmation
from backend.layers.features.agent.agent_gateway_service import AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import build_registry
from backend.layers.product.agent.agent_dispatch import dispatch_fixed_tool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DIRECT_CSRF_CALL = re.compile(r"validate_csrf_token\s*\(")
# 允许直接调用 validate_csrf_token 的地方：定义它的模块、以及共享旁路自身。
ALLOWED_FILES = {
    BACKEND_ROOT / "layers/common/security/csrf.py",
    BACKEND_ROOT / "layers/common/http/request_helpers.py",
}


def _python_sources() -> list[Path]:
    return [
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path not in ALLOWED_FILES
    ]


def test_no_route_bypasses_the_bearer_aware_csrf_helper() -> None:
    """任何直接调 validate_csrf_token 的路由都会让智能体写入 403；这条断言守住它。"""
    offenders: list[str] = []
    for path in _python_sources():
        if path.name.startswith("test_") or "_repro" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        if DIRECT_CSRF_CALL.search(text):
            offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == [], (
        "这些文件绕过了 require_csrf() 的 Bearer 旁路，智能体写入会被 403 CSRF_INVALID："
        + ", ".join(offenders)
    )


def test_cost_writes_use_the_shared_csrf_helper() -> None:
    """成本模块（本次事故现场）逐个写端点都要走共用入口。"""
    for module in (cost_routes_module, enterprise_routes_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "validate_csrf_token" not in source
        assert source.count("require_csrf()") >= 1


@pytest.fixture
def cost_callback_client() -> Any:
    """真 Flask + FakeAuthStore：登录一次拿到会话，然后只用 context 头回调。"""
    import sys

    sys.path.insert(0, str(BACKEND_ROOT / "tests"))
    from backend.app import create_app
    from backend.config.settings import Settings
    from backend.layers.product.agent.routes import _issue_context
    from fake_auth_store import FakeAuthStore

    class FakeCostStore:
        def __init__(self) -> None:
            self.expenses: list[dict[str, Any]] = []

        def create_expense(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
            self.expenses.append(payload)
            return {"id": len(self.expenses), "code": payload.get("code", "EXP-1"), "status": "draft", "row_version": 1}

        def __getattr__(self, name: str) -> Any:
            def _missing(*_a: Any, **_k: Any) -> Any:
                raise AssertionError(f"{name} 未在 fake cost store 中实现")

            return _missing

    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000966", login_name="cb-accept", password="Correct9!", status="active")
    account["permissions"] = ["cost.view", "cost.entry.manage"]
    account["data_scopes"] = [{"scope_type": "area", "area_id": 1}]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "cb-accept", "CSRF_SECRET_KEY": "cb-accept-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false", "AGENT_WRITE_MODE": "direct",
    })
    store = FakeCostStore()
    gateway = AgentGatewayService(
        settings,
        registry=build_registry(lambda tool: lambda arguments, context: dispatch_fixed_tool(tool, arguments, context, settings)),
        confirmations=_MemoryConfirmations(),
    )
    gateway.open_confirmation_work_item = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    client = create_app(settings, store=auth, cost_store=store, agent_gateway=gateway).test_client()
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    login = client.post("/api/v1/auth/login", json={"identifier": "cb-accept", "password": "Correct9!"},
                        headers={"X-CSRF-Token": csrf})
    assert login.status_code == 200, login.get_json()
    session_token = client.get_cookie("adp_session").value

    return _Callback(client.application.test_client(), settings, _issue_context(settings, session_token), store)


class _MemoryConfirmations:
    def __init__(self) -> None:
        self.rows: dict[str, AgentConfirmation] = {}
        self.next_id = 1

    def create(self, confirmation: AgentConfirmation, token: str) -> AgentConfirmation:
        saved = AgentConfirmation(**{**confirmation.__dict__, "id": self.next_id})
        self.next_id += 1
        self.rows[token] = saved
        return saved

    def find(self, *, token: str, user_id: int, session_hash: str) -> AgentConfirmation | None:
        return self.rows.get(token)

    def claim(self, *, token: str, user_id: int, session_hash: str, now: Any = None) -> AgentConfirmation | None:
        return None

    def mark_cancelled(self, confirmation_id: int, *, user_id: int) -> bool:
        return True

    def mark_failed(self, confirmation_id: int, *, user_id: int) -> bool:
        return True

    def mark_expired(self, *, now: Any = None, user_id: int | None = None) -> list[int]:
        return []


class _Callback:
    def __init__(self, client: Any, settings: Any, context_token: str, store: Any) -> None:
        self.client = client
        self.settings = settings
        self.context_token = context_token
        self.store = store

    def prepare(self, operation: str, arguments: dict[str, Any]) -> Any:
        return self.client.post(
            "/api/v1/agent/prepare",
            json={"operation": operation, "arguments": arguments, "conversation_id": "accept-1"},
            # 这就是 DSH 插件 callGateway 的真实形态：没有 Cookie，也没有 CSRF 头
            headers={"Content-Type": "application/json", "X-Agent-Context": self.context_token},
        )


# 必填来自 cost_enterprise_validation.expense_payload：
# category_code / amount / occurred_on / period_start / period_end / source_type / source_ref
VALID_EXPENSE = {
    "category_code": "electricity",
    "amount": "166.33",
    "occurred_on": "2026-06-15",
    "period_start": "2026-06-01",
    "period_end": "2026-06-30",
    "cost_nature": "public",
    "source_type": "manual",
    "source_ref": "AGENT-ACCEPT-1",
    "farm_id": 1,
}


def test_agent_callback_cannot_bypass_confirmation_for_cost_expense(cost_callback_client: _Callback) -> None:
    response = cost_callback_client.prepare("api.cost_create_expense_post_api_v1_cost_expenses", {"payload": dict(VALID_EXPENSE)})

    body = response.get_json()
    assert response.status_code == 200, body
    assert body["data"]["kind"] == "confirmation_required", body
    assert cost_callback_client.store.expenses == []


def test_agent_callback_write_still_rejects_a_forged_context_token(cost_callback_client: _Callback) -> None:
    response = cost_callback_client.client.post(
        "/api/v1/agent/prepare",
        json={"operation": "api.cost_create_expense_post_api_v1_cost_expenses", "arguments": {"payload": dict(VALID_EXPENSE)}},
        headers={"Content-Type": "application/json", "X-Agent-Context": "forged-token"},
    )

    assert response.status_code in {401, 403}, response.get_json()
    assert cost_callback_client.store.expenses == []

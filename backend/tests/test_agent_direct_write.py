"""直连写模式：智能体不再「只读」，按登录者权限直接落地增删改。"""
from __future__ import annotations

from typing import Any

import pytest

from backend.config.settings import ConfigError, Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError, AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import AgentTool, AgentToolRegistry, build_registry
from backend.layers.features.agent.agent_humanize import action_title, change_rows, resource_code, summarize, target_label

TECHNICAL_TOKENS = (
    "api.", "adp_query", "adp_mutation", "POST", "PATCH", "DELETE", "{", "}", "request_id",
    "session_id", "tool_name", "status_code", "expected_version", "row_version", "payload",
)


class _MemoryConfirmations:
    def __init__(self) -> None:
        self.rows: dict[str, Any] = {}

    def create(self, confirmation: Any, token: str) -> Any:
        self.rows[token] = confirmation
        return confirmation

    def find(self, *, token: str, user_id: int, session_hash: str) -> Any:
        return None

    def claim(self, *, token: str, user_id: int, session_hash: str) -> Any:
        return None


def _tool(name: str, *, method: str, path: str, permission: str, risk: str, execute: Any = None) -> AgentTool:
    return AgentTool(
        name=name,
        description="测试工具",
        method=method,
        path_template=path,
        parameters={"payload": {"type": "object", "required": True}},
        required_permission=permission,
        risk=risk,
        execute=execute,
        requires_data_scope=False,
    )


def _gateway(tools: tuple[AgentTool, ...], *, mode: str = "direct", idempotent: Any = None) -> AgentGatewayService:
    settings = Settings.from_env({"APP_ENV": "test", "AGENT_WRITE_MODE": mode})
    return AgentGatewayService(
        settings,
        registry=AgentToolRegistry(tools),
        confirmations=_MemoryConfirmations(),
        idempotent=idempotent or (lambda _settings, **kwargs: kwargs["operation"]()),
    )


def _user(*permissions: str) -> dict[str, Any]:
    return {"id": 9, "status": "active", "permissions": list(permissions), "roles": [{"code": "breeder"}], "data_scopes": []}


def test_direct_mode_executes_the_write_once_and_returns_plain_language() -> None:
    calls: list[dict[str, Any]] = []

    def execute(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        calls.append(arguments)
        return {"record": {"id": 12, "name": "一号塘", "code": "P-12"}}

    tool = _tool("master_data.create_record", method="POST", path="/api/v1/master-data/{resource}", permission="master_data.manage", risk="write", execute=execute)
    result = _gateway((tool,)).prepare_tool(
        _user("master_data.manage"),
        tool.name,
        {"resource": "ponds", "name": "一号塘", "capacity_mu": 12},
        conversation_id="c-1",
        request_id="r-1",
    )

    assert result["kind"] == "executed"
    assert len(calls) == 1
    assert result["message"] == "新增塘口档案完成：「一号塘」，编码 P-12。"
    assert result["execution"]["title"] == "新增塘口档案"
    assert result["execution"]["rows_changed"] == 1
    assert all(token not in result["message"] for token in TECHNICAL_TOKENS)


def test_direct_mode_denies_write_without_permission_and_never_executes() -> None:
    calls: list[dict[str, Any]] = []
    tool = _tool(
        "master_data.create_record", method="POST", path="/api/v1/master-data/{resource}",
        permission="master_data.manage", risk="write", execute=lambda arguments, context: calls.append(arguments),
    )

    with pytest.raises(AgentGatewayError) as exc:
        _gateway((tool,)).prepare_tool(
            _user("master_data.view"),
            tool.name,
            {"resource": "ponds", "name": "一号塘"},
            conversation_id="c-1",
            request_id="r-1",
        )

    assert exc.value.code == "FORBIDDEN"
    assert calls == []


def test_direct_mode_keeps_human_only_operations_delegation_free() -> None:
    tool = _tool("api.auth_login_post_api_v1_auth_login", method="POST", path="/api/v1/auth/login", permission="", risk="human_only")
    result = _gateway((tool,)).prepare_tool(_user(), tool.name, {"payload": {}}, conversation_id="c-1", request_id="r-1")

    assert result["kind"] == "human_only"
    assert "人工" in result["message"] or "本人" in result["message"]


def test_confirm_mode_still_waits_for_the_user_click() -> None:
    calls: list[dict[str, Any]] = []
    tool = _tool(
        "master_data.create_record", method="POST", path="/api/v1/master-data/{resource}",
        permission="master_data.manage", risk="write", execute=lambda arguments, context: calls.append(arguments) or {"record": {"id": 1}},
    )
    gateway = _gateway((tool,), mode="confirm")

    result = gateway.prepare_tool(
        _user("master_data.manage"),
        tool.name,
        {"resource": "ponds", "name": "一号塘"},
        conversation_id="c-1",
        request_id="r-1",
    )

    assert result["kind"] == "confirmation_required"
    assert calls == []
    assert result["confirmation"]["summary"] == "新增塘口档案"
    assert result["confirmation"]["changes"][0] == {"label": "名称", "value": "一号塘"}


def test_direct_mode_hides_framework_failures_behind_business_wording() -> None:
    def boom(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("connection reset by peer")

    tool = _tool(
        "production.create", method="POST", path="/api/v1/production/{resource}",
        permission="production.manage", risk="write", execute=boom,
    )

    with pytest.raises(AgentGatewayError) as exc:
        _gateway((tool,)).prepare_tool(
            _user("production.manage"),
            tool.name,
            {"resource": "feed-logs", "payload": {"pond_id": 2}},
            conversation_id="c-1",
            request_id="r-1",
        )

    assert exc.value.status == 400
    assert "没做成" in exc.value.message
    assert "connection reset by peer" not in exc.value.message
    assert "Traceback" not in exc.value.message


def test_direct_mode_replays_the_same_idempotency_key_for_one_request() -> None:
    seen_keys: list[str] = []

    def idempotent(_settings: Any, **kwargs: Any) -> tuple[dict[str, Any], int]:
        seen_keys.append(str(kwargs["key"]))
        return kwargs["operation"]()

    tool = _tool(
        "master_data.create_record", method="POST", path="/api/v1/master-data/{resource}",
        permission="master_data.manage", risk="write", execute=lambda arguments, context: {"record": {"id": 3}},
    )
    gateway = _gateway((tool,), idempotent=idempotent)

    for _ in range(2):
        gateway.prepare_tool(
            _user("master_data.manage"),
            tool.name,
            {"resource": "ponds", "name": "一号塘"},
            conversation_id="c-1",
            request_id="r-7",
        )

    assert seen_keys == ["agent-direct:master_data.create_record:r-7"] * 2


def test_write_mode_setting_is_bounded() -> None:
    assert Settings.from_env({"APP_ENV": "test"}).agent_write_mode == "direct"
    assert Settings.from_env({"APP_ENV": "test", "AGENT_WRITE_MODE": "confirm"}).agent_write_mode == "confirm"
    with pytest.raises(ConfigError):
        Settings.from_env({"APP_ENV": "test", "AGENT_WRITE_MODE": "sometimes"})


def test_humanize_turns_operations_into_business_chinese() -> None:
    assert action_title("POST", "/api/v1/production/{resource}", resource="feed-logs") == "新增投喂记录"
    assert action_title("DELETE", "/api/v1/master-data/{resource}/{record_id}", resource="ponds") == "删除塘口档案"
    assert action_title("POST", "/api/v1/master-data/ponds/{pond_id}/status-changes") == "申请塘口状态变更"
    assert resource_code("/api/v1/production/{resource}", {"resource": "harvests"}) == "harvests"
    assert change_rows({"resource": "ponds", "payload": {"name": "二号塘", "capacity_mu": 8}}) == [
        {"label": "名称", "value": "二号塘"},
        {"label": "养殖面积（亩）", "value": "8"},
        {"label": "对象类型", "value": "塘口档案"},
    ]


def test_humanize_names_the_affected_object_for_the_confirmation_card() -> None:
    assert target_label("/api/v1/master-data/{resource}", {"resource": "ponds", "payload": {"name": "一号塘"}}) == "塘口档案 一号塘"
    assert target_label("/api/v1/production/{resource}", {"resource": "feed-logs", "payload": {"pond_code": "TK-001"}}) == "投喂记录 TK-001"
    # 拿不到具体对象时退回资源名，而不是把动作名重复一遍。
    assert target_label("/api/v1/production/{resource}", {"resource": "harvests"}) == "出塘记录"


def test_humanize_never_leaks_json_or_machine_keys_in_prose() -> None:
    prose = summarize({"record": {"name": "一号塘", "code": "P-12"}}, title="新增塘口档案")
    assert prose == "新增塘口档案完成：「一号塘」，编码 P-12。"
    assert summarize({"items": [], "total": 0}, title="查询投喂记录") == "查询投喂记录完成，没有符合条件的记录。"
    for token in TECHNICAL_TOKENS:
        assert token not in prose

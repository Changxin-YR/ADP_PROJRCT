"""确认闸门 → 统一待办（人在环上）的集成测试。

分两层，避免"假绿"：
1. **模块级 SQL 断言**：用假连接检查写出的语句与参数，覆盖幂等守卫与失败降级。
2. **网关级挂点断言**：用 spy 替换三个 hook，确认"建确认→开待办""执行成功→完成待办"
   "执行失败→取消待办"三条路径真的被触发（包括失败路径仍收口）。
"""
from __future__ import annotations

from dataclasses import replace

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import backend.layers.features.agent.agent_confirmation_work_item as work_item_module
import backend.layers.features.agent.agent_gateway_service as gateway_module
from backend.layers.features.agent.agent_confirmation_work_item import (
    cancel_confirmation_work_item,
    close_expired_confirmation_work_items,
    complete_confirmation_work_item,
    open_confirmation_work_item,
    source_key_of,
)
from backend.layers.features.agent.agent_contracts import AgentConfirmation
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_tool_registry import build_registry


class _Cursor:
    def __init__(self, log: list[tuple[str, tuple[Any, ...]]], lastrowid: int = 7, rows: list[dict] | None = None):
        self.log = log
        self.lastrowid = lastrowid
        self.rows = rows if rows is not None else []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.log.append((" ".join(sql.split()), params))
        self.rowcount = 1 if sql.strip().upper().startswith("UPDATE") else 0

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, log: list[tuple[str, tuple[Any, ...]]], *, explode: bool = False, rows: list[dict] | None = None):
        self.log, self.explode, self.rows = log, explode, rows

    def __enter__(self):
        if self.explode:
            raise RuntimeError("db down")
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _Cursor(self.log, rows=self.rows)


def _real_tool(*, admin: bool = False):
    """用真实注册表里的工具对象：结构由 OpenAPI 推导，跟生产完全一致，避免手写 fake 漏字段。"""
    tools = build_registry().tools
    if admin:
        return next(t for t in tools if t.path_template.startswith("/api/v1/admin") and t.method == "POST")
    return next(t for t in tools if t.path_template.endswith("/api/v1/sales/orders") and t.method == "POST")


def _write_sales_tool(executor=None):
    """真实销售建单工具（结构来自 OpenAPI），仅把执行器挂上，风险等级本就是 write。"""
    return replace(
        _real_tool(),
        execute=executor or (lambda arguments, context: ({"record": {"id": 1, "code": "MT2609-SO-01"}}, 200)),
    )


def _confirmation(confirmation_id: int = 42, payload: dict | None = None, expires_at=None) -> AgentConfirmation:
    """用真实 AgentConfirmation（冻结 dataclass），字段与生产一致。"""
    return AgentConfirmation(
        id=confirmation_id,
        idempotency_key=f"agent-confirmation:{confirmation_id}",
        token_hash="hash",
        user_id=11,
        session_hash="session-hash-1",
        conversation_id="conv-1",
        request_id="req-1",
        tool_name="api.sales_create_order_post_api_v1_sales_orders",
        payload=payload or {"quantity": 450},
        status="pending",
        expires_at=expires_at or datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=120),
    )

def _user(permissions: list[str] | None = None) -> dict[str, Any]:
    """与网关约定的最小用户上下文：会话哈希 + 未过期作用域 + 权限码。"""
    return {
        "id": 11,
        "name": "验收员",
        "status": "active",
        "roles": [{"code": "breed_manager"}],
        "_session_hash": "session-hash-1",
        "permissions": ["sales.manage"] if permissions is None else permissions,
        "data_scopes": [{"scope_type": "farm", "status": "active", "organization_id": 1}],
    }


USER = _user()


def test_source_key_is_deterministic() -> None:
    assert source_key_of(42) == "agent:confirmation:42"
    assert source_key_of("42") == "agent:confirmation:42"


def test_open_writes_claimed_work_item_bound_to_the_requester(monkeypatch) -> None:
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    work_item_id = open_confirmation_work_item(None, confirmation=_confirmation(), tool=_write_sales_tool(), user=USER)

    assert work_item_id == 7
    assert len(log) == 1
    sql, params = log[0]
    assert "INSERT INTO work_items" in sql
    # 待办指派给发起确认的本人，且初始为 claimed（他自己持有，等待确认动作）
    assert "'claimed'" in sql
    assert params[0] == 11 and params[10] == 11
    assert params[5] == source_key_of(42) and params[6] == source_key_of(42)
    assert "agent:confirmation:42" in params[5]
    assert params[9] == "high"


def test_open_marks_admin_tools_as_high_priority(monkeypatch) -> None:
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    open_confirmation_work_item(None, confirmation=_confirmation(), tool=replace(_real_tool(admin=True), risk="write"), user=USER)
    assert log[0][1][9] == "high"


def test_open_degrades_silently_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection([], explode=True))
    assert open_confirmation_work_item(None, confirmation=_confirmation(), tool=_write_sales_tool(), user=USER) is None


def test_open_ignores_unsaved_confirmation_without_id(monkeypatch) -> None:
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    assert open_confirmation_work_item(None, confirmation=_confirmation(confirmation_id=0), tool=_write_sales_tool(), user=USER) is None
    assert log == []


@pytest.mark.parametrize("settle, expected", [
    (complete_confirmation_work_item, ("status='completed'", "completed_by")),
    (cancel_confirmation_work_item, ("status='cancelled'", "cancelled_by")),
])
def test_settle_guards_on_open_statuses_only(monkeypatch, settle, expected) -> None:
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    settle(None, confirmation_id=42, user_id=11)

    sql, params = log[0]
    assert "UPDATE work_items" in sql
    assert expected[0] in sql and expected[1] in sql
    assert "('pending','claimed','in_progress','escalated')" in sql
    assert "'completed','cancelled'" not in sql.split("WHERE")[0].replace("status IN", "")  # 不是在 OPEN 列表里
    assert params == (11, source_key_of(42))


def test_settle_is_idempotent_by_construction(monkeypatch) -> None:
    """重复收口不报错：由 WHERE status IN (...) 守卫，第二次执行影响 0 行。"""
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    complete_confirmation_work_item(None, confirmation_id=42, user_id=11)
    complete_confirmation_work_item(None, confirmation_id=42, user_id=11)
    assert len(log) == 2
    assert log[0][0] == log[1][0]


def test_settle_degrades_silently_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection([], explode=True))
    complete_confirmation_work_item(None, confirmation_id=42, user_id=11)  # 不抛
    cancel_confirmation_work_item(None, confirmation_id=42, user_id=11)    # 不抛


def _spy_gateway(monkeypatch, calls: list[tuple[str, dict[str, Any]]]):
    """用 spy 替换三个 hook，返回可用的网关；执行器由外部注入。"""
    for name in ("open_confirmation_work_item", "complete_confirmation_work_item", "cancel_confirmation_work_item"):
        monkeypatch.setattr(
            gateway_module,
            name,
            lambda *a, _name=name, **k: calls.append((_name, k)) or (7 if _name == "open_confirmation_work_item" else None),
        )


class _Registry:
    def __init__(self, tool):
        self.tool = tool

    def require(self, name):
        return self.tool


class _Settings:
    agent_confirmation_ttl_seconds = 120
    agent_write_mode = "confirm"  # 待办确认流程只在回退模式下产生


def _prepare(gateway, tool):
    return gateway.prepare_tool(
        _user(),
        tool.name,
        {"quantity": 450},
        request_id="req-1",
        conversation_id="conv-1",
    )


def _gateway_for(tool, *, execute=None, registry=None):
    gateway = gateway_module.AgentGatewayService.__new__(gateway_module.AgentGatewayService)
    gateway.settings = _Settings()
    gateway.registry = registry or _Registry(tool)
    gateway.audit = None
    gateway._idempotent = lambda *a, **k: k["operation"]()
    gateway.confirmations = _ConfirmationStore()
    return gateway


class _ConfirmationStore:
    def __init__(self):
        self.saved = {}

    def create(self, confirmation, token):
        saved = replace(confirmation, id=42, status="pending")
        self.saved[token] = saved
        return saved

    def find(self, *, token, user_id, session_hash):
        return self.saved.get(token)

    def claim(self, *, token, user_id, session_hash, now=None):
        return self.saved.get(token)

    def mark_failed(self, confirmation_id, *, user_id):
        self.failed = confirmation_id


def test_prepare_opens_a_work_item_for_the_requester(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    _spy_gateway(monkeypatch, calls)
    tool = _write_sales_tool()
    gateway = _gateway_for(tool)

    result = _prepare(gateway, tool)

    assert result["kind"] == "confirmation_required"
    assert [name for name, _ in calls] == ["open_confirmation_work_item"]
    assert calls[0][1]["user"]["id"] == 11
    assert calls[0][1]["tool"] is tool


def test_confirm_completes_the_work_item(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    _spy_gateway(monkeypatch, calls)
    tool = _write_sales_tool()
    gateway = _gateway_for(tool)
    prepared = _prepare(gateway, tool)
    token = prepared["confirmation"]["token"]

    gateway.confirm(
        _user(),
        token,
        request_id="req-2",
    )

    names = [name for name, _ in calls]
    assert names == ["open_confirmation_work_item", "complete_confirmation_work_item"]
    assert calls[-1][1]["confirmation_id"] == 42


def test_failed_business_execution_cancels_the_work_item(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    _spy_gateway(monkeypatch, calls)

    def boom(arguments, context):
        raise AgentGatewayError("BUSINESS_ERROR", "业务执行失败", 400)

    tool = _write_sales_tool(boom)
    gateway = _gateway_for(tool)
    prepared = _prepare(gateway, tool)
    token = prepared["confirmation"]["token"]

    with pytest.raises(AgentGatewayError):
        gateway.confirm(
            _user(),
            token,
            request_id="req-3",
        )

    names = [name for name, _ in calls]
    assert names == ["open_confirmation_work_item", "cancel_confirmation_work_item"]
    assert calls[-1][1]["confirmation_id"] == 42


def test_denied_request_does_not_open_a_work_item(monkeypatch) -> None:
    """被拒的请求不应该留下待办：没有确认就没有待办。

    这里用"启用但无有效数据范围"触发真实拒绝（DATA_SCOPE_REQUIRED），
    而不是构造假权限：超管会跳过权限校验，用空 permissions 断言会变成永远通过的空测试。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    _spy_gateway(monkeypatch, calls)
    tool = _write_sales_tool()
    gateway = _gateway_for(tool)
    blocked = {**_user(), "data_scopes": []}

    with pytest.raises(Exception) as error:
        gateway.prepare_tool(blocked, tool.name, {"quantity": 450}, request_id="req-4", conversation_id="conv-1")

    assert getattr(error.value, "code", None) == "DATA_SCOPE_REQUIRED"
    assert calls == []

def test_close_expired_confirmation_work_items_settles_each_id(monkeypatch) -> None:
    """到期确认必须级联收口待办，否则待办会永远停在 claimed。"""
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))

    closed = close_expired_confirmation_work_items(None, confirmation_ids=[42, 43], user_id=11)

    assert closed == 2
    assert len(log) == 2
    for sql, params in log:
        assert "status='cancelled'" in sql
        assert params[0] == 11
    assert source_key_of(42) in log[0][1][-1]
    assert source_key_of(43) in log[1][1][-1]


def test_close_expired_tolerates_empty_input(monkeypatch) -> None:
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(work_item_module, "get_connection", lambda *a, **k: _Connection(log))
    assert close_expired_confirmation_work_items(None, confirmation_ids=[], user_id=11) == 0
    assert log == []


def test_store_mark_expired_returns_ids_and_updates_only_those(monkeypatch) -> None:
    """store 必须返回被处理的确认 ID（否则调用方无法级联），并只更新自己查到的那些。"""
    import backend.layers.features.agent.agent_confirmation_store as store_module

    log: list[tuple[str, tuple[Any, ...]]] = []
    rows = [{"id": 42}, {"id": 43}]
    monkeypatch.setattr(store_module, "get_connection", lambda *a, **k: _Connection(log, rows=rows))

    expired = store_module.MySqlAgentConfirmationStore().mark_expired(user_id=11)

    assert expired == [42, 43]
    select_sql, select_params = log[0]
    assert "SELECT id FROM agent_confirmations" in select_sql
    assert "status='pending'" in select_sql and "user_id=%s" in select_sql
    assert select_params[-1] == 11
    update_sql, update_params = log[1]
    assert "SET status='expired'" in update_sql and "IN (%s,%s)" in update_sql
    assert update_params == (42, 43)


def test_store_mark_expired_skips_update_when_nothing_is_due(monkeypatch) -> None:
    import backend.layers.features.agent.agent_confirmation_store as store_module

    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(store_module, "get_connection", lambda *a, **k: _Connection(log, rows=[]))

    assert store_module.MySqlAgentConfirmationStore().mark_expired() == []
    assert len(log) == 1  # 只有 SELECT，没有多余 UPDATE


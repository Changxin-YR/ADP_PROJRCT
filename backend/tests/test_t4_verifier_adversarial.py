"""t4 终局对抗性验证（verifier 独立编写，只验证不改产品代码）。

A 段：直连写的「同一 request_id 只执行一次」「被拒必不执行」「双层幂等共用一把锁」
      是否由真实 execute_idempotent 保证（用忠实复刻 SQL 语义的假连接，不信替身断言）。
B 段：通俗化在敌意输入下是否泄漏机器标识。
C 段：前后端契约字段是否对得上。

运行：python -m pytest backend/tests/test_t4_verifier_adversarial.py -q --no-header -p no:cacheprovider
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from datetime import datetime, timedelta
from typing import Any

import pytest

from backend.config.settings import Settings
from backend.layers.common.governance.idempotency import key_hash, request_hash
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.agent import agent_gateway_service as gateway_module
from backend.layers.features.agent import agent_humanize as humanize
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError, AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import AgentTool, AgentToolRegistry

TOKENS = ("api.", "adp_query", "adp_mutation", "POST", "PATCH", "DELETE", "{", "}", "request_id",
          "session_id", "tool_name", "status_code", "expected_version", "row_version", "payload")


class FakeIdempotencyDb:
    """忠实复刻 execute_idempotent 用到的 SQL 语义（SELECT FOR UPDATE / INSERT / UPDATE）。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[int, str, str], dict[str, Any]] = {}

    class _Cursor:
        def __init__(self, db: "FakeIdempotencyDb") -> None:
            self.db = db
            self.row: dict[str, Any] | None = None

        def __enter__(self) -> "FakeIdempotencyDb._Cursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[Any, ...]) -> None:
            if sql.startswith("SELECT request_hash"):
                self.row = self.db.rows.get((int(params[0]), str(params[1]), str(params[2])))
            elif sql.startswith("INSERT INTO idempotency_keys"):
                self.db.rows[(int(params[0]), str(params[1]), str(params[2]))] = {
                    "request_hash": params[3], "response_json": None, "response_status": None,
                    "status": "processing", "expires_at": params[4],
                }
            elif sql.startswith("UPDATE idempotency_keys SET status='completed'"):
                self.db.rows[(int(params[3]), str(params[4]), str(params[5]))].update(
                    status="completed", response_json=params[0], response_status=params[1], expires_at=params[2])
            elif sql.startswith("UPDATE idempotency_keys SET status='failed'"):
                self.db.rows[(int(params[1]), str(params[2]), str(params[3]))]["status"] = "failed"

        def fetchone(self) -> dict[str, Any] | None:
            return self.row

    class _Connection:
        def __init__(self, db: "FakeIdempotencyDb") -> None:
            self.db = db

        def cursor(self) -> "FakeIdempotencyDb._Cursor":
            return FakeIdempotencyDb._Cursor(self.db)

    @contextmanager
    def connect(self, _settings: object):
        yield FakeIdempotencyDb._Connection(self)

    def statuses(self) -> list[str]:
        return sorted(row["status"] for row in self.rows.values())


def install_fake_idempotency_db(monkeypatch: Any) -> FakeIdempotencyDb:
    db = FakeIdempotencyDb()
    monkeypatch.setattr("backend.layers.common.db.connection.get_connection", db.connect)
    return db


class MemoryConfirmations:
    """足够真实的确认存储替身：create/find/claim/失败与取消都会改状态。"""

    def __init__(self) -> None:
        self.by_token: dict[str, Any] = {}
        self.now = datetime(2026, 9, 11, 9, 0, 0)  # 早于真实的「现在」，expires_at=创建时刻+120s

    def create(self, confirmation: Any, token: str) -> Any:
        saved = replace(confirmation, id=len(self.by_token) + 1, created_at=self.now)
        self.by_token[token] = saved
        return saved

    @staticmethod
    def expected_session_hash(user: dict[str, Any]) -> str:
        """与 AgentGatewayPolicyMixin.session_hash 同口径，便于用用户字典直接断言。"""
        return str(user.get("_session_hash") or user.get("session_hash") or f"user:{user.get('id')}")

    def find(self, *, token: str, user_id: int, session_hash: str, now: Any = None) -> Any:
        row = self.by_token.get(token)
        if row is None or row.user_id != int(user_id) or row.status != "pending":
            return None
        return row if row.expires_at >= self.now else None

    def claim(self, *, token: str, user_id: int, session_hash: str, now: Any = None) -> Any:
        row = self.find(token=token, user_id=user_id, session_hash=session_hash)
        if row is None:
            return None
        claimed = replace(row, status="confirmed", used_at=self.now)
        self.by_token[token] = claimed
        return claimed

    def mark_cancelled(self, confirmation_id: int, *, user_id: int) -> bool:
        return self._settle(confirmation_id, "cancelled")

    def mark_failed(self, confirmation_id: int, *, user_id: int) -> bool:
        return self._settle(confirmation_id, "failed")

    def mark_expired(self, *, now: Any = None, user_id: int | None = None) -> list[int]:
        return []

    def _settle(self, confirmation_id: int, status: str) -> bool:
        for token, row in self.by_token.items():
            if row.id == int(confirmation_id):
                self.by_token[token] = replace(row, status=status)
                return True
        return False


class WorkItemSpy:
    """替代 work_items 的三个数据库动作，记录顺序以发现悬挂待办。"""

    def __init__(self, monkeypatch: Any, *, open_fails: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        monkeypatch.setattr(gateway_module, "open_confirmation_work_item", self._open)
        monkeypatch.setattr(gateway_module, "complete_confirmation_work_item", self._complete)
        monkeypatch.setattr(gateway_module, "cancel_confirmation_work_item", self._cancel)
        self.open_fails = open_fails

    def _open(self, _settings: Any, *, confirmation: Any, tool: Any, user: Any) -> int | None:
        if self.open_fails:
            raise DomainError("WORK_ITEM_DOWN", "待办库不可用", 500)
        self.calls.append(("open", int(confirmation.id)))
        return int(confirmation.id)

    def _complete(self, _settings: Any, *, confirmation_id: int, user_id: int) -> None:
        self.calls.append(("complete", int(confirmation_id)))

    def _cancel(self, _settings: Any, *, confirmation_id: int, user_id: int) -> None:
        self.calls.append(("cancel", int(confirmation_id)))


def make_tool(name: str, *, method: str = "POST", path: str = "/api/v1/production/{resource}",
              permission: str = "production.manage", risk: str = "write",
              execute: Any = None, role: str | None = None, scope: bool = False) -> AgentTool:
    return AgentTool(
        name=name, description="验证用工具", method=method, path_template=path,
        parameters={"payload": {"type": "object", "required": True}},
        required_permission=permission, risk=risk, execute=execute, required_role=role,
        requires_data_scope=scope,
    )


def make_user(*permissions: str, **extra: Any) -> dict[str, Any]:
    user = {"id": 42, "status": "active", "permissions": list(permissions), "roles": [], "data_scopes": []}
    user.update(extra)
    return user


def build_gateway(tools: tuple[AgentTool, ...], *, mode: str = "direct", audit: Any = None,
                  confirmations: Any = None) -> AgentGatewayService:
    settings = Settings.from_env({"APP_ENV": "test", "AGENT_WRITE_MODE": mode})
    return AgentGatewayService(
        settings, registry=AgentToolRegistry(tools), confirmations=confirmations or MemoryConfirmations(),
        audit=audit,
    )


def recorder() -> tuple[list[dict[str, Any]], Any]:
    events: list[dict[str, Any]] = []
    return events, events.append


def user_with_session(**extra: Any) -> SimpleNamespace:
    """confirm() 需要通过内存确认存储的 find/claim：带上与网关同口径的会话哈希。"""
    user = make_user("production.manage", **extra)
    return SimpleNamespace(user=user, session_hash=MemoryConfirmations.expected_session_hash(user))


def audit_reason(events: list[dict[str, Any]]) -> str:
    return str([row for row in events if row["result"] == "failure"][-1]["reason"])

# =============================================================================
# A. 直连写：只执行一次 / 被拒必不执行 / 双层幂等
# =============================================================================


def test_direct_write_runs_exactly_once_under_the_real_idempotency_implementation(monkeypatch: Any) -> None:
    """真实 execute_idempotent + 假 MySQL：同一 request_id 重放必须只落地一次。"""
    db = install_fake_idempotency_db(monkeypatch)
    calls: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []

    def execute(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        calls.append(arguments)
        contexts.append(dict(context))
        return {"id": 88, "code": "FL-88", "name": "投喂-88", "quantity": 20, "before": {"id": 88}, "after": {"id": 88, "quantity": 20}}

    events, audit = recorder()
    tool = make_tool("production.create_record", execute=execute)
    gateway = build_gateway((tool,), audit=audit)
    payload = {"resource": "feed-logs", "payload": {"pond_id": 3, "quantity": 20}}

    first = gateway.prepare_tool(make_user("production.manage"), tool.name, payload, conversation_id="c-1", request_id="r-fixed")
    replay = gateway.prepare_tool(make_user("production.manage"), tool.name, payload, conversation_id="c-1", request_id="r-fixed")

    assert first["kind"] == "executed"
    assert len(calls) == 1, f"同一 request_id 被重复执行了 {len(calls)} 次"
    assert db.statuses() == ["completed"]
    assert first == replay, "重放应回放已存响应，而不是重新执行"
    assert list(db.rows)[0][1] == "agent:production.create_record"
    # finding A 修复后：幂等键只在外层预留一次，不再转发给内层业务路由
    assert contexts[0].get("idempotency_key") is None, "同一个键不能被两层各预留一次"
    assert contexts[0]["request_id"] == "r-fixed"
    success = [row for row in events if row["result"] == "success"][-1]
    assert success["before"] == {"id": 88} and success["after"] == {"id": 88, "quantity": 20}


def test_direct_write_uses_distinct_keys_per_request_and_blocks_payload_swap(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    calls: list[dict[str, Any]] = []
    tool = make_tool("production.create_record", execute=lambda arguments, context: calls.append(arguments) or {"id": 1})
    gateway = build_gateway((tool,))
    body = {"resource": "feed-logs", "payload": {"quantity": 1}}

    gateway.prepare_tool(make_user("production.manage"), tool.name, body, conversation_id="c-1", request_id="r-a")
    gateway.prepare_tool(make_user("production.manage"), tool.name, body, conversation_id="c-1", request_id="r-b")
    assert len(calls) == 2, "不同 request_id 是两次真实写入（本轮放开的预期行为）"

    events, audit = recorder()
    strict = build_gateway((tool,), audit=audit)
    with pytest.raises(AgentGatewayError) as exc:
        strict.prepare_tool(make_user("production.manage"), tool.name,
                            {"resource": "feed-logs", "payload": {"quantity": 999}},
                            conversation_id="c-1", request_id="r-b")
    assert len(calls) == 2, "键冲突时必须拒绝执行"
    assert "Traceback" not in exc.value.message and "pymysql" not in exc.value.message
    # finding B 修复后：DomainError 的 code/status 原样透出，运营能判断该不该重试。
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert exc.value.status == 409
    assert audit_reason(events) == "IDEMPOTENCY_CONFLICT"


def test_single_layer_idempotency_replays_instead_of_conflicting_with_itself(monkeypatch: Any) -> None:
    """finding A 修复后：外层预留过的同一个键，重放时直接回放，不会再和内层自锁。"""
    db = install_fake_idempotency_db(monkeypatch)
    calls: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    payload = {"resource": "feed-logs", "payload": {"quantity": 1}}
    tool = make_tool(
        "production.create_record",
        execute=lambda arguments, context: (calls.append(arguments), contexts.append(dict(context)), {"id": 1})[2],
    )
    key = "agent-direct:production.create_record:r-nested"
    db.rows[(42, "agent:production.create_record", key_hash(key))] = {
        "request_hash": request_hash(payload), "response_json": '{"kind": "executed", "reused": true}',
        "response_status": 200, "status": "completed", "expires_at": datetime(2026, 9, 11, 13, 0, 0),
    }
    events, audit = recorder()
    gateway = build_gateway((tool,), audit=audit)

    replayed = gateway.prepare_tool(
        make_user("production.manage"), tool.name, payload, conversation_id="c-1", request_id="r-nested",
    )

    assert calls == [], "重放时必须直接回放已存响应，不能再次落地"
    assert contexts == []
    assert replayed["kind"] == "executed"
    assert replayed["data"] == {"kind": "executed", "reused": True}, "回放要带回当初存下的业务响应"
    assert replayed["message"] == "新增投喂记录完成。", "回放同样只给人话，不给原始 JSON"


@pytest.mark.parametrize("case", ["no_permission", "dead_session", "no_scope", "wrong_role"])
def test_direct_write_never_executes_when_gate_says_no(monkeypatch: Any, case: str) -> None:
    install_fake_idempotency_db(monkeypatch)
    calls: list[dict[str, Any]] = []
    events, audit = recorder()
    expected = {
        "no_permission": ("FORBIDDEN", 403, make_user("production.view"), {}),
        "dead_session": ("UNAUTHENTICATED", 401, make_user("production.manage", status="locked"), {}),
        "no_scope": ("DATA_SCOPE_REQUIRED", 403, make_user("production.manage", roles=[{"code": "breeder"}]), {"scope": True}),
        "wrong_role": ("FORBIDDEN", 403, make_user("auth.user.manage", roles=[{"code": "breeder"}]),
                       {"method": "POST", "path": "/api/v1/admin/users", "permission": "auth.user.manage", "role": "super_admin"}),
    }
    code, status, user, tool_kwargs = expected[case]
    tool = make_tool("production.create_record", execute=lambda arguments, context: calls.append(arguments), **tool_kwargs)
    gateway = build_gateway((tool,), audit=audit)

    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(user, tool.name, {"resource": "feed-logs", "payload": {"quantity": 1}},
                             conversation_id="c-1", request_id=f"r-{case}")

    assert exc.value.code == code, case
    assert exc.value.status == status, case
    assert calls == [], f"{case} 时业务 executor 被调用了 {len(calls)} 次"
    assert not any(row["result"] == "success" for row in events)
    # finding C 修复后：会话失效与被拒写一样必须留失败审计，滥用探针才看得到。
    assert events and events[-1]["result"] == "failure", f"{case} 必须留失败审计"
    assert events[-1]["reason"] == code, f"{case} 的审计原因应是 {code}"
    if case == "dead_session":
        assert events[-1]["tool_name"] == tool.name, "会话失效也要带上被尝试的操作用于排查"


def test_direct_write_never_executes_human_only_operations(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    calls: list[dict[str, Any]] = []
    events, audit = recorder()
    tool = make_tool("api.auth_identity", method="POST", path="/api/v1/auth/login", permission="auth.user.manage",
                     risk="human_only", execute=lambda arguments, context: calls.append(arguments))
    gateway = build_gateway((tool,), audit=audit)

    result = gateway.prepare_tool(make_user("auth.user.manage"), tool.name, {"payload": {}},
                                  conversation_id="c-1", request_id="r-human")

    assert result["kind"] == "human_only"
    assert calls == []
    assert [row["result"] for row in events] == ["human_only"]


def test_direct_write_failure_keeps_raw_exception_out_of_message_and_audit(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    events, audit = recorder()

    def boom(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionResetError("pymysql 2003 Can't connect to MySQL server on 127.0.0.1:3306 (password=s3cret)")

    tool = make_tool("production.create_record", execute=boom)
    gateway = build_gateway((tool,), audit=audit)

    with pytest.raises(AgentGatewayError) as exc:
        gateway.prepare_tool(make_user("production.manage"), tool.name, {"resource": "feed-logs", "payload": {}},
                             conversation_id="c-1", request_id="r-boom")

    assert "没做成" in exc.value.message and "新增投喂记录" in exc.value.message
    for leak in ("Traceback", "pymysql", "127.0.0.1", "s3cret", "SELECT", "ConnectionResetError"):
        assert leak not in exc.value.message, f"错误话术泄漏了 {leak}"
    assert exc.value.status == 400
    assert len(events) == 1, f"失败应只留一条审计，实际 {[row['result'] for row in events]}"
    failure = events[-1]
    assert failure["result"] == "failure" and failure["error"] == "业务执行失败"


def test_confirm_mode_opens_completes_and_cancels_work_items(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    spy = WorkItemSpy(monkeypatch)
    calls: list[dict[str, Any]] = []
    confirmations = MemoryConfirmations()
    tool = make_tool("production.create_record", execute=lambda arguments, context: calls.append(arguments) or {"id": 5})
    gateway = build_gateway((tool,), mode="confirm", confirmations=confirmations)

    prepared = gateway.prepare_tool(make_user("production.manage"), tool.name,
                                    {"resource": "feed-logs", "payload": {"quantity": 1}},
                                    conversation_id="c-1", request_id="r-c")
    assert prepared["kind"] == "confirmation_required"
    assert calls == [] and spy.calls == [("open", 1)]

    identity = user_with_session()
    executed = gateway.confirm(identity.user, prepared["confirmation"]["token"], request_id="r-c2")
    assert executed["kind"] == "executed"
    assert len(calls) == 1 and spy.calls == [("open", 1), ("complete", 1)]


def test_confirm_mode_cancels_the_work_item_when_execution_fails(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    spy = WorkItemSpy(monkeypatch)
    confirmations = MemoryConfirmations()

    def boom(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raise DomainError("PRODUCTION_RULE", "投喂记录数量必须大于 0", 400)

    tool = make_tool("production.create_record", execute=boom)
    gateway = build_gateway((tool,), mode="confirm", confirmations=confirmations)
    prepared = gateway.prepare_tool(make_user("production.manage"), tool.name,
                                    {"resource": "feed-logs", "payload": {"quantity": 0}},
                                    conversation_id="c-1", request_id="r-d")

    with pytest.raises(AgentGatewayError) as exc:
        gateway.confirm(user_with_session().user, prepared["confirmation"]["token"], request_id="r-d2")

    # finding D（低）：DomainError 业务规则文案在确认路径被兜底话术吃掉（真实链路里业务错误
    # 会先被 dispatch_fixed_tool 转成 AgentGatewayError，所以线上影响小，但直连 execute 会丢）。
    assert exc.value.message == "业务操作未完成，请在页面核对状态"
    assert spy.calls == [("open", 1), ("cancel", 1)], "失败必须取消待办，否则会悬挂"
    assert confirmations.by_token[prepared["confirmation"]["token"]].status == "failed"


def test_confirm_mode_rechecks_permission_at_click_time(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    WorkItemSpy(monkeypatch)
    calls: list[dict[str, Any]] = []
    events, audit = recorder()
    confirmations = MemoryConfirmations()
    tool = make_tool("production.create_record", execute=lambda arguments, context: calls.append(arguments) or {"id": 5})
    gateway = build_gateway((tool,), mode="confirm", audit=audit, confirmations=confirmations)
    prepared = gateway.prepare_tool(make_user("production.manage"), tool.name,
                                    {"resource": "feed-logs", "payload": {"quantity": 1}},
                                    conversation_id="c-1", request_id="r-e")

    with pytest.raises(AgentGatewayError) as exc:
        gateway.confirm(user_with_session(permissions=["production.view"]).user, prepared["confirmation"]["token"], request_id="r-e2")

    assert exc.value.code == "FORBIDDEN"
    assert calls == [], "权限被收回后确认不得落地"
    assert events[-1]["result"] == "failure"

# =============================================================================
# B. 通俗化：敌意输入不得泄漏机器标识
# =============================================================================


STRUCTURED_HOSTILE_INPUTS: list[Any] = [
    None, True, False, 0, 1, "", "   ", {}, [], 12345678901234567890,
    [{"name": "一号塘", "weight_kg": "1234.50", "quantity": "20", "status": "pending"}],
    {"items": [{"name": "一号塘", "amount": "1.50"}], "total": "99", "page_size": "20"},
    {"record": {"name": "二号塘", "unknown_machine_field": {"nested_api.value": 1}}},
    {"surprise_key": {"api.tool": "x" * 400}},
]
KEY_MARKERS = ("api.", "adp_query", "adp_mutation", "request_id", "session_id", "tool_name",
               "expected_version", "row_version")


@pytest.mark.parametrize("payload", STRUCTURED_HOSTILE_INPUTS, ids=[f"case{index}" for index in range(len(STRUCTURED_HOSTILE_INPUTS))])
def test_summarize_never_returns_machine_identifiers_for_structured_input(payload: Any) -> None:
    """dict/list/标量输入：结构、字段名、追踪字段都不许进人话。"""
    prose = humanize.summarize(payload, title="新增投喂记录")
    assert isinstance(prose, str) and prose.strip()
    for token in (*KEY_MARKERS, "adp_query", "PATCH", "DELETE", "{", "}", "[", "]", "payload"):
        assert token not in prose, f"{token} 泄漏进人话：{prose[:200]}"
    if isinstance(payload, dict):
        assert "surprise key" not in prose and "surprise_key" not in prose


RAW_STRING_PASSTHROUGH = [
    "api.production_create_post_api_v1_production_resource",
    "POST /api/v1/production/feed-logs",
    "request_id=req_9f8a7b6c session_id=sess-1234 tool_name=adp_mutation",
    "weight_kg=20 pond_code=TK-001 expected_version=3",
    '{"code":"NOT_FOUND","message":"请求的资源不存在"}',
]


@pytest.mark.parametrize("text", RAW_STRING_PASSTHROUGH)
def test_raw_string_output_is_verbatim_until_the_frontend_sanitizer_runs(text: str) -> None:
    """finding E（低危）：后端 summarize 对「纯字符串输出」原样透传，不去技术标识。

    该字符串只可能来自业务接口的 message/错误文本；面板侧 AgentPanel.vue 会对
    result.message 再跑一次 sanitizeTechnical，所以用户看不到机器标识。这里把契约
    边界钉住：如果需要「后端单独也干净」，必须由后端补一次净化。
    """
    assert humanize.summarize(text, title="新增投喂记录") == text
    # 而同样的文本一旦是结构化字段值，就会被翻译：说明差别只在「字符串直通」这一条路径。
    assert "weight_kg" not in humanize.summarize({"weight_kg": "20", "pond_code": "TK-001"}, title="新增投喂记录")

def test_change_rows_uses_chinese_labels_and_drops_tracking_fields() -> None:
    rows = humanize.change_rows({
        "resource": "feed-logs", "expected_version": 3, "raw_instruction": "给3号塘投喂20公斤",
        "payload": {"pond_code": "TK-001", "weight_kg": "1234.50", "quantity": 20, "note": None,
                    "nested_machine": {"inner_key": "x"}},
    })
    labels = {row["label"]: row["value"] for row in rows}
    assert labels["塘口编码"] == "TK-001"
    assert labels["重量（kg）"] == "1234.50"
    assert labels["数量"] == "20"
    assert labels["对象类型"] == "投喂记录"
    assert list(labels)[-1] == "对象类型"
    assert not any(key in labels for key in ("expected_version", "raw_instruction", "版本号", "原始指令"))
    for label in labels:
        assert "expected_version" not in label and "row_version" not in label


def test_action_title_and_target_label_stay_chinese_for_hostile_paths() -> None:
    cases = [
        (("POST", "/api/v1/production/{resource}"), {"resource": "feed-logs"}, "新增投喂记录", "投喂记录"),
        (("DELETE", "/api/v1/master-data/{resource}/{record_id}"), {"resource": "ponds"}, "删除塘口档案", "塘口档案"),
        (("POST", "/api/v1/admin/users"), {"payload": {"name": "张三"}}, "新增账号", "系统账号 张三"),
        # finding F 修复后：表里没有的资源段不再回显英文 code，退回中性说法。
        (("POST", "/api/v1/nowhere/unknown"), {"resource": ""}, "新增该业务对象", "该业务对象"),
    ]
    for (method, path), arguments, title, target in cases:
        assert humanize.action_title(method, path, resource=humanize.resource_code(path, arguments)) == title
        assert humanize.target_label(path, arguments) == target


def test_executed_message_from_the_gateway_is_plain_chinese(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    tool = make_tool("production.create_record", execute=lambda arguments, context: {
        "id": 9, "code": "FL-HTTP-1", "name": "投喂-HTTP", "quantity": 20, "weight_kg": "1234.50",
    })
    gateway = build_gateway((tool,))
    result = gateway.prepare_tool(make_user("production.manage"), tool.name,
                                 {"resource": "feed-logs", "payload": {"pond_code": "TK-001", "quantity": 20}},
                                 conversation_id="c-1", request_id="r-plain")

    message = result["message"]
    # finding F（低）：字符串型数字走 Decimal 分支，不再加千分位；int/Decimal 会加。
    assert message == "新增投喂记录完成：「投喂-HTTP」，编码 FL-HTTP-1，20尾，1,234.5kg。"
    assert humanize.summarize({"quantity": 1234}, title="新增投喂记录").endswith("1,234尾。")
    assert result["execution"]["title"] == "新增投喂记录"
    assert result["execution"]["rows_changed"] == 1
    assert all(token not in message for token in TOKENS)


# =============================================================================
# C. 前后端契约：字段名与语义
# =============================================================================


def test_executed_and_confirmation_payloads_match_the_frontend_contract(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    WorkItemSpy(monkeypatch)
    tool = make_tool("production.create_record", execute=lambda arguments, context: {"id": 5, "name": "一号塘"})
    arguments = {"resource": "feed-logs", "payload": {"pond_code": "TK-001", "quantity": 20}}

    direct = build_gateway((tool,)).prepare_tool(make_user("production.manage"), tool.name, arguments,
                                                conversation_id="c-1", request_id="r-contract-1")
    assert set(direct) >= {"kind", "message", "execution", "request_id", "status", "data"}
    assert set(direct["execution"]) == {"title", "detail", "summary", "changes", "rows_changed"}
    assert direct["kind"] == "executed"

    confirm = build_gateway((tool,), mode="confirm").prepare_tool(make_user("production.manage"), tool.name, arguments,
                                                                  conversation_id="c-1", request_id="r-contract-2")
    card = confirm["confirmation"]
    assert confirm["kind"] == "confirmation_required"
    assert set(card) >= {"id", "token", "tool_name", "summary", "target", "changes", "risk", "risk_level", "expires_at"}
    assert card["risk_level"] in {"normal", "high"}
    assert card["target"] == "投喂记录 TK-001"
    assert card["summary"] == "新增投喂记录"


def test_admin_confirmation_is_flagged_high_risk(monkeypatch: Any) -> None:
    install_fake_idempotency_db(monkeypatch)
    WorkItemSpy(monkeypatch)
    tool = make_tool("admin.create_user", path="/api/v1/admin/users", permission="auth.user.manage",
                     role="super_admin", execute=lambda arguments, context: {"id": 1})
    user = make_user("auth.user.manage", roles=[{"code": "super_admin"}])
    card = build_gateway((tool,), mode="confirm").prepare_tool(
        user, tool.name, {"payload": {"name": "张三"}}, conversation_id="c-1", request_id="r-admin")["confirmation"]

    assert card["risk_level"] == "high"
    assert "账号" in card["risk"] and "api." not in card["risk"]
    assert card["target"] == "系统账号 张三"

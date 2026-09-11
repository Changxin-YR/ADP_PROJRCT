"""MySQL 集成用例：智能体确认待办在真实库里的可见性与到期级联。

本地无 MySQL 凭据时按既有基建自动 skip（`disposable_database` 在缺少
`ADP_TEST_MYSQL_CLIENT` / `ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1` 时既定 skip）；
有库时真跑，验证三件事：
1. 待办指派给发起确认的本人、初始状态 claimed，且 source_key 与确认 ID 一一对应；
2. `mark_expired` 返回的 ID 能把对应待办级联收口成 cancelled（此前会永远停在 claimed）；
3. 收口后再次执行仍然幂等，不会把已完成的待办改回去。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.layers.common.db.connection import get_connection
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_confirmation_work_item import (
    close_expired_confirmation_work_items,
    open_confirmation_work_item,
    source_key_of,
)
from backend.layers.features.agent.agent_contracts import AgentConfirmation
from backend.layers.features.agent.agent_tool_registry import build_registry
from backend.tests.mysql_test_database import disposable_database, settings_for


def _env_for(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", settings.mysql_host)
    monkeypatch.setenv("MYSQL_PORT", str(settings.mysql_port))
    monkeypatch.setenv("MYSQL_DATABASE", settings.mysql_database)
    monkeypatch.setenv("MYSQL_USER", settings.mysql_user)
    monkeypatch.setenv("MYSQL_PASSWORD", settings.mysql_password)


def _sales_tool():
    tools = build_registry().tools
    return next(t for t in tools if t.path_template.endswith("/api/v1/sales/orders") and t.method == "POST")


def _confirmation(user_id: int, *, seconds: int) -> AgentConfirmation:
    return AgentConfirmation(
        id=0,
        idempotency_key="agent-confirmation:pending",
        token_hash="",
        user_id=user_id,
        session_hash="session-hash",
        conversation_id="conversation-1",
        request_id="request-1",
        tool_name="api.sales_create_order_post_api_v1_sales_orders",
        payload={"quantity": 450},
        status="pending",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=seconds),
    )


def _work_item(cursor: Any, confirmation_id: int) -> dict[str, Any]:
    cursor.execute(
        "SELECT assignee_user_id,status,module_code,action_code,object_type,source_key,priority "
        "FROM work_items WHERE source_key=%s",
        (source_key_of(confirmation_id),),
    )
    return dict(cursor.fetchone())


def test_confirmation_work_item_is_visible_to_requester_and_expires_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_database("adp_agent_work_item", through=34) as database:
        settings = settings_for(database)
        _env_for(settings, monkeypatch)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000002','Agent User','hash','active')"
            )
            user_id = int(cursor.lastrowid)

        store = MySqlAgentConfirmationStore()
        tool = _sales_tool()

        # 1) 未过期：待办指派给本人、状态 claimed
        live = store.create(_confirmation(user_id, seconds=120), "token-live")
        assert open_confirmation_work_item(settings, confirmation=live, tool=tool, user={"id": user_id}) == live.id
        with get_connection(settings) as connection, connection.cursor() as cursor:
            row = _work_item(cursor, live.id)
        assert row["assignee_user_id"] == user_id, "待办必须指派给发起确认的本人"
        assert row["status"] == "claimed"
        assert row["module_code"] == "agent" and row["action_code"] == "confirm_write"
        assert row["object_type"] == "agent:confirmation"

        # 2) 已过期：mark_expired 返回 ID，级联把待办收口为 cancelled
        stale = store.create(_confirmation(user_id, seconds=-60), "token-stale")
        open_confirmation_work_item(settings, confirmation=stale, tool=tool, user={"id": user_id})
        expired_ids = store.mark_expired(user_id=user_id)
        assert stale.id in expired_ids
        assert live.id not in expired_ids, "未到期的确认不能被清理"

        close_expired_confirmation_work_items(settings, confirmation_ids=expired_ids, user_id=user_id)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            assert _work_item(cursor, stale.id)["status"] == "cancelled"
            assert _work_item(cursor, live.id)["status"] == "claimed"
            cursor.execute("SELECT status FROM agent_confirmations WHERE id IN (%s,%s) ORDER BY id", (live.id, stale.id))
            statuses = [r["status"] for r in cursor.fetchall()]
        assert statuses == ["pending", "expired"]

        # 3) 幂等：重复收口不会把状态改回去，也不会报错
        close_expired_confirmation_work_items(settings, confirmation_ids=expired_ids, user_id=user_id)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            assert _work_item(cursor, stale.id)["status"] == "cancelled"

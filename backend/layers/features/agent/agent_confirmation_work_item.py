"""把智能体的"确认闸门"接入统一待办队列（人在环上：一个队列收口两类决策）。

设计要点：
- **不新增表列**：用确定性的 ``source_key = agent:confirmation:{confirmation_id}`` 关联 work_items
  与 agent_confirmations，避免双写一致性与迁移成本。
- 待办**直接指派给发起确认的本人**（智能体只代表登录用户操作，确认人就是他自己）；
  初始状态 ``claimed``：用户点"发起"时其实已经持有它，等待的是确认动作本身。
- ``complete/cancel`` 用 ``WHERE status IN ('pending','claimed','in_progress','escalated')`` 守卫，
  重复调用天然幂等，也允许待办被流转到 in_progress 后仍能收口。
- **失败隔离**：本模块的写操作在独立的 ``get_connection(settings)`` 里执行。``get_connection``
  是事务语义（成功提交 / 异常回滚），若与主流程共用请求连接，一旦这里抛错会把整个请求事务标记为
  回滚，从而"弄脏"主流程。独立连接保证：待办失败最多丢一条待办，绝不拖垮确认与业务执行。
"""
from __future__ import annotations

from typing import Any

from backend.layers.common.db.connection import get_connection

def _humanize(tool: Any, payload: Any) -> tuple[str, str, list[dict[str, str]]]:
    from backend.layers.features.agent.agent_humanize import action_title, change_rows, resource_code, target_label

    path = str(getattr(tool, "path_template", "") or "")
    arguments = payload if isinstance(payload, dict) else {}
    action = action_title(str(getattr(tool, "method", "") or "").upper(), path, resource=resource_code(path, arguments))
    return action, target_label(path, arguments), change_rows(arguments)


def _action_text(tool: Any, payload: Any) -> str:
    """待办标题：说清要干什么，不出现工具名。"""
    return _humanize(tool, payload)[0]


def _detail_text(tool: Any, payload: Any) -> str:
    """待办详情：影响对象 + 关键字段，不出现工具名与原始 JSON。"""
    _action, target, rows = _humanize(tool, payload)
    text = f"影响对象：{target}"
    filled = "、".join(f"{row['label']} {row['value']}" for row in rows[:6])
    return f"{text}｜{filled}"[:1000] if filled else text[:1000]


MODULE_CODE = "agent"
ACTION_CODE = "confirm_write"
OBJECT_TYPE = "agent:confirmation"
SETTLED_STATUSES = "('completed','cancelled')"
OPEN_STATUSES = "('pending','claimed','in_progress','escalated')"


def source_key_of(confirmation_id: int) -> str:
    return f"agent:confirmation:{int(confirmation_id)}"


def open_confirmation_work_item(
    settings: Any,
    *,
    confirmation: Any,
    tool: Any,
    user: dict[str, Any],
) -> int | None:
    """为写操作确认建一条待办；任何失败都降级为 None，不影响确认流程。"""
    confirmation_id = int(getattr(confirmation, "id", 0) or 0)
    if confirmation_id <= 0:
        return None
    from backend.layers.features.agent.agent_gateway_policy import requires_confirmation

    risk_level = "high" if requires_confirmation(tool) else "normal"
    payload = getattr(confirmation, "payload", None) or {}
    # 待办标题与详情都必须是业务人话：工具名/参数 JSON 会直接渲染在待办队列里。
    action = _action_text(tool, payload)
    detail_text = _detail_text(tool, payload)
    try:
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO work_items "
                "(assignee_user_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,detail,priority,status,"
                " claimed_by,claimed_at,due_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'claimed',%s,CURRENT_TIMESTAMP,%s) "
                "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),updated_at=CURRENT_TIMESTAMP",
                (
                    int(user["id"]),
                    MODULE_CODE,
                    ACTION_CODE,
                    OBJECT_TYPE,
                    confirmation_id,
                    source_key_of(confirmation_id),
                    source_key_of(confirmation_id),
                    f"待确认：{action}"[:255],
                    detail_text,
                    risk_level,
                    int(user["id"]),
                    getattr(confirmation, "expires_at", None),
                ),
            )
            work_item_id = cursor.lastrowid
        return int(work_item_id) if work_item_id else None
    except Exception:  # noqa: BLE001 - 待办是增强能力，绝不能让确认流程失败
        return None


def complete_confirmation_work_item(settings: Any, *, confirmation_id: int, user_id: int) -> None:
    _settle(settings, confirmation_id=confirmation_id, user_id=user_id, completed=True)


def cancel_confirmation_work_item(settings: Any, *, confirmation_id: int, user_id: int) -> None:
    _settle(settings, confirmation_id=confirmation_id, user_id=user_id, completed=False)


def _settle(settings: Any, *, confirmation_id: int, user_id: int, completed: bool) -> None:
    try:
        with get_connection(settings) as connection, connection.cursor() as cursor:
            if completed:
                cursor.execute(
                    "UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,"
                    "completion_note='智能体写操作已由本人确认执行',row_version=row_version+1 "
                    f"WHERE source_key=%s AND status IN {OPEN_STATUSES}",
                    (int(user_id), source_key_of(confirmation_id)),
                )
            else:
                cursor.execute(
                    "UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,"
                    "cancel_reason='确认执行失败，待办自动取消',row_version=row_version+1 "
                    f"WHERE source_key=%s AND status IN {OPEN_STATUSES}",
                    (int(user_id), source_key_of(confirmation_id)),
                )
    except Exception:  # noqa: BLE001 - 收口失败不影响主流程
        return



def close_expired_confirmation_work_items(settings: Any, *, confirmation_ids: list[int], user_id: int) -> int:
    """确认到期后把对应待办一并收口，避免待办永远停在 claimed。返回处理条数。

    不需要再包一层 try：_settle 内部已逐条降级（失败即放弃该条且不抛出），
    在这里再造一层"保护"只会制造虚假的安全感。
    """
    for confirmation_id in confirmation_ids or []:
        _settle(settings, confirmation_id=int(confirmation_id), user_id=int(user_id), completed=False)
    return len(confirmation_ids or [])

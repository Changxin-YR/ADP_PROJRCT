from __future__ import annotations

from typing import Any


def notify_work_item_created(
    connection: Any,
    *,
    organization_id: Any,
    module_code: str,
    action_code: str,
    object_type: str,
    object_id: Any,
    object_ref: str | None,
    source_key: str,
    title: str,
    permission_codes: list[str],
) -> None:
    """待办生成时同步写入未读通知（最小实现，BUG-006）。

    - 复用 work_items 的关键字段（module/action/object/source_key/title）。
    - 收件人 = 同企业内持有对应处理权限（permission_codes）的在用账号；
      企业归属按账号数据范围解析（区域/基地 -> organization_id）。
    - dedup 由 (recipient_user_id, dedup_key) 唯一键收敛：重复提交只累加
      occurrence_count 并刷新 last_occurred_at，不会产生重复未读。
    - 不传 permission_codes 或解析不到收件人时不生成任何记录（安全降级）。
    """
    if not organization_id or not permission_codes:
        return
    try:
        organization_id = int(organization_id)
    except (TypeError, ValueError):
        return
    placeholders = ",".join(["%s"] * len(permission_codes))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT u.id
            FROM users u
            INNER JOIN user_roles ur ON ur.user_id = u.id
            INNER JOIN roles r ON r.id = ur.role_id AND r.status = 'active'
            INNER JOIN role_permissions rp ON rp.role_id = r.id
            INNER JOIN permissions p ON p.id = rp.permission_id
            WHERE u.status = 'active'
              AND p.code IN ({placeholders})
              AND u.id IN (
                  SELECT uds.user_id
                  FROM user_data_scopes uds
                  INNER JOIN data_scopes ds ON ds.id = uds.data_scope_id AND ds.status = 'active'
                  LEFT JOIN areas a ON a.id = ds.area_id
                  LEFT JOIN farms f ON f.id = a.farm_id
                  WHERE ds.scope_type = 'farm'
                     OR COALESCE(a.organization_id, f.organization_id) = %s
              )
            """,
            (*permission_codes, organization_id),
        )
        recipients = [int(row["id"]) for row in cursor.fetchall()]
        dedup_key = f"work_item:{source_key}"[:191]
        for recipient in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_user_id, module_code, notification_type, object_type, object_id,
                     object_ref, dedup_key, title, body, level)
                VALUES (%s, %s, 'work_item', %s, %s, %s, %s, %s, %s, 'normal')
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title), body = VALUES(body), level = VALUES(level),
                    occurrence_count = occurrence_count + 1,
                    last_occurred_at = CURRENT_TIMESTAMP,
                    status = IF(status = 'closed', 'unread', status)
                """,
                (
                    recipient,
                    module_code,
                    object_type,
                    object_id,
                    object_ref,
                    dedup_key,
                    f"待办提醒：{title}",
                    f"您有一条新的待办事项：{title}，请及时处理。",
                ),
            )

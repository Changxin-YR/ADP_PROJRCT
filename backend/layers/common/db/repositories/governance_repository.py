from __future__ import annotations

from datetime import date, datetime
from typing import Any


class GovernanceRepository:
    """SQL access for append-only audit queries and shared governance records."""

    @staticmethod
    def _area_scope_sql(area_ids: list[int] | None) -> tuple[str, list[Any]]:
        if not area_ids:
            return "", []
        placeholders = ",".join(["%s"] * len(area_ids))
        params: list[Any] = [*area_ids]
        predicate = f"""
            AND (
                (wi.object_type = 'master:areas' AND EXISTS (SELECT 1 FROM areas x WHERE x.id=wi.object_id AND x.id IN ({placeholders})))
                OR (wi.object_type = 'master:pond-groups' AND EXISTS (SELECT 1 FROM pond_groups x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'master:ponds' AND EXISTS (SELECT 1 FROM ponds x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'master:pond_status_change' AND EXISTS (SELECT 1 FROM ponds p WHERE p.id=wi.object_id AND p.area_id IN ({placeholders})))
                OR (wi.object_type LIKE 'production:%' AND wi.object_type <> 'production:batches' AND EXISTS (SELECT 1 FROM production_documents x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'production:batches' AND EXISTS (SELECT 1 FROM production_batches x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type LIKE 'warehouse:%' AND EXISTS (SELECT 1 FROM warehouse_documents x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'purchase:order' AND EXISTS (SELECT 1 FROM purchase_orders x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'purchase:payment' AND EXISTS (SELECT 1 FROM purchase_payments x JOIN purchase_payables py ON py.id=x.payable_id JOIN purchase_orders po ON po.id=py.purchase_order_id WHERE x.id=wi.object_id AND po.area_id IN ({placeholders})))
                OR (wi.object_type = 'sales:order' AND EXISTS (SELECT 1 FROM sales_orders x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'sales:delivery' AND EXISTS (SELECT 1 FROM sales_deliveries x JOIN sales_orders so ON so.id=x.sales_order_id WHERE x.id=wi.object_id AND so.area_id IN ({placeholders})))
                OR (wi.object_type = 'sales:receipt' AND EXISTS (SELECT 1 FROM sales_receipts x JOIN sales_receivables sr ON sr.id=x.receivable_id JOIN sales_orders so ON so.id=sr.sales_order_id WHERE x.id=wi.object_id AND so.area_id IN ({placeholders})))
                OR (wi.object_type = 'cost:asset' AND EXISTS (SELECT 1 FROM cost_assets x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'cost:entry' AND EXISTS (SELECT 1 FROM cost_entries x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
                OR (wi.object_type = 'cost:settlement' AND EXISTS (SELECT 1 FROM cost_settlements x WHERE x.id=wi.object_id AND x.area_id IN ({placeholders})))
            )
        """
        return predicate, params * 15

    def list_audit_logs(
        self,
        connection: Any,
        *,
        user_id: int | None = None,
        module_code: str | None = None,
        action_code: str | None = None,
        object_type: str | None = None,
        result: str | None = None,
        created_from: date | datetime | None = None,
        created_to: date | datetime | None = None,
        request_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        conditions: list[str] = []
        params: list[Any] = []
        filters = (
            ("al.user_id = %s", user_id),
            ("al.module_code = %s", module_code),
            ("al.action_code = %s", action_code),
            ("al.object_type = %s", object_type),
            ("al.result = %s", result),
            ("al.created_at >= %s", created_from),
            ("al.created_at < %s", created_to),
            ("al.request_id = %s", request_id),
        )
        for clause, value in filters:
            if value is not None and value != "":
                conditions.append(clause)
                params.append(value)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM audit_logs AS al {where}", tuple(params))
            total = int((cursor.fetchone() or {}).get("total", 0))
            offset = (page - 1) * page_size
            cursor.execute(
                f"""
                SELECT al.id, al.user_id, COALESCE(al.actor_name_snapshot, u.name) AS actor_name,
                       al.action, al.action_code, al.module_code, al.object_type, al.object_id,
                       al.object_ref, al.result, al.detail_json, al.reason, al.ip_address,
                       al.request_id, al.before_json, al.after_json, al.changed_fields_json,
                       al.related_work_item_id, al.created_at
                FROM audit_logs AS al
                LEFT JOIN users AS u ON u.id = al.user_id
                {where}
                ORDER BY al.created_at DESC, al.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [page_size, offset]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": offset + len(items) < total}

    def list_work_items(
        self,
        connection: Any,
        *,
        user_id: int,
        allowed_modules: list[str] | None = None,
        allow_unassigned: bool = True,
        allowed_area_ids: list[int] | None = None,
        status: str | None = None,
        include_history: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        conditions = ["(wi.assignee_user_id = %s" + (" OR wi.assignee_user_id IS NULL)" if allow_unassigned else ")")]
        params: list[Any] = [user_id]
        if allowed_modules is not None:
            if not allowed_modules:
                conditions.append("1 = 0")
            else:
                conditions.append(f"wi.module_code IN ({','.join(['%s'] * len(allowed_modules))})")
                params.extend(allowed_modules)
        area_sql, area_params = self._area_scope_sql(allowed_area_ids)
        if area_sql:
            conditions.append(area_sql.strip()[4:].strip())
            params.extend(area_params)
        if status:
            conditions.append("wi.status = %s")
            params.append(status)
        elif not include_history:
            conditions.append("wi.status IN ('pending', 'claimed', 'in_progress', 'escalated')")
        where = "WHERE " + " AND ".join(conditions)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM work_items AS wi {where}", tuple(params))
            total = int((cursor.fetchone() or {}).get("total", 0))
            offset = (page - 1) * page_size
            cursor.execute(
                f"""
                SELECT wi.id, wi.assignee_user_id, wi.module_code, wi.action_code,
                       wi.object_type, wi.object_id, wi.object_ref, wi.source_key,
                       wi.title, wi.detail, wi.priority, wi.status, wi.due_at,
                       wi.claimed_by, wi.claimed_at, wi.completed_by, wi.completed_at,
                       wi.completion_note, wi.cancelled_by, wi.cancelled_at,
                       wi.cancel_reason, wi.row_version, wi.created_at, wi.updated_at,
                       (wi.due_at IS NOT NULL AND wi.due_at < CURRENT_TIMESTAMP) AS overdue
                FROM work_items AS wi
                {where}
                ORDER BY FIELD(wi.status, 'pending', 'escalated', 'claimed', 'in_progress', 'completed', 'cancelled'),
                         wi.due_at IS NULL, wi.due_at ASC, wi.updated_at DESC, wi.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [page_size, offset]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": offset + len(items) < total}

    def transition_work_item(
        self,
        connection: Any,
        *,
        item_id: int,
        user_id: int,
        allowed_modules: list[str],
        allow_unassigned: bool,
        allowed_area_ids: list[int] | None = None,
        action: str,
        expected_version: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"claim", "start", "complete", "cancel"}
        if action not in allowed:
            raise ValueError("不支持的待办操作")
        with connection.cursor() as cursor:
            area_sql, area_params = self._area_scope_sql(allowed_area_ids)
            cursor.execute(f"SELECT wi.* FROM work_items wi WHERE wi.id = %s{area_sql} FOR UPDATE", (item_id, *area_params))
            item = cursor.fetchone()
            if item is None:
                raise ValueError("待办不存在")
            if item.get("module_code") not in allowed_modules:
                raise PermissionError("无权处理该业务模块的待办")
            if item.get("module_code") != "workbench" or item.get("object_type") != "workbench:manual":
                raise PermissionError("领域待办必须进入对应业务完成处理")
            if item.get("assignee_user_id") is None and not allow_unassigned:
                raise PermissionError("无权认领未分配待办")
            if item.get("assignee_user_id") not in {None, user_id}:
                raise PermissionError("无权处理该待办")
            if expected_version is not None and int(item.get("row_version", 0)) != int(expected_version):
                raise ValueError("待办已被其他人更新，请刷新后重试")
            current = item.get("status")
            updates: str
            params: list[Any]
            if action == "claim":
                if current not in {"pending", "escalated"}:
                    raise ValueError("当前状态不能认领")
                updates = "assignee_user_id = %s, claimed_by = %s, claimed_at = CURRENT_TIMESTAMP, status = 'claimed'"
                params = [user_id, user_id]
            elif action == "start":
                if current != "claimed" or item.get("claimed_by") != user_id:
                    raise ValueError("当前状态不能开始处理")
                updates = "status = 'in_progress'"
                params = []
            elif action == "complete":
                if current not in {"claimed", "in_progress"} or item.get("assignee_user_id") != user_id:
                    raise ValueError("当前状态不能完成")
                updates = "status = 'completed', completed_by = %s, completed_at = CURRENT_TIMESTAMP, completion_note = %s"
                params = [user_id, note]
            else:
                if current not in {"pending", "claimed", "in_progress", "escalated"} or item.get("assignee_user_id") != user_id:
                    raise ValueError("当前状态不能取消")
                if not note:
                    raise ValueError("取消待办必须填写原因")
                updates = "status = 'cancelled', cancelled_by = %s, cancelled_at = CURRENT_TIMESTAMP, cancel_reason = %s"
                params = [user_id, note]
            version_clause = " AND row_version = %s" if expected_version is not None else ""
            where_params: list[Any] = [item_id]
            if expected_version is not None:
                where_params.append(expected_version)
            cursor.execute(f"UPDATE work_items SET {updates}, row_version = row_version + 1 WHERE id = %s{version_clause}", tuple(params + where_params))
            if cursor.rowcount != 1:
                raise ValueError("待办已被其他人更新，请刷新后重试")
            cursor.execute("SELECT * FROM work_items WHERE id = %s", (item_id,))
            updated = cursor.fetchone()
        result = dict(updated or {**item, "status": "completed" if action == "complete" else action})
        result["_audit_before_status"] = current
        return result

    def list_notifications(
        self,
        connection: Any,
        *,
        user_id: int,
        status: str | None = None,
        include_history: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        conditions = ["n.recipient_user_id = %s"]
        params: list[Any] = [user_id]
        if status:
            conditions.append("n.status = %s")
            params.append(status)
        elif not include_history:
            conditions.append("n.status IN ('unread', 'escalated')")
        where = "WHERE " + " AND ".join(conditions)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM notifications AS n {where}", tuple(params))
            total = int((cursor.fetchone() or {}).get("total", 0))
            offset = (page - 1) * page_size
            cursor.execute(
                f"""
                SELECT n.id, n.recipient_user_id, n.module_code, n.notification_type,
                       n.object_type, n.object_id, n.object_ref, n.dedup_key, n.title,
                       n.body, n.level, n.status, n.occurrence_count, n.first_occurred_at,
                       n.last_occurred_at, n.read_at, n.closed_by, n.closed_at,
                       n.close_conclusion, n.created_at, n.updated_at
                FROM notifications AS n
                {where}
                ORDER BY FIELD(n.status, 'unread', 'escalated', 'read', 'closed'), n.last_occurred_at DESC, n.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [page_size, offset]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": offset + len(items) < total}

    def mark_notification_read(self, connection: Any, *, notification_id: int, user_id: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE notifications SET status = 'read', read_at = COALESCE(read_at, CURRENT_TIMESTAMP) WHERE id = %s AND recipient_user_id = %s AND status = 'unread'", (notification_id, user_id))
            if cursor.rowcount != 1:
                raise ValueError("消息不存在或已处理")
            cursor.execute("SELECT * FROM notifications WHERE id = %s", (notification_id,))
            return dict(cursor.fetchone() or {})

    def close_notification(self, connection: Any, *, notification_id: int, user_id: int, conclusion: str) -> dict[str, Any]:
        if not conclusion.strip():
            raise ValueError("关闭消息必须填写处理结论")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE notifications SET status = 'closed', closed_by = %s, closed_at = CURRENT_TIMESTAMP, close_conclusion = %s WHERE id = %s AND recipient_user_id = %s AND status IN ('unread', 'read', 'escalated')", (user_id, conclusion.strip(), notification_id, user_id))
            if cursor.rowcount != 1:
                raise ValueError("消息不存在或已关闭")
            cursor.execute("SELECT * FROM notifications WHERE id = %s", (notification_id,))
            return dict(cursor.fetchone() or {})

    def upsert_notification(self, connection: Any, *, payload: dict[str, Any]) -> dict[str, Any]:
        required = ("recipient_user_id", "module_code", "notification_type", "dedup_key", "title")
        if any(not payload.get(key) for key in required):
            raise ValueError("通知缺少必要字段")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_user_id, module_code, notification_type, object_type, object_id,
                     object_ref, dedup_key, title, body, level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title), body = VALUES(body), level = VALUES(level),
                    occurrence_count = occurrence_count + 1, last_occurred_at = CURRENT_TIMESTAMP,
                    status = IF(status = 'closed', 'unread', status)
                """,
                tuple(payload.get(key) for key in ("recipient_user_id", "module_code", "notification_type", "object_type", "object_id", "object_ref", "dedup_key", "title", "body", "level")),
            )
            cursor.execute("SELECT * FROM notifications WHERE recipient_user_id = %s AND dedup_key = %s", (payload["recipient_user_id"], payload["dedup_key"]))
            return dict(cursor.fetchone() or {})

from __future__ import annotations

import json
from typing import Any

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import decode, page_result, require_evidence, require_scope, require_unlocked, scope_clause, validate_scope
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created


class MySqlCostExpenseStore:
    def __init__(self, settings: Any) -> None:
        self.settings, self.audit = settings, AuditLogger()

    @staticmethod
    def _get(cursor: Any, record_id: int, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT ce.*,c.code AS category_code,c.name AS category_name FROM cost_entries ce JOIN cost_categories c ON c.id=ce.category_id WHERE ce.id=%s" + (" FOR UPDATE" if lock else ""), (record_id,))
        return decode(cursor.fetchone())

    def get_expense(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id)
            if row:
                require_scope(user, row)
            return row

    def list_expenses(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        clauses, values = ["ce.source_type NOT IN ('legacy_import','asset_depreciation','warehouse_ledger')"], []
        scope, scoped = scope_clause(user, "ce")
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("ce.status=%s"); values.append(status)
        if search:
            clauses.append("(ce.source_ref LIKE %s OR c.name LIKE %s)"); values.extend([f"%{search}%"] * 2)
        joins = " FROM cost_entries ce JOIN cost_categories c ON c.id=ce.category_id"
        where = " AND ".join(clauses)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT ce.*,c.code AS category_code,c.name AS category_name{joins} WHERE {where} ORDER BY ce.updated_at DESC,ce.id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            items = [decode(row) or {} for row in cursor.fetchall()]
        return page_result(items, page, page_size, total)

    @staticmethod
    def _category(cursor: Any, code: str) -> dict[str, Any]:
        cursor.execute("SELECT id,default_nature FROM cost_categories WHERE code=%s AND status='active'", (code,))
        category = cursor.fetchone()
        if not category:
            raise DomainError("COST_CATEGORY_INVALID", "成本分类不存在或已停用", 400)
        return category

    @staticmethod
    def _values(payload: dict[str, Any], category: dict[str, Any]) -> tuple[Any, ...]:
        evidence = payload.get("evidence_attachment_ids")
        return (
            payload["organization_id"], payload["farm_id"], payload.get("area_id"), category["id"], payload["amount"],
            payload["occurred_on"], payload["period_start"], payload["period_end"], payload.get("cost_nature") or category["default_nature"],
            payload["source_type"], payload["source_ref"], json.dumps(payload.get("source_detail"), ensure_ascii=False) if payload.get("source_detail") is not None else None,
            payload.get("target_type"), payload.get("target_id"), json.dumps(evidence) if evidence is not None else None,
        )

    def create_expense(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            clean = validate_scope(cursor, payload, user); category = self._category(cursor, clean["category_code"]); require_unlocked(cursor, clean)
            cursor.execute(
                "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,cost_nature,source_type,source_ref,source_detail_json,target_type,target_id,evidence_attachment_ids_json,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s)",
                (*self._values(clean, category), user_id),
            )
            row = self._get(cursor, int(cursor.lastrowid)) or {}
            self._audit(connection, user_id, "create", row["id"], after=row)
            return row

    def update_expense(self, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_ENTRY_NOT_FOUND", "费用记录不存在", 404)
            require_scope(user, before)
            if before["status"] not in {"draft", "submitted"}:
                raise DomainError("RECORD_READ_ONLY", "已核验费用不可编辑", 409)
            clean = validate_scope(cursor, payload, user); category = self._category(cursor, clean["category_code"]); require_unlocked(cursor, clean)
            cursor.execute(
                "UPDATE cost_entries SET organization_id=%s,farm_id=%s,area_id=%s,category_id=%s,amount=%s,occurred_on=%s,period_start=%s,period_end=%s,cost_nature=%s,source_type=%s,source_ref=%s,source_detail_json=%s,target_type=%s,target_id=%s,evidence_attachment_ids_json=%s,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')",
                (*self._values(clean, category), user_id, record_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, record_id) or {}
            save_revision(connection, build_revision(entity_type="cost:entry", entity_id=record_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
            if after["status"] == "submitted":
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"cost:entry:{record_id}:verify"))
            self._audit(connection, user_id, "update", record_id, before=before, after=after)
            return after

    def transition_expense(self, record_id: int, status: str, *, expected_version: int, evidence_attachment_ids: list[int], user: dict[str, Any], user_id: int) -> dict[str, Any]:
        previous = {"submitted": "draft", "verified": "submitted", "confirmed": "verified"}[status]
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_ENTRY_NOT_FOUND", "费用记录不存在", 404)
            require_scope(user, before)
            if before["status"] != previous or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "状态或版本已变化，请刷新后重试", 409)
            if status == "confirmed":
                require_unlocked(cursor, before)
            if status in {"verified", "confirmed"}:
                require_evidence(cursor, before, "cost:entry", evidence_attachment_ids)
            assignments = {"submitted": "", "verified": ",verified_by=%s,verified_at=NOW()", "confirmed": ",confirmed_by=%s,confirmed_at=NOW()"}[status]
            params: list[Any] = [status, json.dumps(evidence_attachment_ids) if evidence_attachment_ids else None]
            if assignments:
                params.append(user_id)
            params.extend([record_id, expected_version, previous])
            cursor.execute(f"UPDATE cost_entries SET status=%s,evidence_attachment_ids_json=COALESCE(%s,evidence_attachment_ids_json),row_version=row_version+1{assignments} WHERE id=%s AND row_version=%s AND status=%s", tuple(params))
            after = self._get(cursor, record_id) or {}; source = f"cost:entry:{record_id}"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','verify','cost:entry',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"entry:{record_id}", f"{source}:verify", f"核验费用：{after['source_ref']}", after["row_version"]))
                notify_work_item_created(
                    connection,
                    organization_id=after["organization_id"],
                    module_code="cost",
                    action_code="verify",
                    object_type="cost:entry",
                    object_id=record_id,
                    object_ref=f"entry:{record_id}",
                    source_key=f"{source}:verify",
                    title=f"核验费用：{after['source_ref']}",
                    permission_codes=["cost.entry.verify"],
                )
            elif status == "verified":
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='费用核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{source}:verify"))
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','confirm','cost:entry',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"entry:{record_id}", f"{source}:confirm", f"确认费用：{after['source_ref']}", after["row_version"]))
                notify_work_item_created(
                    connection,
                    organization_id=after["organization_id"],
                    module_code="cost",
                    action_code="confirm",
                    object_type="cost:entry",
                    object_id=record_id,
                    object_ref=f"entry:{record_id}",
                    source_key=f"{source}:confirm",
                    title=f"确认费用：{after['source_ref']}",
                    permission_codes=["cost.entry.confirm"],
                )
            else:
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='费用确认完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{source}:confirm"))
            self._audit(connection, user_id, status, record_id, before=before, after=after)
            return after

    def delete_expense(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id, True)
            if not row:
                raise DomainError("COST_ENTRY_NOT_FOUND", "费用记录不存在", 404)
            require_scope(user, row)
            cursor.execute("DELETE FROM cost_entries WHERE id=%s AND status='draft'", (record_id,))
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅未提交草稿可删除", 409)
            self._audit(connection, user_id, "delete", record_id, before=row)
            return row

    def reverse_expense(self, record_id: int, *, reason: str, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            original = self._get(cursor, record_id, True)
            if not original or original["status"] != "confirmed" or original.get("reversal_of_id") is not None:
                raise DomainError("COST_REVERSAL_NOT_ALLOWED", "仅已确认费用可冲销", 409)
            if original.get("source_type") in {"asset_depreciation", "warehouse_ledger"}:
                raise DomainError("COST_REVERSAL_NOT_ALLOWED", "自动成本来源不能通过费用接口冲销", 409)
            require_scope(user, original); require_unlocked(cursor, original)
            cursor.execute("SELECT id FROM cost_entries WHERE reversal_of_id=%s LIMIT 1", (record_id,))
            if cursor.fetchone():
                raise DomainError("COST_REVERSAL_EXISTS", "该费用已存在冲销记录", 409)
            cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,source_detail_json,target_type,target_id,reversal_of_id,created_by,confirmed_by,confirmed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,'reversal',%s,%s,%s,%s,%s,%s,%s,NOW())", (original["organization_id"], original["farm_id"], original.get("area_id"), original["category_id"], -abs(original["amount"]), original["occurred_on"], original["period_start"], original["period_end"], original["cost_nature"], f"REV-{record_id}-{user_id}", json.dumps({"reason": reason}, ensure_ascii=False), original.get("target_type"), original.get("target_id"), record_id, user_id, user_id))
            row = self._get(cursor, int(cursor.lastrowid)) or {}; self._audit(connection, user_id, "reverse", record_id, before=original, after=row, reason=reason)
            return row

    def _audit(self, connection: Any, user_id: int, action: str, record_id: int, **values: Any) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_cost_entry", object_type="cost_entry", object_id=record_id, object_ref=f"cost_entry:{record_id}", result="success", ip_address=None, module_code="cost", action_code=f"{action}_cost_entry", **values)

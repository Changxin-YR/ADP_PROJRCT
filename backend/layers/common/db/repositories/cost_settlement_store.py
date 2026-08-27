from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import decode, page_result, require_scope, scope_clause
from backend.layers.common.governance.lifecycle import DomainError


class MySqlCostSettlementStore:
    def __init__(self, settings: Any) -> None:
        self.settings, self.audit = settings, AuditLogger()

    @staticmethod
    def _get(cursor: Any, record_id: int, lock: bool = False, sources: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT s.*,u.name AS operator FROM cost_settlements s LEFT JOIN users u ON u.id=s.created_by WHERE s.id=%s" + (" FOR UPDATE" if lock else ""), (record_id,))
        row = decode(cursor.fetchone())
        if row and sources:
            cursor.execute("SELECT * FROM cost_settlement_sources WHERE settlement_id=%s ORDER BY direction,source_type,id", (record_id,))
            row["sources"] = [decode(item) or {} for item in cursor.fetchall()]
        return row

    def get_settlement(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id, sources=True)
            if row:
                require_scope(user, row)
            return row

    def list_settlements(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        clauses, values = ["1=1"], []
        scope, scoped = scope_clause(user, "s")
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("s.status=%s"); values.append(status)
        if search:
            clauses.append("(s.code LIKE %s OR s.name LIKE %s)"); values.extend([f"%{search}%"] * 2)
        joins, where = " FROM cost_settlements s LEFT JOIN users u ON u.id=s.created_by", " AND ".join(clauses)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT s.*,u.name AS operator{joins} WHERE {where} ORDER BY s.period_end DESC,s.id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            rows = [decode(row) or {} for row in cursor.fetchall()]
        return page_result(rows, page, page_size, total)

    @staticmethod
    def _income_sources(cursor: Any, run: dict[str, Any], period_start: Any, period_end: Any) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT d.id AS source_id,d.code AS source_ref,(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-parent.quantity END)*o.unit_price AS amount,JSON_OBJECT('sales_order_id',o.id,'customer_id',o.customer_id,'delivered_at',d.delivered_at,'correction_of_id',d.correction_of_id) AS snapshot_json FROM sales_deliveries d LEFT JOIN sales_deliveries parent ON parent.id=d.correction_of_id JOIN sales_orders o ON o.id=d.sales_order_id WHERE d.organization_id=%s AND o.farm_id=%s AND (%s IS NULL OR o.area_id=%s) AND d.status='verified' AND DATE(d.delivered_at) BETWEEN %s AND %s ORDER BY d.id",
            (run["organization_id"], run["farm_id"], run.get("area_id"), run.get("area_id"), period_start, period_end),
        )
        return list(cursor.fetchall())

    @staticmethod
    def _cost_sources(cursor: Any, run_id: int) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT ce.id AS source_id,ce.source_type,ce.source_ref,SUM(d.amount) AS amount,JSON_OBJECT('category_id',ce.category_id,'allocation_run_id',d.run_id,'source_detail',ce.source_detail_json) AS snapshot_json FROM cost_allocation_details d JOIN cost_entries ce ON ce.id=d.cost_entry_id WHERE d.run_id=%s GROUP BY ce.id,ce.source_type,ce.source_ref,ce.category_id,d.run_id ORDER BY ce.id",
            (run_id,),
        )
        return list(cursor.fetchall())

    def _assert_sources_current(self, cursor: Any, settlement: dict[str, Any]) -> None:
        """正式核验前重读收入和成本来源，避免确认过期快照。"""
        stored = {
            (str(row.get("direction")), int(row.get("source_id"))): Decimal(str(row.get("amount") or 0))
            for row in settlement.get("sources", [])
        }
        income = self._income_sources(cursor, settlement, settlement["period_start"], settlement["period_end"])
        current = {
            ("income", int(row["source_id"])): Decimal(str(row.get("amount") or 0))
            for row in income
        }
        current.update({
            ("cost", int(row["source_id"])): Decimal(str(row.get("amount") or 0))
            for row in self._cost_sources(cursor, int(settlement["allocation_run_id"]))
        })
        if current != stored:
            raise DomainError("COST_SETTLEMENT_STALE", "结算来源已变化，请重新生成结算", 409)

    def create_settlement(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM cost_allocation_runs WHERE id=%s AND status='completed' FOR UPDATE", (payload["allocation_run_id"],)); run = cursor.fetchone()
            if not run or run["period_start"] != payload["period_start"] or run["period_end"] != payload["period_end"]:
                raise DomainError("COST_SETTLEMENT_RUN_INVALID", "结算期间与有效分摊结果不匹配", 422)
            require_scope(user, {**run, "created_by": user_id})
            cursor.execute("SELECT id FROM cost_settlements WHERE organization_id=%s AND farm_id=%s AND area_id<=>%s AND status<>'reversed' AND period_start<=%s AND period_end>=%s LIMIT 1", (run["organization_id"], run["farm_id"], run.get("area_id"), payload["period_end"], payload["period_start"]))
            if cursor.fetchone():
                raise DomainError("COST_SETTLEMENT_PERIOD_OVERLAP", "结算期间与已有未反结算期间重叠", 409)
            cursor.execute("SELECT 1 FROM cost_entries WHERE organization_id=%s AND farm_id=%s AND (%s IS NULL OR area_id=%s) AND status='confirmed' AND period_start<=%s AND period_end>=%s AND COALESCE(verified_at,created_at)>%s LIMIT 1", (run["organization_id"], run["farm_id"], run.get("area_id"), run.get("area_id"), payload["period_end"], payload["period_start"], run["created_at"]))
            if cursor.fetchone():
                raise DomainError("COST_SETTLEMENT_RUN_STALE", "分摊结果已过期，请重新运行成本分摊", 409)
            income_sources = self._income_sources(cursor, run, payload["period_start"], payload["period_end"]); cost_sources = self._cost_sources(cursor, run["id"])
            income = sum((Decimal(str(row["amount"])) for row in income_sources), Decimal("0")); cost = sum((Decimal(str(row["amount"])) for row in cost_sources), Decimal("0"))
            cursor.execute("SELECT COUNT(*)+1 AS version FROM cost_settlements WHERE organization_id=%s AND farm_id=%s AND area_id<=>%s AND period_start=%s AND period_end=%s", (run["organization_id"], run["farm_id"], run.get("area_id"), payload["period_start"], payload["period_end"])); version = int(cursor.fetchone()["version"])
            code = f"SET-{payload['period_start']:%Y%m}-{run['farm_id']}-{run.get('area_id') or 0}-{version}"
            cursor.execute("INSERT INTO cost_settlements (organization_id,farm_id,area_id,code,name,period_start,period_end,allocation_run_id,income_amount,cost_amount,profit_amount,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (run["organization_id"], run["farm_id"], run.get("area_id"), code, payload["name"], payload["period_start"], payload["period_end"], run["id"], income, cost, income - cost, user_id))
            settlement_id = int(cursor.lastrowid)
            source_rows = [
                (settlement_id, direction, row.get("source_type") or source_type, row["source_id"], row["source_ref"], row["amount"], row["snapshot_json"] if isinstance(row["snapshot_json"], str) else json.dumps(row["snapshot_json"], ensure_ascii=False, default=str))
                for direction, source_type, rows in (("income", "sales_delivery", income_sources), ("cost", "cost_entry", cost_sources)) for row in rows
            ]
            if source_rows:
                cursor.executemany("INSERT INTO cost_settlement_sources (settlement_id,direction,source_type,source_id,source_ref,amount,snapshot_json) VALUES (%s,%s,%s,%s,%s,%s,%s)", source_rows)
            row = self._get(cursor, settlement_id, sources=True) or {}; self._audit(connection, user_id, "create", settlement_id, after=row)
            return row

    def update_settlement(self, record_id: int, name: str, *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_SETTLEMENT_NOT_FOUND", "结算记录不存在", 404)
            require_scope(user, before)
            if before["status"] not in {"draft", "submitted"} or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "仅草稿或待核验的当前版本可编辑", 409)
            cursor.execute("UPDATE cost_settlements SET name=%s,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s", (name, user_id, record_id, expected_version))
            after = self._get(cursor, record_id, sources=True) or {}
            if after["status"] == "submitted":
                cursor.execute("UPDATE work_items SET target_version=%s,status='pending' WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"cost:settlement:{record_id}:verify"))
            self._audit(connection, user_id, "update", record_id, before=before, after=after)
            return after

    def delete_settlement(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True, True)
            if not before:
                raise DomainError("COST_SETTLEMENT_NOT_FOUND", "结算记录不存在", 404)
            require_scope(user, before)
            if before["status"] != "draft":
                raise DomainError("DELETE_NOT_ALLOWED", "仅结算草稿可删除", 409)
            self._audit(connection, user_id, "delete", record_id, before=before)
            cursor.execute("DELETE FROM cost_settlement_sources WHERE settlement_id=%s", (record_id,))
            cursor.execute("DELETE FROM cost_settlements WHERE id=%s AND status='draft'", (record_id,))
            return before

    def transition_settlement(self, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, **_: Any) -> dict[str, Any]:
        previous = {"submitted": "draft", "verified": "submitted", "confirmed": "verified"}[status]
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True, sources=status in {"verified", "confirmed"})
            if not before:
                raise DomainError("COST_SETTLEMENT_NOT_FOUND", "结算记录不存在", 404)
            require_scope(user, before)
            if before["status"] != previous or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "状态或版本已变化，请刷新后重试", 409)
            if status in {"verified", "confirmed"}:
                self._assert_sources_current(cursor, before)
            if status == "confirmed" and int(before.get("verified_by") or 0) == int(user_id):
                raise DomainError("SELF_APPROVAL_FORBIDDEN", "结算核验人与确认人必须分离", 403)
            assignment = {"submitted": "", "verified": ",verified_by=%s,verified_at=NOW()", "confirmed": ",confirmed_by=%s,confirmed_at=NOW()"}[status]
            params: list[Any] = [status]
            if assignment:
                params.append(user_id)
            params.extend([record_id, expected_version, previous])
            cursor.execute(f"UPDATE cost_settlements SET status=%s,row_version=row_version+1{assignment} WHERE id=%s AND row_version=%s AND status=%s", tuple(params))
            after = self._get(cursor, record_id, sources=True) or {}; key = f"cost:settlement:{record_id}"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','verify','cost:settlement',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"settlement:{record_id}", f"{key}:verify", f"核验结算：{after['name']}", after["row_version"]))
            elif status == "verified":
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='结算核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{key}:verify"))
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','confirm','cost:settlement',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"settlement:{record_id}", f"{key}:confirm", f"确认结算：{after['name']}", after["row_version"]))
            else:
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='结算确认完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{key}:confirm"))
            self._audit(connection, user_id, status, record_id, before=before, after=after); return after

    def reverse_settlement(self, record_id: int, *, expected_version: int, reason: str, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_SETTLEMENT_NOT_FOUND", "结算记录不存在", 404)
            require_scope(user, before)
            cursor.execute("UPDATE cost_settlements SET status='reversed',reversal_reason=%s,reversed_by=%s,reversed_at=NOW(),row_version=row_version+1 WHERE id=%s AND status='confirmed' AND row_version=%s", (reason, user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "仅当前版本的已确认结算可反结算", 409)
            after = self._get(cursor, record_id, sources=True) or {}; self._audit(connection, user_id, "reverse", record_id, before=before, after=after, reason=reason)
            return after

    def net_report(self, *, period_start: Any, period_end: Any, user: dict[str, Any]) -> dict[str, Any]:
        scope, values = scope_clause(user, "s"); clauses = ["s.status='confirmed'", "s.period_start>=%s", "s.period_end<=%s"]
        params: list[Any] = [period_start, period_end]
        if scope:
            clauses.append(scope); params.extend(values)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COALESCE(SUM(income_amount),0) AS income_amount,COALESCE(SUM(cost_amount),0) AS cost_amount,COALESCE(SUM(profit_amount),0) AS profit_amount,COUNT(*) AS settlement_count FROM cost_settlements s WHERE {' AND '.join(clauses)}", tuple(params))
            return dict(cursor.fetchone())

    def _audit(self, connection: Any, user_id: int, action: str, record_id: int, **values: Any) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_cost_settlement", object_type="cost_settlement", object_id=record_id, object_ref=f"cost_settlement:{record_id}", result="success", ip_address=None, module_code="cost", action_code=f"{action}_cost_settlement", **values)

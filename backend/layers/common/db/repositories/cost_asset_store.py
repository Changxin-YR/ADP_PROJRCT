from __future__ import annotations

import calendar
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import decode, page_result, require_evidence, require_scope, require_unlocked, scope_clause, validate_scope
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision


ASSET_COLUMNS = ("organization_id", "farm_id", "area_id", "code", "name", "asset_type", "category_id", "purchase_date", "original_value", "salvage_value", "useful_life_months", "depreciation_start_date", "allocation_driver", "target_type", "target_id", "note", "evidence_attachment_ids_json")


class MySqlCostAssetStore:
    def __init__(self, settings: Any) -> None:
        self.settings, self.audit = settings, AuditLogger()

    @staticmethod
    def _get(cursor: Any, record_id: int, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT a.*,c.code AS category_code,c.name AS category_name FROM cost_assets a JOIN cost_categories c ON c.id=a.category_id WHERE a.id=%s" + (" FOR UPDATE" if lock else ""), (record_id,))
        return decode(cursor.fetchone())

    def get_asset(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id)
            if row:
                require_scope(user, row)
            return row

    def list_assets(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        clauses, values = ["1=1"], []
        scope, scoped = scope_clause(user, "a")
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("a.status=%s"); values.append(status)
        if search:
            clauses.append("(a.code LIKE %s OR a.name LIKE %s)"); values.extend([f"%{search}%"] * 2)
        joins, where = " FROM cost_assets a JOIN cost_categories c ON c.id=a.category_id", " AND ".join(clauses)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT a.*,c.code AS category_code,c.name AS category_name,COALESCE((SELECT SUM(d.amount) FROM cost_depreciation_entries d WHERE d.asset_id=a.id),0) AS accumulated_depreciation{joins} WHERE {where} ORDER BY a.updated_at DESC,a.id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            rows = [decode(row) or {} for row in cursor.fetchall()]
        return page_result(rows, page, page_size, total)

    @staticmethod
    def _clean(cursor: Any, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        clean = validate_scope(cursor, payload, user)
        cursor.execute("SELECT id FROM cost_categories WHERE code=%s AND status='active'", (clean["category_code"],))
        category = cursor.fetchone()
        if not category:
            raise DomainError("COST_CATEGORY_INVALID", "资产成本分类不存在", 400)
        clean["category_id"] = category["id"]
        evidence = clean.pop("evidence_attachment_ids", None)
        clean["evidence_attachment_ids_json"] = json.dumps(evidence) if evidence is not None else None
        return clean

    @staticmethod
    def _values(clean: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(clean.get(field) for field in ASSET_COLUMNS)

    def create_asset(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            clean = self._clean(cursor, payload, user); require_unlocked(cursor, clean, "purchase_date")
            columns = ",".join(ASSET_COLUMNS)
            cursor.execute(f"INSERT INTO cost_assets ({columns},status,created_by) VALUES ({','.join(['%s'] * len(ASSET_COLUMNS))},'draft',%s)", (*self._values(clean), user_id))
            row = self._get(cursor, int(cursor.lastrowid)) or {}; self._audit(connection, user_id, "create", row["id"], after=row)
            return row

    def update_asset(self, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_ASSET_NOT_FOUND", "资产不存在", 404)
            require_scope(user, before)
            if before["status"] not in {"draft", "submitted"}:
                raise DomainError("RECORD_READ_ONLY", "已核验资产不可编辑", 409)
            clean = self._clean(cursor, payload, user); require_unlocked(cursor, clean, "purchase_date")
            assignments = ",".join(f"{field}=%s" for field in ASSET_COLUMNS)
            cursor.execute(f"UPDATE cost_assets SET {assignments},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*self._values(clean), user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, record_id) or {}
            save_revision(connection, build_revision(entity_type="cost:asset", entity_id=record_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
            if after["status"] == "submitted":
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"cost:asset:{record_id}:verify"))
            self._audit(connection, user_id, "update", record_id, before=before, after=after)
            return after

    def transition_asset(self, record_id: int, status: str, *, expected_version: int, evidence_attachment_ids: list[int], user: dict[str, Any], user_id: int) -> dict[str, Any]:
        previous = {"submitted": "draft", "verified": "submitted", "confirmed": "verified"}[status]
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, True)
            if not before:
                raise DomainError("COST_ASSET_NOT_FOUND", "资产不存在", 404)
            require_scope(user, before)
            if before["status"] != previous or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "状态或版本已变化，请刷新后重试", 409)
            if status in {"verified", "confirmed"}:
                require_evidence(cursor, before, "cost:asset", evidence_attachment_ids)
            assignments = {"submitted": "", "verified": ",verified_by=%s,verified_at=NOW()", "confirmed": ",confirmed_by=%s,confirmed_at=NOW()"}[status]
            params: list[Any] = [status, json.dumps(evidence_attachment_ids) if evidence_attachment_ids else None]
            if assignments:
                params.append(user_id)
            params.extend([record_id, expected_version, previous])
            cursor.execute(f"UPDATE cost_assets SET status=%s,evidence_attachment_ids_json=COALESCE(%s,evidence_attachment_ids_json),row_version=row_version+1{assignments} WHERE id=%s AND row_version=%s AND status=%s", tuple(params))
            after = self._get(cursor, record_id) or {}; key = f"cost:asset:{record_id}"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','verify','cost:asset',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"asset:{record_id}", f"{key}:verify", f"核验资产：{after['name']}", after["row_version"]))
            elif status == "verified":
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='资产核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{key}:verify"))
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'cost','confirm','cost:asset',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"asset:{record_id}", f"{key}:confirm", f"确认资产：{after['name']}", after["row_version"]))
            else:
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='资产确认完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"{key}:confirm"))
            self._audit(connection, user_id, status, record_id, before=before, after=after)
            return after

    def delete_asset(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id, True)
            if not row:
                raise DomainError("COST_ASSET_NOT_FOUND", "资产不存在", 404)
            require_scope(user, row); cursor.execute("DELETE FROM cost_assets WHERE id=%s AND status='draft'", (record_id,))
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅未提交资产草稿可删除", 409)
            self._audit(connection, user_id, "delete", record_id, before=row); return row

    def depreciate_asset(self, record_id: int, *, period: str, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        period_start = date.fromisoformat(f"{period}-01"); period_end = date(period_start.year, period_start.month, calendar.monthrange(period_start.year, period_start.month)[1])
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            asset = self._get(cursor, record_id, True)
            if not asset or asset["status"] != "confirmed":
                raise DomainError("COST_ASSET_NOT_CONFIRMED", "仅已确认资产可计提折旧", 409)
            require_scope(user, asset); require_unlocked(cursor, {**asset, "period_date": period_end}, "period_date")
            cursor.execute(
                "SELECT period_start,period_end FROM accounting_periods "
                "WHERE organization_id=%s AND farm_id=%s AND status='open' "
                "ORDER BY period_start DESC LIMIT 1 FOR UPDATE",
                (asset["organization_id"], asset["farm_id"]),
            )
            open_period = cursor.fetchone()
            if open_period is None or period_start < open_period["period_start"] or period_end > open_period["period_end"]:
                raise DomainError("ACCOUNTING_PERIOD_CLOSED", "折旧期间不是当前开放会计期间", 409)
            start = asset["depreciation_start_date"]
            month_offset = (period_start.year - start.year) * 12 + period_start.month - start.month
            if month_offset < 0 or month_offset >= int(asset["useful_life_months"]):
                raise DomainError("DEPRECIATION_PERIOD_INVALID", "折旧期间不在资产使用期限内", 422)
            cursor.execute("SELECT id FROM cost_depreciation_entries WHERE asset_id=%s AND period_start=%s AND period_end=%s", (record_id, period_start, period_end))
            if cursor.fetchone():
                raise DomainError("DEPRECIATION_PERIOD_EXISTS", "该资产在此期间已计提折旧", 409)
            cursor.execute("SELECT COALESCE(SUM(amount),0) AS accumulated,COUNT(*) AS periods FROM cost_depreciation_entries WHERE asset_id=%s", (record_id,)); totals = cursor.fetchone()
            if int(totals["periods"]) >= int(asset["useful_life_months"]):
                raise DomainError("ASSET_FULLY_DEPRECIATED", "资产已完成全部折旧", 409)
            if int(totals["periods"]) != month_offset:
                raise DomainError("DEPRECIATION_PERIOD_INVALID", "折旧必须按使用期限逐月计提", 422)
            depreciable = Decimal(str(asset["original_value"])) - Decimal(str(asset["salvage_value"])); remaining = depreciable - Decimal(str(totals["accumulated"]))
            regular = (depreciable / int(asset["useful_life_months"])).quantize(Decimal("0.01"))
            amount = remaining if int(totals["periods"]) == int(asset["useful_life_months"]) - 1 else min(regular, remaining)
            try:
                cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,source_detail_json,target_type,target_id,created_by,confirmed_by,confirmed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed','public','asset_depreciation',%s,%s,%s,%s,%s,%s,NOW())", (asset["organization_id"], asset["farm_id"], asset.get("area_id"), asset["category_id"], amount, period_end, period_start, period_end, f"DEP-{asset['code']}-{period}", json.dumps({"asset_id": record_id, "asset_code": asset["code"]}, ensure_ascii=False), asset.get("target_type"), asset.get("target_id"), user_id, user_id))
                entry_id = int(cursor.lastrowid)
                cursor.execute("INSERT INTO cost_depreciation_entries (organization_id,asset_id,period_start,period_end,amount,cost_entry_id,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)", (asset["organization_id"], record_id, period_start, period_end, amount, entry_id, user_id))
            except pymysql.IntegrityError as exc:
                raise DomainError("DEPRECIATION_PERIOD_EXISTS", "该资产在此期间已计提折旧", 409) from exc
            depreciation_id = int(cursor.lastrowid)
            self._audit(connection, user_id, "depreciate", record_id, after={"period": period, "amount": amount, "cost_entry_id": entry_id})
            return {"id": depreciation_id, "asset_id": record_id, "period": period, "period_start": period_start, "period_end": period_end, "amount": amount, "cost_entry_id": entry_id}

    def _audit(self, connection: Any, user_id: int, action: str, record_id: int, **values: Any) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_cost_asset", object_type="cost_asset", object_id=record_id, object_ref=f"cost_asset:{record_id}", result="success", ip_address=None, module_code="cost", action_code=f"{action}_cost_asset", **values)

from __future__ import annotations

from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.lifecycle import verify_version


class WarehouseMasterStoreMixin:
    audit = AuditLogger()
    @staticmethod
    def _ensure_scope_immutable(cursor: Any, warehouse_id: int, before: dict[str, Any], merged: dict[str, Any]) -> None:
        changed = any(str(merged.get(field)) != str(before.get(field)) for field in ("farm_id", "area_id"))
        if not changed:
            return
        for table in ("inventory_ledger", "warehouse_documents", "purchase_orders"):
            cursor.execute(f"SELECT 1 FROM {table} WHERE warehouse_id=%s LIMIT 1", (warehouse_id,))
            if cursor.fetchone():
                raise DomainError("WAREHOUSE_SCOPE_IMMUTABLE", "仓库已有历史业务记录，不能修改基地或区域归属", 409)

    @staticmethod
    def _validate_area(cursor: Any, area_id: Any, organization_id: int, farm_id: int) -> None:
        if not area_id:
            return
        cursor.execute("SELECT organization_id,farm_id FROM areas WHERE id=%s AND status<>'archived'", (area_id,))
        area = cursor.fetchone()
        if area is None or int(area["organization_id"]) != organization_id or int(area["farm_id"]) != farm_id:
            raise DomainError("WAREHOUSE_SCOPE_INVALID", "区域不属于所选企业和基地", 400)

    def create_warehouse(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT organization_id FROM farms WHERE id=%s AND status='verified'", (payload.get("farm_id"),))
            farm = cursor.fetchone()
            if farm is None:
                raise DomainError("WAREHOUSE_FARM_INVALID", "所属基地不存在或已归档", 400)
            clean = {**payload, "organization_id": int(payload.get("organization_id") or farm["organization_id"]), "status": payload.get("status") or "active"}
            if int(clean["organization_id"]) != int(farm["organization_id"]):
                raise DomainError("WAREHOUSE_SCOPE_INVALID", "基地不属于所选企业", 400)
            self._validate_area(cursor, clean.get("area_id"), int(clean["organization_id"]), int(clean["farm_id"]))
            self._require_write_scope(user, {**clean, "created_by": user_id})
            try:
                cursor.execute("INSERT INTO warehouses (organization_id,farm_id,area_id,code,name,location,status) VALUES (%s,%s,%s,%s,%s,%s,%s)", (clean["organization_id"], clean["farm_id"], clean.get("area_id"), clean["code"], clean["name"], clean.get("location"), clean["status"]))
            except pymysql.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise DomainError("WAREHOUSE_CODE_EXISTS", "当前企业仓库编码已存在", 409) from exc
                raise DomainError("WAREHOUSE_CONSTRAINT_INVALID", "仓库档案不符合数据库约束", 400) from exc
            warehouse_id = int(cursor.lastrowid)
            cursor.execute("SELECT id,organization_id,farm_id,area_id,code,name,location,status,row_version,created_at FROM warehouses WHERE id=%s", (warehouse_id,))
            row = dict(cursor.fetchone() or {})
            self.audit.write(connection, user_id=user_id, action="create_warehouse", object_type="warehouse", object_id=warehouse_id, object_ref=f"warehouse:{warehouse_id}", result="success", ip_address=None, module_code="warehouse", before=None, after=row)
            return row

    def update_warehouse(self, warehouse_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM warehouses WHERE id=%s FOR UPDATE", (warehouse_id,))
            before = cursor.fetchone()
            if before is None:
                raise DomainError("WAREHOUSE_NOT_FOUND", "仓库不存在", 404)
            verify_version(expected_version=expected_version, current_version=int(before.get("row_version", 1)))
            self._require_scope(user, before)
            clean = {key: value for key, value in payload.items() if key in {"farm_id", "area_id", "code", "name", "location", "status"}}
            if not clean:
                raise DomainError("WAREHOUSE_NO_CHANGES", "没有可保存的修改", 400)
            merged = {**before, **clean}
            cursor.execute("SELECT organization_id FROM farms WHERE id=%s AND status='verified'", (merged["farm_id"],))
            farm = cursor.fetchone()
            if farm is None or int(farm["organization_id"]) != int(before["organization_id"]):
                raise DomainError("WAREHOUSE_SCOPE_INVALID", "基地不属于当前企业", 400)
            self._ensure_scope_immutable(cursor, warehouse_id, before, merged)
            self._validate_area(cursor, merged.get("area_id"), int(before["organization_id"]), int(merged["farm_id"]))
            self._require_write_scope(user, {**merged, "created_by": user_id})
            if clean.get("status") == "disabled" and str(before.get("status")) != "disabled":
                cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) AS balance FROM inventory_ledger WHERE warehouse_id=%s", (warehouse_id,))
                balance = cursor.fetchone() or {}
                cursor.execute("SELECT COUNT(*) AS pending FROM warehouse_documents WHERE (warehouse_id=%s OR target_warehouse_id=%s) AND status IN ('draft','submitted','in_transit')", (warehouse_id, warehouse_id))
                pending = cursor.fetchone() or {}
                cursor.execute("SELECT COUNT(*) AS pending FROM purchase_orders WHERE warehouse_id=%s AND status NOT IN ('closed','cancelled')", (warehouse_id,))
                purchase_pending = cursor.fetchone() or {}
                if float(balance.get("balance") or 0) != 0 or int(pending.get("pending") or 0) or int(purchase_pending.get("pending") or 0):
                    raise DomainError("WAREHOUSE_DISABLE_BLOCKED", "仓库存在库存或未完成业务，暂不能停用", 409)
            assignments = ",".join(f"{key}=%s" for key in clean)
            try:
                cursor.execute(f"UPDATE warehouses SET {assignments},row_version=row_version+1 WHERE id=%s AND row_version=%s", (*clean.values(), warehouse_id, expected_version))
            except pymysql.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise DomainError("WAREHOUSE_CODE_EXISTS", "当前企业仓库编码已存在", 409) from exc
                raise DomainError("WAREHOUSE_CONSTRAINT_INVALID", "仓库档案不符合数据库约束", 400) from exc
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "仓库档案已被其他人修改，请刷新后重试", 409)
            cursor.execute("SELECT id,organization_id,farm_id,area_id,code,name,location,status,row_version,created_at FROM warehouses WHERE id=%s", (warehouse_id,))
            row = dict(cursor.fetchone() or {})
            self.audit.write(connection, user_id=user_id, action="update_warehouse", object_type="warehouse", object_id=warehouse_id, object_ref=f"warehouse:{warehouse_id}", result="success", ip_address=None, module_code="warehouse", before=dict(before), after=row)
            return row

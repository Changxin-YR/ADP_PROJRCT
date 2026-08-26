from __future__ import annotations

from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError


class WarehouseMasterStoreMixin:
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
            cursor.execute("SELECT organization_id FROM farms WHERE id=%s AND status<>'archived'", (payload.get("farm_id"),))
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
            cursor.execute("SELECT id,organization_id,farm_id,area_id,code,name,location,status,created_at FROM warehouses WHERE id=%s", (warehouse_id,))
            return dict(cursor.fetchone() or {})

    def update_warehouse(self, warehouse_id: int, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM warehouses WHERE id=%s FOR UPDATE", (warehouse_id,))
            before = cursor.fetchone()
            if before is None:
                raise DomainError("WAREHOUSE_NOT_FOUND", "仓库不存在", 404)
            self._require_scope(user, before)
            clean = {key: value for key, value in payload.items() if key in {"farm_id", "area_id", "code", "name", "location", "status"}}
            if not clean:
                raise DomainError("WAREHOUSE_NO_CHANGES", "没有可保存的修改", 400)
            merged = {**before, **clean}
            cursor.execute("SELECT organization_id FROM farms WHERE id=%s AND status<>'archived'", (merged["farm_id"],))
            farm = cursor.fetchone()
            if farm is None or int(farm["organization_id"]) != int(before["organization_id"]):
                raise DomainError("WAREHOUSE_SCOPE_INVALID", "基地不属于当前企业", 400)
            self._validate_area(cursor, merged.get("area_id"), int(before["organization_id"]), int(merged["farm_id"]))
            self._require_write_scope(user, {**merged, "created_by": user_id})
            assignments = ",".join(f"{key}=%s" for key in clean)
            try:
                cursor.execute(f"UPDATE warehouses SET {assignments} WHERE id=%s", (*clean.values(), warehouse_id))
            except pymysql.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise DomainError("WAREHOUSE_CODE_EXISTS", "当前企业仓库编码已存在", 409) from exc
                raise DomainError("WAREHOUSE_CONSTRAINT_INVALID", "仓库档案不符合数据库约束", 400) from exc
            cursor.execute("SELECT id,organization_id,farm_id,area_id,code,name,location,status,created_at FROM warehouses WHERE id=%s", (warehouse_id,))
            return dict(cursor.fetchone() or {})

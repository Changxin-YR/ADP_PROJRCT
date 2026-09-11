from __future__ import annotations

from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.common.security.data_scope import row_in_scope, scope_predicate


REQUISITION_WRITE_FIELDS = {"code", "name", "material_id", "quantity", "warehouse_id", "reason", "alert_key"}
REQUISITION_SELECT = (
    "SELECT q.*,m.name AS material_name,m.unit AS material_unit,"
    "w.name AS warehouse_name,o.code AS converted_order_code,o.status AS converted_order_status"
    " FROM purchase_requisitions q"
    " JOIN materials m ON m.id=q.material_id"
    " LEFT JOIN warehouses w ON w.id=q.warehouse_id"
    " LEFT JOIN purchase_orders o ON o.id=q.converted_order_id"
)
REQUISITION_SORT = {"code": "q.code", "name": "q.name", "quantity": "q.quantity", "status": "q.status", "updated_at": "q.updated_at"}


def _sort_clause(sort_by: str | None, sort_dir: str | None) -> str:
    """Build ORDER BY from a fixed column map; client input never reaches SQL."""
    column = REQUISITION_SORT.get(str(sort_by or ""), "q.updated_at")
    direction = "ASC" if str(sort_dir or "").lower() == "asc" else "DESC"
    return f"{column} {direction},q.id DESC"


class MySqlPurchaseRequisitionStore:
    """请购单存储：一张请购单最多转换出一张采购单。"""

    def __init__(self, settings: Any, purchase: Any = None) -> None:
        self.settings = settings
        # 转换动作复用采购单 store 的 _scoped/_payload/_get/_audit，避免第二套主数据校验。
        self.purchase = purchase

    @staticmethod
    def _scope(user: dict[str, Any]) -> tuple[str, list[Any]]:
        return scope_predicate(user, "q")

    @staticmethod
    def _require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        if not row_in_scope(user, row):
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的请购单", 403)

    @staticmethod
    def _payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in payload.items()
            if key in REQUISITION_WRITE_FIELDS | {"organization_id", "farm_id", "area_id"} and value != ""
        }

    def _get(self, cursor: Any, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT * FROM purchase_requisitions WHERE id=%s" + (" FOR UPDATE" if lock else ""), (record_id,))
        return cursor.fetchone()

    def _resolve_scope(self, cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        """请购单的组织/基地/区域取自物料与目标仓库，与采购单同一套主数据校验。"""
        result = dict(payload)
        cursor.execute("SELECT organization_id FROM materials WHERE id=%s AND status='verified'", (result.get("material_id"),))
        material = cursor.fetchone()
        if material is None:
            raise DomainError("PURCHASE_MASTER_DATA_INVALID", "物料不存在或未核验", 400)
        organization_id = int(material["organization_id"])
        warehouse_id = result.get("warehouse_id")
        if warehouse_id:
            cursor.execute(
                "SELECT organization_id,farm_id,area_id FROM warehouses WHERE id=%s AND status='active'",
                (warehouse_id,),
            )
            warehouse = cursor.fetchone()
            if warehouse is None or int(warehouse["organization_id"]) != organization_id:
                raise DomainError("PURCHASE_MASTER_DATA_INVALID", "请购仓库不存在、已停用或与物料不属于同一企业", 400)
            result.update(warehouse)
        else:
            for key in ("farm_id", "area_id"):
                result.pop(key, None)
        if not result.get("farm_id"):
            raise DomainError("PURCHASE_REQUISITION_FARM_REQUIRED", "请购单必须指定目标仓库或所属基地", 400)
        return result

    def get_requisition(self, record_id: int, *, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, record_id)
            if row is not None and user is not None:
                self._require_scope(user, row)
            return row

    def list_requisitions(
        self, *, user: dict[str, Any], page: int = 1, page_size: int = 20,
        status: str | None = None, search: str | None = None,
        sort_by: str | None = None, sort_dir: str | None = None, **_: Any,
    ) -> dict[str, Any]:
        clauses, values = ["1=1"], []
        scope, scoped = self._scope(user)
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("q.status=%s"); values.append(status)
        if search:
            clauses.append("(q.code LIKE %s OR q.name LIKE %s OR m.name LIKE %s)"); values.extend([f"%{search}%"] * 3)
        where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{REQUISITION_SELECT.split(' FROM ', 1)[1]} WHERE {where}", tuple(values))
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"{REQUISITION_SELECT} WHERE {where} ORDER BY {_sort_clause(sort_by, sort_dir)} LIMIT %s OFFSET %s",
                tuple(values + [page_size, (page - 1) * page_size]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def create_requisition(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scoped = self._resolve_scope(cursor, payload)
            self._require_scope(user, scoped)
            clean = {**self._payload(scoped), "status": "draft", "row_version": 1, "created_by": user_id}
            cursor.execute(
                f"INSERT INTO purchase_requisitions ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})",
                tuple(clean.values()),
            )
            record_id = int(cursor.lastrowid); row = self._get(cursor, record_id) or {}
            self.purchase._audit(connection, user_id, "create", "requisition", record_id, after=row)
            return row

    def update_requisition(
        self, record_id: int, payload: dict[str, Any], *,
        expected_version: int, user: dict[str, Any], user_id: int,
    ) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
            self._require_scope(user, before)
            scoped = self._resolve_scope(cursor, {**before, **payload})
            self._require_scope(user, scoped)
            clean = self._payload(payload)
            if not clean:
                raise DomainError("PURCHASE_REQUISITION_NO_CHANGES", "没有可保存的修改", 400)
            cursor.execute(
                f"UPDATE purchase_requisitions SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 "
                "WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')",
                (*clean.values(), user_id, record_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "请购单状态或版本已变化", 409)
            after = self._get(cursor, record_id) or {}
            self.purchase._audit(connection, user_id, "update", "requisition", record_id, before=before, after=after)
            return after

    @staticmethod
    def _requisition_work_items(connection: Any, cursor: Any, after: dict[str, Any], record_id: int, user_id: int) -> None:
        source_key = f"purchase:requisition:{record_id}:approve"
        if after["status"] == "submitted":
            cursor.execute(
                "INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) "
                "VALUES (%s,'purchase','approve','purchase:requisition',%s,%s,%s,%s,'pending',%s) "
                "ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)",
                (after["organization_id"], record_id, f"requisition:{record_id}", source_key,
                 f"审批请购单：{after['name']}", after["row_version"]),
            )
            notify_work_item_created(
                connection,
                organization_id=after["organization_id"],
                area_id=after.get("area_id"),
                module_code="purchase",
                action_code="approve",
                object_type="purchase:requisition",
                object_id=record_id,
                object_ref=f"requisition:{record_id}",
                source_key=source_key,
                title=f"审批请购单：{after['name']}",
                permission_codes=["purchase.verify"],
            )
        else:
            cursor.execute(
                "UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,"
                "completion_note='请购审批完成',row_version=row_version+1 "
                "WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')",
                (user_id, source_key),
            )

    def set_requisition_status(
        self, record_id: int, status: str, *,
        expected_version: int, user: dict[str, Any], user_id: int, reason: str | None = None,
    ) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
            self._require_scope(user, before)
            extra, params = "", [status, user_id]
            if status == "approved":
                extra = ",approved_by=%s,approved_at=CURRENT_TIMESTAMP"; params.append(user_id)
            elif status == "cancelled":
                extra = ",cancellation_reason=%s,cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP"
                params.extend([reason, user_id])
            params.extend([record_id, expected_version])
            cursor.execute(
                f"UPDATE purchase_requisitions SET status=%s,updated_by=%s{extra},row_version=row_version+1 "
                "WHERE id=%s AND row_version=%s",
                tuple(params),
            )
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "请购单状态或版本已变化", 409)
            after = self._get(cursor, record_id) or {}
            self._requisition_work_items(connection, cursor, after, record_id, user_id)
            self.purchase._audit(connection, user_id, status, "requisition", record_id, before=before, after=after)
            return after

    def convert_requisition(
        self, record_id: int, payload: dict[str, Any], *,
        expected_version: int, user: dict[str, Any], user_id: int,
    ) -> dict[str, Any]:
        """已审批的请购单转成采购单草稿；重复转换返回 409。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
            self._require_scope(user, before)
            if before["status"] == "converted" or before.get("converted_order_id"):
                raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409)
            if before["status"] != "approved":
                raise DomainError("INVALID_STATE_TRANSITION", "仅已审批的请购单可以转换为采购单", 409)
            cursor.execute(
                "SELECT id,status FROM purchase_orders WHERE requisition_id=%s AND status<>'cancelled'",
                (record_id,),
            )
            if cursor.fetchone() is not None:
                raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409)
            # 组织/基地/区域一律取自请购单，不允许跨基地转换。
            order_payload = {
                "code": before["code"], "name": before["name"], "material_id": before["material_id"],
                "quantity": before["quantity"], "supplier_id": payload.get("supplier_id"),
                "due_date": payload.get("due_date"), "unit_price": payload.get("unit_price"),
                "expected_delivery_date": payload.get("expected_delivery_date") or None,
                "organization_id": before["organization_id"], "farm_id": before["farm_id"],
                "area_id": before.get("area_id"),
                "warehouse_id": before.get("warehouse_id") or payload.get("warehouse_id"),
            }
            for key in ("due_date", "unit_price", "supplier_id", "warehouse_id"):
                if not order_payload.get(key):
                    raise DomainError("PURCHASE_REQUISITION_CONVERT_FIELDS", "转换采购单必须填写供应商、单价、交货仓和到期日", 400)
            scoped = self.purchase._scoped(cursor, order_payload)
            self.purchase._require_scope(user, scoped)
            clean = self.purchase._payload(scoped)
            clean.update(status="draft", row_version=1, created_by=user_id, requisition_id=record_id)
            try:
                cursor.execute(
                    f"INSERT INTO purchase_orders ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})",
                    tuple(clean.values()),
                )
            except pymysql.IntegrityError as exc:
                # 唯一键 uq_purchase_orders_requisition 兜底并发转换。
                raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409) from exc
            order_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE purchase_requisitions SET status='converted',converted_order_id=%s,converted_by=%s,"
                "converted_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s",
                (order_id, user_id, user_id, record_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "请购单状态或版本已变化", 409)
            order = self.purchase._get(cursor, order_id) or {}
            requisition = self._get(cursor, record_id) or {}
            self.purchase._audit(connection, user_id, "convert", "requisition", record_id, before=before, after=requisition)
            self.purchase._audit(connection, user_id, "create_from_requisition", "order", order_id, after=order)
            self._requisition_work_items(connection, cursor, requisition, record_id, user_id)
            return {"record": order, "requisition": requisition}

    def delete_requisition_draft(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, record_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
            self._require_scope(user, before)
            if before["status"] != "draft":
                raise DomainError("DELETE_NOT_ALLOWED", "仅草稿状态的请购单可以删除", 409)
            cursor.execute("DELETE FROM purchase_requisitions WHERE id=%s AND status='draft'", (record_id,))
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅草稿状态的请购单可以删除", 409)
            self.purchase._audit(connection, user_id, "delete_draft", "requisition", record_id, before=before)
            return before

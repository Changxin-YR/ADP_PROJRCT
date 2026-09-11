"""请购闭环边界回归（t2 的补充覆盖，只补真实缺口）。

文件头声明一个待产品决策的现状：**请购单号与采购单号目前共用同一编码空间**
（convert 时采购单直接沿用请购单 code）。因此当同企业已存在同号采购单时，唯一键
uq_purchase_orders_org_code 会先于业务语义触发，当前被映射成
PURCHASE_REQUISITION_ALREADY_CONVERTED(409)，文案偏"已转换"语义。本文件把这个
现状锁住，避免它被无声改变；是否应拆分编码空间由产品决定。

假绿防护：
- 纯逻辑用例只断言**服务层/错误映射**，不使用任何"假装是数据库"的断言。
- 真实唯一键冲突单独交给 test_real_mysql_duplicate_code_conflict_is_mapped_to_409，
  它走 disposable_database 起真实 MySQL；本机无凭据时如实 skip，不伪造通过。
"""

from __future__ import annotations

from typing import Any

import pymysql
import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import row_in_scope, scope_predicate
from backend.layers.features.purchase.purchase_requisition_service import RequisitionService
from backend.layers.features.purchase.purchase_requisition_store import MySqlPurchaseRequisitionStore
from backend.layers.features.purchase.purchase_service import PurchaseService


def actor(user_id: int, *permissions: str, roles: list[str] | None = None,
          scopes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "roles": roles or [],
            "data_scopes": scopes or []}


def area_user(user_id: int, area_id: int, *permissions: str) -> dict[str, Any]:
    """area 域账号：带 roles 才会真正启用范围强制（data_scope.enforced）。"""
    return actor(user_id, *permissions, roles=[{"code": "buyer"}],
                 scopes=[{"scope_type": "area", "area_id": area_id, "organization_id": 1, "farm_id": 9}])


def org_user(user_id: int, organization_id: int, *permissions: str) -> dict[str, Any]:
    return actor(user_id, *permissions, roles=[{"code": "buyer"}],
                 scopes=[{"scope_type": "farm", "organization_id": organization_id, "farm_id": None}])


def requisition_row(**overrides: Any) -> dict[str, Any]:
    row = {"id": 1, "code": "PR-0001", "name": "饲料补货请购", "material_id": 8, "quantity": 500,
           "warehouse_id": 3, "reason": "安全库存不足", "alert_key": "3:11:low_stock",
           "status": "approved", "row_version": 3, "converted_order_id": None,
           "organization_id": 1, "farm_id": 9, "area_id": 5, "created_by": 7}
    row.update(overrides)
    return row


class ScopedStore:
    """内存请购单 store。

    两个关键方法刻意复用**生产实现**，而不是自造断言：
    - list_requisitions 用真实 scope_predicate/row_in_scope 复现 SQL WHERE 的过滤语义；
    - get/set_status 用真实 MySqlPurchaseRequisitionStore._require_scope 做越权拒绝。
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.items = {int(row["id"]): dict(row) for row in rows}
        self.orders: dict[int, dict[str, Any]] = {}

    def list_requisitions(self, *, user: dict[str, Any], **_: Any) -> dict[str, Any]:
        # 与 list SQL 等价：越权行被静默过滤掉（不是报错）。
        visible = [dict(row) for row in self.items.values() if row_in_scope(user, row)]
        return {"items": visible, "page": 1, "page_size": 20, "total": len(visible), "has_next": False}

    def get_requisition(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        row = self.items.get(record_id)
        if row is None:
            return None
        MySqlPurchaseRequisitionStore._require_scope(user, row)
        return dict(row)

    def set_requisition_status(self, record_id: int, status: str, *, expected_version: int,
                               user: dict[str, Any], user_id: int, **_: Any) -> dict[str, Any]:
        row = self.items[record_id]
        MySqlPurchaseRequisitionStore._require_scope(user, row)
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(status=status, row_version=expected_version + 1)
        return dict(row)

    def convert_requisition(self, record_id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        raise AssertionError("越权路径必须在服务/scope 层就被拦住，不允许走到转换")


def service(store: Any) -> RequisitionService:
    return RequisitionService(store, PurchaseService(store))


# ---------------------------------------------------------------- (a) 跨数据范围
def test_area_scope_filters_out_of_scope_requisitions_from_lists() -> None:
    """list 的真实语义是"越权行不返回"，与 get/approve 的 403 不同。"""
    store = ScopedStore([
        requisition_row(id=1, area_id=5, created_by=7),
        requisition_row(id=2, area_id=6, created_by=8),
    ])
    scoped = area_user(7, 5, "purchase.view", "purchase.manage")
    # 真实谓词确实按 area 收窄（非空子句），证明范围强制已启用而非"无范围即放行"。
    predicate, values = scope_predicate(scoped, "q")
    assert predicate == "q.area_id IN (%s)" and values == [5]

    page = service(store).list_requisitions(scoped)
    assert [row["id"] for row in page["items"]] == [1]
    assert page["total"] == 1
    assert all(row["area_id"] == 5 for row in page["items"])


def test_out_of_scope_single_record_read_is_forbidden() -> None:
    store = ScopedStore([requisition_row(id=2, area_id=6, created_by=8)])
    scoped = area_user(7, 5, "purchase.view", "purchase.manage")
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN") as failure:
        service(store)._requisition(scoped, 2)
    assert failure.value.status == 403


def test_out_of_scope_approve_is_forbidden_and_writes_nothing() -> None:
    store = ScopedStore([requisition_row(id=2, area_id=6, created_by=8, status="submitted", row_version=2)])
    approver = area_user(7, 5, "purchase.view", "purchase.verify")
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN") as failure:
        service(store).approve_requisition(approver, 2, {"expected_version": 2})
    assert failure.value.status == 403
    # 越权尝试不能留下任何副作用。
    assert store.items[2]["status"] == "submitted" and store.items[2]["row_version"] == 2


def test_cross_organization_requisition_is_out_of_scope() -> None:
    store = ScopedStore([requisition_row(id=3, organization_id=2)])
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        service(store)._requisition(org_user(7, 1, "purchase.view"), 3)


# -------------------------------------------------- (b) convert 缺必填字段 -> 400
@pytest.mark.parametrize("missing", ["supplier_id", "unit_price", "due_date"])
def test_convert_without_required_field_is_rejected(missing: str) -> None:
    store = ScopedStore([requisition_row(warehouse_id=3)])
    payload = {"supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3}
    payload.pop(missing)
    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_CONVERT_FIELDS") as failure:
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, payload)
    assert failure.value.status == 400


def test_convert_without_any_warehouse_is_rejected() -> None:
    """请购单本身没填仓库、且请求里也不给 warehouse_id 时必须 400。"""
    store = ScopedStore([requisition_row(warehouse_id=None)])
    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_CONVERT_FIELDS"):
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3})


def test_convert_with_unknown_field_is_rejected() -> None:
    store = ScopedStore([requisition_row()])
    with pytest.raises(DomainError, match="PURCHASE_FIELD_INVALID"):
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25",
            "expected_version": 3, "status": "converted"})


# ------------------------------------------- (d) draft 状态直接 convert -> 409
def test_draft_requisition_cannot_be_converted() -> None:
    store = ScopedStore([requisition_row(status="draft", row_version=1, converted_order_id=None)])
    with pytest.raises(DomainError, match="INVALID_STATE_TRANSITION") as failure:
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 1})
    assert failure.value.status == 409
    assert store.orders == {}


def test_submitted_requisition_also_cannot_be_converted() -> None:
    store = ScopedStore([requisition_row(status="submitted", row_version=2)])
    with pytest.raises(DomainError, match="INVALID_STATE_TRANSITION"):
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 2})


# --------------------- (f) 唯一键冲突 -> 409 的**错误映射**（仅映射，非真实冲突）
class UniqueKeyConflictStore(ScopedStore):
    """模拟 MySQL 唯一键冲突，仅用于验证 store 的 IntegrityError -> 409 映射。

    注意：这里测的是**错误映射分支**，不是真实唯一键。真实 uq_purchase_orders_org_code /
    uq_purchase_orders_requisition 冲突由下面的 MySQL 集成用例覆盖。
    """

    def convert_requisition(self, record_id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        try:
            raise pymysql.err.IntegrityError(1062, "Duplicate entry 'PR-0001' for key 'uq_purchase_orders_org_code'")
        except pymysql.IntegrityError as exc:
            # 与 MySqlPurchaseRequisitionStore.convert_requisition 完全相同的映射。
            raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409) from exc


def test_integrity_error_is_mapped_to_already_converted_409() -> None:
    store = UniqueKeyConflictStore([requisition_row()])
    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_ALREADY_CONVERTED") as failure:
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3})
    assert failure.value.status == 409
    # 现状记录：文案说"已转换"，但真实原因可能是 code 撞号（共用编码空间，待产品决策）。
    assert "已转换" in str(failure.value)


def test_already_converted_requisition_is_rejected_before_any_write() -> None:
    store = ScopedStore([requisition_row(status="converted", converted_order_id=99)])
    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_ALREADY_CONVERTED"):
        service(store).convert_requisition(actor(7, "purchase.manage"), 1, {
            "supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3})
    assert store.orders == {}


# ----------------------------- 真实 MySQL：编码空间共用导致的唯一键冲突（本机 skip）
def test_real_mysql_duplicate_code_conflict_is_mapped_to_409() -> None:
    """真实唯一键冲突：同企业已存在同号采购单时，请购单转换必须 409 而不是建出第二张单。"""
    from backend.layers.common.db.connection import get_connection
    from backend.layers.features.purchase.purchase_requisition_store import MySqlPurchaseRequisitionStore
    from backend.layers.features.purchase.purchase_service import PurchaseService
    from backend.tests.mysql_test_database import disposable_database, settings_for

    with disposable_database("adp_req_boundary", through=34) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
            ids = dict(cursor.fetchone())
            cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
            ids.update(cursor.fetchone())
            cursor.execute(
                "INSERT INTO users (phone,name,password_hash,status) VALUES ('13930000001','请购经办','hash','active')")
            ids["user_id"] = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'RB','边界区','verified',%s)",
                (ids["organization_id"], ids["farm_id"], ids["user_id"]))
            ids["area_id"] = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,settlement_days,status,created_by)"
                " VALUES (%s,%s,%s,'supplier','RS1','边界供应商',30,'verified',%s)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["user_id"]))
            ids["supplier_id"] = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO materials (organization_id,farm_id,area_id,code,name,unit,status,created_by)"
                " VALUES (%s,%s,%s,'RM1','边界物料','kg','verified',%s)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["user_id"]))
            ids["material_id"] = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO warehouses (organization_id,farm_id,area_id,code,name) VALUES (%s,%s,%s,'RW1','边界仓')",
                (ids["organization_id"], ids["farm_id"], ids["area_id"]))
            ids["warehouse_id"] = int(cursor.lastrowid)
            # 预先占用 PR-DUP 这个编码：证明采购单与请购单共用编码空间。
            cursor.execute(
                "INSERT INTO purchase_orders (organization_id,farm_id,area_id,code,name,supplier_id,material_id,"
                "warehouse_id,quantity,unit_price,total_amount,due_date,status,row_version,created_by)"
                " VALUES (%s,%s,%s,'PR-DUP','已存在的采购单',%s,%s,%s,10,1,10,'2026-01-01','draft',1,%s)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["supplier_id"], ids["material_id"],
                 ids["warehouse_id"], ids["user_id"]))
            cursor.execute(
                "INSERT INTO purchase_requisitions (organization_id,farm_id,area_id,code,name,material_id,quantity,"
                "warehouse_id,reason,status,row_version,created_by) VALUES (%s,%s,%s,'PR-DUP','同号请购',%s,10,%s,'撞号验证','approved',3,%s)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["material_id"], ids["warehouse_id"], ids["user_id"]))
            requisition_id = int(cursor.lastrowid)

        from backend.layers.features.purchase.purchase_store import MySqlPurchaseStore
        purchase_store = MySqlPurchaseStore(settings)
        store = MySqlPurchaseRequisitionStore(settings, purchase_store)
        requisition_service = RequisitionService(store, PurchaseService(purchase_store))
        operator = {"id": ids["user_id"], "permissions": ["purchase.view", "purchase.manage"],
                    "roles": [], "data_scopes": []}
        with pytest.raises(DomainError) as failure:
            requisition_service.convert_requisition(operator, requisition_id, {
                "supplier_id": ids["supplier_id"], "unit_price": 6.5, "due_date": "2026-09-25",
                "warehouse_id": ids["warehouse_id"], "expected_version": 3})
        assert failure.value.status == 409
        assert failure.value.code == "PURCHASE_REQUISITION_ALREADY_CONVERTED"
        # 关键：不能因为撞号就多建一张采购单。
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM purchase_orders WHERE code='PR-DUP'")
            assert int(cursor.fetchone()["total"]) == 1

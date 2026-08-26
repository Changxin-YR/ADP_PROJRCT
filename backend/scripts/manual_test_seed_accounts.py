from __future__ import annotations

from typing import Any

from werkzeug.security import generate_password_hash


ORG_CODE = "TEST-20260817-ORG"
FARM_CODE = "TEST-20260817-FARM"
AREA_CODES = ("TEST-20260817-AREA-EAST", "TEST-20260817-AREA-WEST")
POND_CODES = tuple(f"TEST-20260817-POND-{index:02d}" for index in range(1, 5))
MATERIALS = (
    ("TEST-20260817-MAT-FEED", "[测试]草鱼膨化饲料", "饲料", "kg"),
    ("TEST-20260817-MAT-SEED", "[测试]草鱼苗种", "苗种", "尾"),
    ("TEST-20260817-MAT-HEALTH", "[测试]水产动保物料", "动保", "kg"),
    ("TEST-20260817-MAT-EQUIP", "[测试]增氧设备配件", "设备", "件"),
)
ACCOUNTS = (
    ("test-admin", "19000001001", "[测试]超级管理员", "super_admin"),
    ("test-breed-manager", "19000001002", "[测试]养殖管理员", "breed_manager"),
    ("test-breed-worker", "19000001003", "[测试]养殖作业员", "breed_worker"),
    ("test-warehouse", "19000001004", "[测试]仓储管理员", "warehouse_manager"),
    ("test-purchaser", "19000001005", "[测试]采购人员", "purchaser"),
    ("test-finance", "19000001006", "[测试]财务人员", "finance_staff"),
    ("test-sales", "19000001007", "[测试]销售人员", "sales_staff"),
)


def _id(
    cursor: Any,
    select_sql: str,
    select_params: tuple[object, ...],
    insert_sql: str,
    insert_params: tuple[object, ...],
) -> int:
    cursor.execute(select_sql, select_params)
    row = cursor.fetchone()
    if row:
        return int(row["id"])
    cursor.execute(insert_sql, insert_params)
    return int(cursor.lastrowid)


def _seed_users(cursor: Any, password: str) -> dict[str, int]:
    password_hash = generate_password_hash(password, method="scrypt")
    role_ids: dict[str, int] = {}
    for _, _, _, role_code in ACCOUNTS:
        cursor.execute("SELECT id FROM roles WHERE code=%s AND status='active'", (role_code,))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"Required role not found: {role_code}")
        role_ids[role_code] = int(row["id"])

    user_ids: dict[str, int] = {}
    for login, phone, name, role_code in ACCOUNTS:
        user_id = _id(
            cursor,
            "SELECT id FROM users WHERE login_name=%s",
            (login,),
            "INSERT INTO users (login_name,phone,name,password_hash,status) VALUES (%s,%s,%s,%s,'active')",
            (login, phone, name, password_hash),
        )
        cursor.execute(
            "INSERT IGNORE INTO user_roles (user_id,role_id) VALUES (%s,%s)",
            (user_id, role_ids[role_code]),
        )
        user_ids[login] = user_id
    return user_ids


def _seed_scope(cursor: Any, user_ids: dict[str, int]) -> None:
    scope_id = _id(
        cursor,
        "SELECT id FROM data_scopes WHERE code=%s",
        (f"{FARM_CODE}-ALL",),
        "INSERT INTO data_scopes (code,name,scope_type,area_id,status) VALUES (%s,%s,'farm',NULL,'active')",
        (f"{FARM_CODE}-ALL", "[测试]养殖场全部数据"),
    )
    admin_id = user_ids["test-admin"]
    for user_id in user_ids.values():
        cursor.execute(
            "INSERT IGNORE INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)",
            (user_id, scope_id, admin_id),
        )


def _seed_farm(cursor: Any, user_ids: dict[str, int]) -> tuple[int, int, list[int]]:
    admin_id = user_ids["test-admin"]
    organization_id = _id(
        cursor,
        "SELECT id FROM organizations WHERE code=%s",
        (ORG_CODE,),
        "INSERT INTO organizations (code,name,status) VALUES (%s,%s,'active')",
        (ORG_CODE, "[测试]水产养殖有限公司"),
    )
    farm_id = _id(
        cursor,
        "SELECT id FROM farms WHERE organization_id=%s AND code=%s",
        (organization_id, FARM_CODE),
        "INSERT INTO farms (organization_id,code,name,status,created_by) VALUES (%s,%s,%s,'verified',%s)",
        (organization_id, FARM_CODE, "[测试]示范养殖场", admin_id),
    )
    area_ids = []
    for index, code in enumerate(AREA_CODES):
        area_ids.append(_id(
            cursor,
            "SELECT id FROM areas WHERE code=%s",
            (code,),
            "INSERT INTO areas (organization_id,farm_id,code,name,status,sort_order,created_by) VALUES (%s,%s,%s,%s,'verified',%s,%s)",
            (organization_id, farm_id, code, f"[测试]{'东' if index == 0 else '西'}区", (index + 1) * 10, admin_id),
        ))
    return organization_id, farm_id, area_ids


def _seed_master_data(
    cursor: Any,
    user_ids: dict[str, int],
    organization_id: int,
    farm_id: int,
    area_ids: list[int],
) -> None:
    manager_id = user_ids["test-breed-manager"]
    for index, code in enumerate(POND_CODES):
        area_id = area_ids[0 if index < 2 else 1]
        _id(
            cursor,
            "SELECT id FROM ponds WHERE farm_id=%s AND code=%s",
            (farm_id, code),
            "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,description,location_text,species,manager_name,capacity_mu,pond_status,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'farming','verified',%s)",
            (organization_id, farm_id, area_id, code, f"[测试]{index + 1:02d}号塘", "人工测试专用塘口", f"测试区-{index + 1}", "草鱼", "测试养殖管理员", 12 + index, manager_id),
        )

    supplier_id = _id(
        cursor,
        "SELECT id FROM business_partners WHERE organization_id=%s AND partner_type='supplier' AND code=%s",
        (organization_id, "TEST-20260817-SUPPLIER"),
        "INSERT INTO business_partners (organization_id,farm_id,partner_type,code,name,contact_name,phone,address,status,created_by) VALUES (%s,%s,'supplier',%s,%s,%s,%s,%s,'verified',%s)",
        (organization_id, farm_id, "TEST-20260817-SUPPLIER", "[测试]水产物资供应商", "测试供应商联系人", "19000002001", "测试地址", user_ids["test-purchaser"]),
    )
    _id(
        cursor,
        "SELECT id FROM business_partners WHERE organization_id=%s AND partner_type='customer' AND code=%s",
        (organization_id, "TEST-20260817-CUSTOMER"),
        "INSERT INTO business_partners (organization_id,farm_id,partner_type,code,name,contact_name,phone,address,status,created_by) VALUES (%s,%s,'customer',%s,%s,%s,%s,%s,'verified',%s)",
        (organization_id, farm_id, "TEST-20260817-CUSTOMER", "[测试]鲜活水产客户", "测试客户联系人", "19000002002", "测试地址", user_ids["test-sales"]),
    )
    for code, name, category, unit in MATERIALS:
        _id(
            cursor,
            "SELECT id FROM materials WHERE organization_id=%s AND code=%s",
            (organization_id, code),
            "INSERT INTO materials (organization_id,farm_id,code,name,category,unit,safety_stock,default_supplier_id,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,100,%s,'verified',%s)",
            (organization_id, farm_id, code, name, category, unit, supplier_id, user_ids["test-warehouse"]),
        )
    _id(
        cursor,
        "SELECT id FROM warehouses WHERE organization_id=%s AND code=%s",
        (organization_id, "TEST-20260817-WAREHOUSE"),
        "INSERT INTO warehouses (organization_id,farm_id,code,name,location,status) VALUES (%s,%s,%s,%s,%s,'active')",
        (organization_id, farm_id, "TEST-20260817-WAREHOUSE", "[测试]综合仓库", "测试养殖场内"),
    )


def seed_accounts(cursor: Any, password: str) -> dict[str, object]:
    user_ids = _seed_users(cursor, password)
    _seed_scope(cursor, user_ids)
    organization_id, farm_id, area_ids = _seed_farm(cursor, user_ids)
    _seed_master_data(cursor, user_ids, organization_id, farm_id, area_ids)
    return {
        "organization": ORG_CODE,
        "farm": FARM_CODE,
        "accounts": [login for login, *_ in ACCOUNTS],
        "areas": len(AREA_CODES),
        "ponds": len(POND_CODES),
        "materials": len(MATERIALS),
    }

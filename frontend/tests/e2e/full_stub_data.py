"""Playwright 全流程桩服务的固定测试数据。"""

ROLES = [
    {"id": 1, "code": "super_admin", "name": "超级管理员", "description": "平台级账号管理、审核与系统配置"},
    {"id": 2, "code": "breed_manager", "name": "养殖管理员", "description": "全场/区域养殖生产管理"},
    {"id": 3, "code": "breed_worker", "name": "养殖作业员", "description": "投喂、巡塘、水质检测等日常作业"},
    {"id": 4, "code": "warehouse_manager", "name": "仓储管理员", "description": "物资出入库与库存管理"},
    {"id": 5, "code": "purchaser", "name": "采购人员", "description": "采购订单、供应商与应付管理"},
    {"id": 6, "code": "finance_staff", "name": "财务人员", "description": "费用审核、成本核算与资金管理"},
    {"id": 7, "code": "sales_staff", "name": "销售人员", "description": "销售订单、客户与应收管理"},
]
AREAS = [
    {"id": 1, "code": "north-farm", "name": "北区基地"},
    {"id": 2, "code": "south-farm", "name": "南区基地"},
]
SCOPES = [
    {"id": 1, "code": "farm-all", "name": "全场数据（所有基地）", "scope_type": "farm", "area_id": None, "area_name": None},
    {"id": 2, "code": "north-farm-all", "name": "北区基地全部数据", "scope_type": "area", "area_id": 1, "area_name": "北区基地"},
    {"id": 3, "code": "south-farm-all", "name": "南区基地全部数据", "scope_type": "area", "area_id": 2, "area_name": "南区基地"},
    {"id": 4, "code": "personal-self", "name": "仅本人数据", "scope_type": "personal", "area_id": None, "area_name": None},
]
ADMIN_USER = {
    "id": 1, "name": "系统管理员", "phone": "13800000000", "login_name": "admin", "status": "active",
    "roles": [{"id": 1, "code": "super_admin", "name": "超级管理员"}],
    "data_scopes": [{"id": 1, "code": "farm-all", "name": "全场数据（所有基地）"}],
    "permissions": [
        "workbench.enter", "work_item.view", "work_item.manage",
        "master_data.view", "master_data.manage", "master_data.verify",
        "warehouse.view", "warehouse.manage", "production.view", "production.manage",
        "purchase.view", "sales.view", "finance.payable.view", "finance.receivable.view",
        "cost.view", "cost.allocation.manage", "data_exchange.view",
        "auth.review", "auth.user.manage", "auth.role.manage", "audit.view", "auth.session.view",
    ],
}
# 仅查看、无 warehouse.manage 的账号：用于验证库存预警"处理"按钮隐藏
LIMITED_USER = {
    "id": 4, "name": "仓储查看员", "phone": "13900000002", "login_name": "viewer", "status": "active",
    "roles": [{"id": 4, "code": "warehouse_manager", "name": "仓储管理员"}],
    "data_scopes": [{"id": 1, "code": "farm-all", "name": "全场数据（所有基地）"}],
    "permissions": ["workbench.enter", "work_item.view", "warehouse.view"],
}
MANAGED_USERS = [
    {**ADMIN_USER, "created_at": "2026-08-01 09:00:00", "updated_at": "2026-08-10 09:00:00"},
    {"id": 2, "name": "李养殖", "phone": "13900000001", "login_name": "li", "status": "active",
     "roles": [{"id": 2, "code": "breed_manager", "name": "养殖管理员"}],
     "data_scopes": [{"id": 2, "code": "north-farm-all", "name": "北区基地全部数据"}],
     "created_at": "2026-08-02 09:00:00", "updated_at": "2026-08-09 09:00:00"},
    {"id": 3, "name": "王仓储", "phone": "13900000002", "login_name": "wang", "status": "active",
     "roles": [{"id": 4, "code": "warehouse_manager", "name": "仓储管理员"}],
     "data_scopes": [{"id": 4, "code": "personal-self", "name": "仅本人数据"}],
     "created_at": "2026-08-03 09:00:00", "updated_at": "2026-08-08 09:00:00"},
]
APPLICATIONS = [
    {"id": 11, "version_no": 1, "name": "赵销售", "phone": "13700000001", "desired_role_id": 7, "area_id": 1,
     "desired_scope_type": "personal", "application_note": "应聘销售人员", "status": "pending",
     "desired_role_name": "销售人员", "area_name": "北区基地", "created_at": "2026-08-14 10:00:00",
     "submitted_at": "2026-08-14 10:00:00", "updated_at": "2026-08-14 10:00:00"},
    {"id": 12, "version_no": 1, "name": "钱财务", "phone": "13700000002", "desired_role_id": 6, "area_id": 2,
     "desired_scope_type": "farm", "application_note": "应聘财务人员", "status": "pending",
     "desired_role_name": "财务人员", "area_name": "南区基地", "created_at": "2026-08-15 11:00:00",
     "submitted_at": "2026-08-15 11:00:00", "updated_at": "2026-08-15 11:00:00"},
]

COST_CATEGORIES = [
    (1, "pond_rent", "塘租", "public", "120000.00", "17.8571", "area"),
    (2, "equipment", "设备", "public", "38000.00", "5.6548", "equipment_count"),
    (3, "infrastructure", "基础建设", "public", "46000.00", "6.8452", "area"),
    (4, "labor", "人工", "public", "144000.00", "21.4286", "work_scope"),
    (5, "electricity", "电费", "public", "42000.00", "6.2500", "runtime_hours"),
    (6, "seed", "苗种", "direct", "96000.00", "14.2857", "direct_input"),
    (7, "feed", "饲料", "direct", "128000.00", "19.0476", "direct_consumption"),
    (8, "health", "动保", "direct", "26000.00", "3.8690", "direct_consumption"),
    (9, "other", "其他费用", "public", "32000.00", "4.7619", "equal"),
]
COST_ROWS = [
    {"id": row[0], "code": row[1], "name": row[2], "nature": row[3], "amount": row[4], "share": row[5], "allocation_driver": row[6]}
    for row in COST_CATEGORIES
]
COST_ENTRIES = [
    {
        "id": row["id"], "category_code": row["code"], "category_name": row["name"], "amount": row["amount"],
        "occurred_on": "2026-08-15", "period_start": "2026-01-01", "period_end": "2026-08-15",
        "status": "confirmed", "source_type": "legacy_import", "source_ref": "LEGACY-INIT-2026",
        "source_detail_json": {"note": "从既有成本构成页面迁移的初始化口径"},
    }
    for row in COST_ROWS
]
RULE_VERSIONS = [{
    "number": 1,
    "reason": "初始化九类成本分摊规则",
    "effective_from": "2026-01-01",
    "drivers": {row["id"]: row["allocation_driver"] for row in COST_ROWS},
}]
PONDS = [
    {
        "id": 1, "code": "P-001", "name": "一号塘", "area_id": 1, "area_name": "北区基地",
        "pond_group_id": 1, "group_name": "北区一组", "species": "鲈鱼", "capacity_mu": 8.5,
        "pond_status": "farming", "status": "verified", "row_version": 3, "version": 3,
        "location_text": "北区东侧", "manager_name": "李养殖", "description": "主养鲈鱼",
        "water_source": "外河水", "active_batch_count": 1,
        "aerator_count": 4, "stocking_spec": "5cm/尾", "current_spec": "350g/尾",
        "stock_quantity": 12000, "stock_quantity_source": "sampling",
        "allowed_actions": ["view", "edit"],
        "timeline_preview": [],
        "status_change_targets": ["rest", "clean"],
        "can_request_status_change": False, "can_verify_status_change": False,
        "pending_status_change": None,
    },
]
AREAS_STUB = [{"id": 1, "code": "north-farm", "name": "北区基地"}, {"id": 2, "code": "south-farm", "name": "南区基地"}]
POND_GROUPS_STUB = [{"id": 1, "code": "north-g1", "name": "北区一组", "area_id": 1}]
WORK_ITEMS_STUB = [
    {
        "id": 11, "title": "核验塘口档案 P-001", "detail": "塘口档案待核验", "module_code": "master_data",
        "action_code": "verify", "object_type": "master:ponds", "object_id": 1, "priority": "high",
        "status": "pending", "due_at": "2026-08-10 10:00:00", "overdue": True, "row_version": 1,
        "handling_mode": "manual",
    },
    {
        "id": 12, "title": "核验入库单 IN-031", "detail": "入库单待核验", "module_code": "warehouse",
        "action_code": "verify", "object_type": "warehouse:in", "object_id": 31, "priority": "normal",
        "status": "pending", "due_at": "2026-08-11 10:00:00", "overdue": True, "row_version": 1,
        "handling_mode": "domain",
    },
]
NOTIFICATIONS_STUB = [
    {
        "id": 21, "title": "低库存预警：鲈鱼饲料", "body": "一号仓 鲈鱼饲料 低于安全库存", "module_code": "warehouse",
        "level": "high", "status": "unread", "last_occurred_at": "2026-08-16 08:30:00", "occurrence_count": 2,
    },
]
ALERTS_STUB = [
    {
        "id": 8, "alert_key": "1:8:low_stock", "material_name": "鲈鱼饲料", "lot_no": "LOT-8",
        "warehouse_name": "一号仓", "alert_type": "low_stock", "severity": "high",
        "current_quantity": 2, "safety_stock": 10, "expiry_date": "2027-02-28",
        "status": "pending", "allowed_actions": ["handle"],
    },
    {
        "id": 9, "alert_key": "1:9:expiring", "material_name": "消毒剂", "lot_no": "LOT-9",
        "warehouse_name": "一号仓", "alert_type": "expiring", "severity": "medium",
        "current_quantity": 20, "safety_stock": 5, "expiry_date": "2026-08-25",
        "status": "pending", "allowed_actions": ["handle"],
    },
]
AUTH_STATE = {"authenticated": False}

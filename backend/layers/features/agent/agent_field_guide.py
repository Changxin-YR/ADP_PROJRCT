"""把「这个接口到底允许填哪些字段」告诉模型。

起因：线上 2026-09-11 智能体写塘口时传了 ``{area: 11.2, group_id: 5}``，被
``MASTER_FIELD_INVALID`` 拒了——因为塘口档案认的是 ``capacity_mu``、``pond_group_id``。
模型当时拿到的工具说明只有一个不透明的 ``payload`` 对象，字段全靠猜。

字段清单本身在业务层已经有一份（``MASTER_FIELDS`` / ``FIELDS`` / ``EXPENSE_FIELDS`` …），
这里只做「取出来 + 挂到工具上」，绝不另写第二份口径。
"""

from __future__ import annotations

from typing import Any

# --- 业务层已有的字段口径（不复制，直接引用） -----------------------------------------
from backend.layers.features.cost.cost_enterprise_validation import ASSET_FIELDS, EXPENSE_FIELDS
from backend.layers.features.master_data.master_data_service import MASTER_FIELDS
from backend.layers.features.production.production_service import FIELDS as PRODUCTION_FIELDS
from backend.layers.features.sales.sales_service import DELIVERY_FIELDS, ORDER_FIELDS as SALES_ORDER_FIELDS
from backend.layers.features.purchase.purchase_service import ORDER_FIELDS as PURCHASE_ORDER_FIELDS
from backend.layers.features.warehouse.warehouse_store import FIELDS as WAREHOUSE_FIELDS

# 资源必须显式列出来：模型猜 resource 名字也要花一轮工具调用。
PRODUCTION_RESOURCES = ("samplings", "transfers", "losses", "harvests", "feed-plans", "feed-tasks", "feed-logs", "daily-operations", "batches")
MASTER_RESOURCES = ("farms", "areas", "pond-groups", "ponds", "materials", "suppliers", "customers", "settings")
WAREHOUSE_RESOURCES = ("issues", "receipts", "transfers", "stocktakes", "scraps", "warehouses", "alerts")

# 生产记录：不同单据的必填项不同，与 production_service.create 的校验保持一致。
# 与 production_service.create 的硬性校验一致：所有单据都要 code+name；批次额外要塘口+品种。
# 「数量或重量至少填一个」是二者其一的约束，不标成必填以免模型重复追问。
_PRODUCTION_REQUIRED: dict[str, tuple[str, ...]] = {
    "batches": ("code", "name", "pond_id", "species"),
}
# 与 master_data_service.create 的校验保持一致：只有编码和名称是硬性必填；
# 其余（farm_id/area_id/pond_group_id 等）由数据范围与业务校验决定，标成必填会误导模型乱填。
_MASTER_REQUIRED: dict[str, tuple[str, ...]] = {}

# 非通用路径的专用写接口。
_SPECIAL_TOOLS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "api.cost_create_expense_post_api_v1_cost_expenses": (tuple(sorted(EXPENSE_FIELDS)), ("category_code", "amount", "occurred_on", "period_start", "period_end", "source_type", "source_ref")),
    "api.cost_update_expense_patch_api_v1_cost_expenses_record_id": (tuple(sorted(EXPENSE_FIELDS)), ()),
    "api.cost_create_asset_post_api_v1_cost_assets": (tuple(sorted(ASSET_FIELDS)), ("code", "name", "asset_type", "category_code", "purchase_date", "original_value")),
    "api.cost_update_asset_patch_api_v1_cost_assets_record_id": (tuple(sorted(ASSET_FIELDS)), ()),
    "api.purchase_create_order_post_api_v1_purchase_orders": (tuple(sorted(PURCHASE_ORDER_FIELDS)), ()),
    "api.sales_create_order_post_api_v1_sales_orders": (tuple(sorted(SALES_ORDER_FIELDS)), ()),
    "api.sales_create_delivery_post_api_v1_sales_deliveries": (tuple(sorted(DELIVERY_FIELDS)), ()),
    "api.production_change_batch_status_post_api_v1_production_batches_batch_id_status": (("batch_status", "reason", "expected_version"), ("batch_status", "reason")),
    "admin.update_role_permissions": (("permission_ids",), ("permission_ids",)),
    "admin.update_grants": (("role_ids", "data_scope_ids", "permissions"), ()),
    "admin.create_user": (("phone", "name", "login_name", "role_ids"), ("phone", "name")),
}


def _resource_of(path: str, arguments: dict[str, Any] | None = None) -> str:
    from backend.layers.features.agent.agent_humanize import resource_code

    payload = arguments if isinstance(arguments, dict) else {}
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return resource_code(path, {**body, **payload})


def field_spec(tool: Any, arguments: dict[str, Any] | None = None) -> tuple[list[str], list[str]] | None:
    """返回 (可用字段, 必填字段)；拿不到就返回 None，调用方据此省略。"""
    name = str(getattr(tool, "name", "") or "")
    if name in _SPECIAL_TOOLS:
        allowed, required = _SPECIAL_TOOLS[name]
        return list(allowed), list(required)

    path = str(getattr(tool, "path_template", "") or "")
    allowed, required = _fields_for_resource(path, _resource_of(path, arguments))
    return (allowed, required) if allowed else None


def fields_by_resource(tool: Any) -> dict[str, list[str]]:
    """通用 ``{resource}`` 写接口：每个资源各自允许哪些字段，一次全给模型。"""
    path = str(getattr(tool, "path_template", "") or "")
    result: dict[str, list[str]] = {}
    for resource in resources_for(path):
        allowed, required = _fields_for_resource(path, resource)
        if allowed:
            result[resource] = [f"{name}!" if name in required else name for name in allowed]
    return result


def _fields_for_resource(path: str, resource: str) -> tuple[list[str], list[str]]:
    if "/api/v1/production/" in path and resource in PRODUCTION_FIELDS:
        allowed = sorted(field for field in PRODUCTION_FIELDS[resource] if field != "payload")
        return allowed, list(_PRODUCTION_REQUIRED.get(resource, ("code", "name")))
    if "/api/v1/master-data/" in path and resource in MASTER_FIELDS:
        return sorted(MASTER_FIELDS[resource]), list(_MASTER_REQUIRED.get(resource, ("code", "name")))
    if "/api/v1/warehouse/" in path and resource in WAREHOUSE_RESOURCES:
        return sorted(WAREHOUSE_FIELDS), []
    return [], []


def resources_for(path: str) -> list[str]:
    """路径里的 ``{resource}`` 可以填哪些值。"""
    if "/api/v1/production/{resource}" in path or path.startswith("/api/v1/production/{resource}"):
        return list(PRODUCTION_RESOURCES)
    if "/api/v1/master-data/{resource}" in path:
        return list(MASTER_RESOURCES)
    if "/api/v1/warehouse/{resource}" in path:
        return list(WAREHOUSE_RESOURCES)
    return []

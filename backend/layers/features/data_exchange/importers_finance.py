"""采购/销售/成本导入器：被 importers.IMPORTERS 注册表引用。"""

from __future__ import annotations

import calendar as _calendar
import json as _json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.import_refs import (
    _batch,
    _category,
    _date,
    _decimal,
    _fetch,
    _first_category,
    _first_farm,
    _first_warehouse,
    _int,
    _text,
    _warehouse,
    enforce_area_scope,
    scoped_area_defaults,
)


def import_purchase_order(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    warehouse_id = _int(row.get("warehouse_id"))
    if warehouse_id is None:
        raise DomainError("WAREHOUSE_REQUIRED", "采购导入必须明确填写仓库", 400)
    if not _text(row.get("due_date")) or _date(row.get("due_date")) is None:
        raise DomainError("DUE_DATE_REQUIRED", "采购导入必须填写有效付款到期日", 400)
    warehouse = _warehouse(cursor, organization_id, warehouse_id)
    enforce_area_scope(user, int(warehouse["area_id"] or 0))
    supplier = _fetch(cursor, "SELECT id FROM business_partners WHERE id=%s AND organization_id=%s AND partner_type='supplier' AND status='verified'", (_int(row.get("supplier_id")), organization_id))
    if supplier is None:
        raise DomainError("SUPPLIER_NOT_FOUND", "供应商不存在或不属于当前企业", 400)
    material = _fetch(cursor, "SELECT id FROM materials WHERE id=%s AND organization_id=%s AND status='verified'", (_int(row.get("material_id")), organization_id))
    if material is None:
        raise DomainError("MATERIAL_NOT_FOUND", "物料不存在或不属于当前企业", 400)
    quantity, unit_price = _decimal(row.get("quantity")), _decimal(row.get("unit_price"))
    total = (quantity * unit_price).quantize(Decimal("0.01"))
    due = _date(row.get("due_date"))
    cursor.execute(
        "INSERT INTO purchase_orders (organization_id,farm_id,area_id,code,name,supplier_id,material_id,warehouse_id,quantity,unit_price,total_amount,due_date,status,row_version,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, warehouse["farm_id"], warehouse["area_id"], row["code"], _text(row.get("name")) or str(row["code"]), row["supplier_id"], row["material_id"], warehouse_id, quantity, unit_price, total, due, user_id),
    )
    return "purchase:orders", int(cursor.lastrowid)


def import_payment(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    payment_method = _text(row.get("payment_method"))
    if payment_method not in {"bank_transfer", "cash", "check", "digital_wallet", "other"}:
        raise DomainError("PAYMENT_METHOD_REQUIRED", "付款导入必须填写有效付款方式", 400)
    payable = _fetch(cursor, "SELECT p.id,p.status,o.area_id FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id WHERE p.id=%s AND p.organization_id=%s", (_int(row.get("payable_id")), organization_id))
    if payable is None:
        raise DomainError("PAYABLE_NOT_FOUND", "应付账款不存在或不属于当前企业", 400)
    if payable["status"] not in {"unpaid", "partial"}:
        raise DomainError("PAYABLE_NOT_OPEN", "应付账款不存在或已经结清", 409)
    enforce_area_scope(user, int(payable["area_id"]) if payable.get("area_id") else None)
    cursor.execute(
        "INSERT INTO purchase_payments (organization_id,payable_id,code,name,amount,paid_at,payment_method,status,row_version,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, payable["id"], row["code"], _text(row.get("name")) or str(row["code"]), row["amount"], row["happened_at"], payment_method, user_id),
    )
    return "purchase:payments", int(cursor.lastrowid)


def import_sales_order(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    batch = _batch(cursor, organization_id, _int(row.get("batch_id")))
    enforce_area_scope(user, int(batch["area_id"]))
    customer = _fetch(cursor, "SELECT id FROM business_partners WHERE id=%s AND organization_id=%s AND partner_type='customer' AND status='verified'", (_int(row.get("customer_id")), organization_id))
    if customer is None:
        raise DomainError("CUSTOMER_NOT_FOUND", "客户不存在或不属于当前企业", 400)
    quantity, unit_price = _decimal(row.get("quantity")), _decimal(row.get("unit_price"))
    total = (quantity * unit_price).quantize(Decimal("0.01"))
    unit = _text(row.get("unit")) or "kg"
    sold_at = _date(row.get("sold_at"))
    due = _date(row.get("due_date"))
    if sold_at is None or due is None:
        raise DomainError("SALES_DATE_REQUIRED", "销售导入必须填写销售日期和收款到期日", 400)
    if due < sold_at:
        raise DomainError("SALES_DATE_INVALID", "收款到期日不能早于销售日期", 400)
    cursor.execute(
        "INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,row_version,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, batch["farm_id"], batch["area_id"], batch["pond_id"], batch["id"], customer["id"], row["code"], _text(row.get("name")) or str(row["code"]), batch["species"], quantity, unit, unit_price, total, sold_at, due, user_id),
    )
    return "sales:orders", int(cursor.lastrowid)


def import_customer_receipt(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    receivable = _fetch(cursor, "SELECT r.id,r.status,o.area_id FROM sales_receivables r JOIN sales_orders o ON o.id=r.sales_order_id WHERE r.id=%s AND r.organization_id=%s", (_int(row.get("receivable_id")), organization_id))
    if receivable is None:
        raise DomainError("RECEIVABLE_NOT_FOUND", "应收账款不存在或不属于当前企业", 400)
    if receivable["status"] not in {"unpaid", "partial"}:
        raise DomainError("RECEIVABLE_NOT_PAYABLE", "当前应收状态不能登记收款", 409)
    enforce_area_scope(user, int(receivable["area_id"]) if receivable.get("area_id") else None)
    cursor.execute(
        "INSERT INTO sales_receipts (organization_id,receivable_id,code,name,amount,received_at,receipt_method,status,row_version,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, receivable["id"], row["code"], _text(row.get("name")) or str(row["code"]), row["amount"], row["happened_at"], _text(row.get("receipt_method")) or "bank_transfer", user_id),
    )
    return "sales:receipts", int(cursor.lastrowid)


def import_expense(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    category_id = _category(cursor, _text(row.get("category_code")))
    if category_id is None:
        raise DomainError("COST_CATEGORY_INVALID", "成本分类不存在或已停用", 400)
    nature = _fetch(cursor, "SELECT default_nature FROM cost_categories WHERE id=%s", (category_id,))["default_nature"]
    scope = scoped_area_defaults(cursor, user, organization_id)
    farm_id = scope.get("farm_id") or _first_farm(cursor, organization_id)
    if farm_id is None:
        raise DomainError("COST_SCOPE_REQUIRED", "企业没有基地，无法登记费用", 400)
    occurred = _date(row.get("happened_at")) or date.today()
    period_start = occurred.replace(day=1)
    period_end = period_start.replace(day=_calendar.monthrange(occurred.year, occurred.month)[1])
    cursor.execute(
        "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,source_detail_json,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,'import',%s,NULL,%s)",
        (organization_id, farm_id, scope.get("area_id"), category_id, row["amount"], occurred, period_start, period_end, nature, row["code"], user_id),
    )
    return "cost:entries", int(cursor.lastrowid)


def import_asset(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int, asset_type: str, entity_type: str) -> tuple[str, int]:
    category_code = _text(row.get("category_code"))
    category_id = _category(cursor, category_code)
    if category_id is None:
        raise DomainError("COST_CATEGORY_INVALID", "资产导入必须填写有效成本分类", 400)
    scope = scoped_area_defaults(cursor, user, organization_id)
    farm_id = scope.get("farm_id") or _first_farm(cursor, organization_id)
    if farm_id is None:
        raise DomainError("COST_SCOPE_REQUIRED", "企业没有基地，无法登记资产", 400)
    purchase = _date(row.get("purchase_date") or row.get("happened_at"))
    depreciation_start = _date(row.get("depreciation_start_date"))
    if purchase is None or depreciation_start is None:
        raise DomainError("COST_ASSET_DATE_REQUIRED", "资产导入必须填写购买日期和折旧开始日", 400)
    if depreciation_start < purchase:
        raise DomainError("COST_ASSET_DATE_INVALID", "折旧开始日不能早于购买日期", 400)
    salvage = _decimal(row.get("salvage_value"))
    useful_life = _int(row.get("useful_life_months"))
    if useful_life is None or useful_life <= 0:
        raise DomainError("COST_ASSET_LIFE_INVALID", "资产导入必须填写大于 0 的使用寿命（月）", 400)
    if salvage < 0:
        raise DomainError("COST_ASSET_SALVAGE_INVALID", "预计残值不能为负数", 400)
    cursor.execute(
        "INSERT INTO cost_assets (organization_id,farm_id,area_id,code,name,asset_type,category_id,purchase_date,original_value,salvage_value,useful_life_months,depreciation_start_date,allocation_driver,status,row_version,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, farm_id, scope.get("area_id"), row["code"], row["name"], asset_type, category_id, purchase, row["amount"], salvage, useful_life, depreciation_start, _text(row.get("allocation_driver")) or "equal", user_id),
    )
    return entity_type, int(cursor.lastrowid)


def import_cost_adjustment(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    source_id = _int(row.get("source_id"))
    source = _fetch(cursor, "SELECT organization_id,farm_id,area_id,category_id,cost_nature,period_start,period_end FROM cost_entries WHERE id=%s", (source_id,))
    if source is None or int(source["organization_id"]) != organization_id:
        raise DomainError("COST_SOURCE_NOT_FOUND", "原成本记录不存在或不属于当前企业", 400)
    enforce_area_scope(user, int(source["area_id"]) if source.get("area_id") else None)
    detail = _json.dumps({"reason": _text(row.get("reason"))}, ensure_ascii=False)
    cursor.execute(
        "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,source_detail_json,reversal_of_id,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,'adjustment',%s,%s,%s,%s)",
        (organization_id, source["farm_id"], source.get("area_id"), source["category_id"], -abs(_decimal(row.get("amount"))), date.today(), source["period_start"], source["period_end"], source["cost_nature"], row["code"], detail, source_id, user_id),
    )
    return "cost:adjustments", int(cursor.lastrowid)



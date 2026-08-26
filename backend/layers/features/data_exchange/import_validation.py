"""导入预览的业务校验（BUG-008）：编号唯一、关联对象存在、非法状态/日期/金额。

被 DataExchangeService.preview 调用；错误逐行列+中文原因，确保「确认阶段才冲突」
的场景提前到预览阶段。写入逻辑见 importers.py。
"""

from __future__ import annotations

from typing import Any

from backend.layers.features.data_exchange.import_refs import _date, _decimal, _fetch, _int, _text

SALES_UNITS = {"kg", "jin", "tail"}
RECEIPT_METHODS = {"bank_transfer", "cash", "check", "digital_wallet", "other"}
ASSET_TYPES = {"equipment", "infrastructure", "lease"}

# 编号唯一性：template_code -> (表, 类型列, 类型值)。类型列用于同表多类型
# （生产单据 document_type / 往来单位 partner_type / 成本来源 source_type）。
CODE_UNIQUENESS: dict[str, tuple[str, str | None, str | None]] = {
    "ponds": ("ponds", None, None),
    "batches": ("production_batches", None, None),
    "stocking": ("production_batches", None, None),
    "samplings": ("production_documents", "document_type", "sampling"),
    "transfers": ("production_documents", "document_type", "transfer"),
    "losses": ("production_documents", "document_type", "loss"),
    "harvests": ("production_documents", "document_type", "harvest"),
    "feed-plans": ("production_documents", "document_type", "feed_plan"),
    "feed-tasks": ("production_documents", "document_type", "feed_task"),
    "feed-logs": ("production_documents", "document_type", "feed_log"),
    "daily-operations": ("production_documents", "document_type", "daily_operation"),
    "materials": ("materials", None, None),
    "receipts": ("warehouse_documents", "document_type", "receipt"),
    "issues": ("warehouse_documents", "document_type", "issue"),
    "warehouse-transfers": ("warehouse_documents", "document_type", "transfer"),
    "returns": ("warehouse_documents", "document_type", "return"),
    "stocktakes": ("warehouse_documents", "document_type", "stocktake"),
    "scraps": ("warehouse_documents", "document_type", "scrap"),
    "suppliers": ("business_partners", "partner_type", "supplier"),
    "customers": ("business_partners", "partner_type", "customer"),
    "purchase-orders": ("purchase_orders", None, None),
    "payments": ("purchase_payments", None, None),
    "sales-orders": ("sales_orders", None, None),
    "customer-receipts": ("sales_receipts", None, None),
    "expenses": ("cost_entries", "source_type", "import"),
    "assets": ("cost_assets", None, None),
    "leases": ("cost_assets", None, None),
    "cost-adjustments": ("cost_entries", "source_type", "adjustment"),
    "business-settings": ("business_settings", None, None),
}

# 关联对象存在性：template_code -> [(字段, 表, 中文名, 附加条件)]
REFERENCE_CHECKS: dict[str, list[tuple[str, str, str, str]]] = {
    "ponds": [("farm_id", "farms", "基地", ""), ("area_id", "areas", "区域", "")],
    "batches": [("pond_id", "ponds", "塘口", "")],
    "stocking": [("batch_id", "production_batches", "批次", "")],
    "samplings": [("batch_id", "production_batches", "批次", "")],
    "transfers": [("batch_id", "production_batches", "批次", ""), ("target_pond_id", "ponds", "目标塘口", "")],
    "losses": [("batch_id", "production_batches", "批次", "")],
    "harvests": [("batch_id", "production_batches", "批次", "")],
    "feed-plans": [("pond_id", "ponds", "塘口", "")],
    "feed-logs": [("pond_id", "ponds", "塘口", ""), ("material_id", "materials", "饲料", "")],
    "feed-tasks": [("assignee_id", "users", "作业员", "status='active'"), ("pond_id", "ponds", "塘口", "")],
    "daily-operations": [("pond_id", "ponds", "塘口", "")],
    "receipts": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "仓库", "status='active'")],
    "issues": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "仓库", "status='active'")],
    "warehouse-transfers": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "调出仓", "status='active'"), ("target_warehouse_id", "warehouses", "调入仓", "status='active'")],
    "returns": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "仓库", "status='active'")],
    "stocktakes": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "仓库", "status='active'")],
    "scraps": [("material_id", "materials", "物料", "status='verified'"), ("warehouse_id", "warehouses", "仓库", "status='active'")],
    "purchase-orders": [("supplier_id", "business_partners", "供应商", "partner_type='supplier'"), ("material_id", "materials", "物料", ""), ("warehouse_id", "warehouses", "收货仓", "status='active'")],
    "payments": [("payable_id", "purchase_payables", "应付账款", "")],
    "sales-orders": [("customer_id", "business_partners", "客户", "partner_type='customer'"), ("batch_id", "production_batches", "批次", "")],
    "customer-receipts": [("receivable_id", "sales_receivables", "应收账款", "")],
    "cost-adjustments": [("source_id", "cost_entries", "原成本记录", "")],
}

# 编号列名：cost_entries 用 source_ref 存业务编号。
CODE_COLUMN = {"cost_entries": "source_ref"}


def _error(number: int, column: str, message: str, value: Any = None) -> dict[str, Any]:
    return {"row": number, "column": column, "message": message, "value": value}


def validate_rows(cursor: Any, organization_id: int, template_code: str, rows: list[dict[str, Any]], row_numbers: list[int]) -> list[dict[str, Any]]:
    """预览阶段业务校验：编号唯一 + 关联对象存在 + 模板特定规则。"""
    errors: list[dict[str, Any]] = []
    spec = CODE_UNIQUENESS.get(template_code)
    if spec:
        table, type_column, type_value = spec
        code_column = CODE_COLUMN.get(table, "code")
        codes = [str(row["code"]).strip() for row in rows if _text(row.get("code"))]
        seen: set[str] = set()
        for row, number in zip(rows, row_numbers):
            text = _text(row.get("code"))
            if not text:
                continue
            if text in seen:
                errors.append(_error(number, "code", f"文件内业务编号重复：{text}", row.get("code")))
            seen.add(text)
        if codes:
            placeholders = ",".join(["%s"] * len(codes))
            if type_column:
                cursor.execute(
                    f"SELECT {code_column} FROM {table} WHERE organization_id=%s AND {type_column}=%s AND {code_column} IN ({placeholders})",
                    (organization_id, type_value, *codes),
                )
            else:
                cursor.execute(f"SELECT {code_column} FROM {table} WHERE organization_id=%s AND {code_column} IN ({placeholders})", (organization_id, *codes))
            existing = {str(row[code_column]) for row in cursor.fetchall()}
            for row, number in zip(rows, row_numbers):
                text = _text(row.get("code"))
                if text and text in existing:
                    errors.append(_error(number, "code", f"业务编号已存在：{text}，请更换编号后重新导入", row.get("code")))
    for field, table, label, extra in REFERENCE_CHECKS.get(template_code, []):
        ids = sorted({value for value in (_int(row.get(field)) for row in rows) if value})
        if not ids:
            continue
        placeholders = ",".join(["%s"] * len(ids))
        where = f" AND {extra}" if extra else ""
        if table == "users":
            cursor.execute(f"SELECT id FROM users WHERE id IN ({placeholders}){where}", tuple(ids))
        else:
            cursor.execute(f"SELECT id FROM {table} WHERE organization_id=%s AND id IN ({placeholders}){where}", (organization_id, *ids))
        existing = {int(row["id"]) for row in cursor.fetchall()}
        for row, number in zip(rows, row_numbers):
            value = _int(row.get(field))
            if value is not None and value not in existing:
                errors.append(_error(number, field, f"{label}不存在或不在当前企业范围：{value}", row.get(field)))
    special = SPECIAL_CHECKS.get(template_code)
    if special:
        for checker in (special if isinstance(special, list) else [special]):
            checker(cursor, organization_id, rows, row_numbers, errors)
    return errors


def _check_stocking(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    batch_ids = sorted({value for value in (_int(row.get("batch_id")) for row in rows) if value})
    if batch_ids:
        placeholders = ",".join(["%s"] * len(batch_ids))
        cursor.execute(f"SELECT b.id,b.status,c.id AS correction_id FROM production_batches b LEFT JOIN production_batches c ON c.correction_of_id=b.id WHERE b.organization_id=%s AND b.id IN ({placeholders})", (organization_id, *batch_ids))
        batches = {int(item["id"]): item for item in cursor.fetchall()}
        seen: set[int] = set()
        for row, number in zip(rows, row_numbers):
            batch_id = _int(row.get("batch_id"))
            batch = batches.get(batch_id or 0)
            if batch_id in seen:
                errors.append(_error(number, "batch_id", f"文件内同一批次只能有一条投苗更正：批次 {batch_id}", row.get("batch_id")))
            elif batch and batch["status"] != "verified":
                errors.append(_error(number, "batch_id", f"投苗导入只能关联已核验批次：批次 {batch_id}", row.get("batch_id")))
            elif batch and batch.get("correction_id"):
                errors.append(_error(number, "batch_id", f"该批次已有待处理或历史更正：批次 {batch_id}", row.get("batch_id")))
            if batch_id:
                seen.add(batch_id)


def _check_transfer_targets(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    for row, number in zip(rows, row_numbers):
        target = _int(row.get("target_pond_id"))
        batch_row = _fetch(cursor, "SELECT pond_id FROM production_batches WHERE id=%s AND organization_id=%s", (_int(row.get("batch_id")), organization_id))
        if target and batch_row and target == int(batch_row["pond_id"]):
            errors.append(_error(number, "target_pond_id", "转入塘口不能与批次当前塘口相同", row.get("target_pond_id")))


def _check_warehouse_transfer(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    del organization_id
    for row, number in zip(rows, row_numbers):
        source, target = _int(row.get("warehouse_id")), _int(row.get("target_warehouse_id"))
        if target is None:
            errors.append(_error(number, "target_warehouse_id", "调拨记录必须填写目标仓（调入仓）", row.get("target_warehouse_id")))
        elif source and target == source:
            errors.append(_error(number, "target_warehouse_id", "调入仓不能与调出仓相同", row.get("target_warehouse_id")))


def _check_payments(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    payable_ids = sorted({value for value in (_int(row.get("payable_id")) for row in rows) if value})
    if not payable_ids:
        return
    placeholders = ",".join(["%s"] * len(payable_ids))
    cursor.execute(
        f"SELECT p.id,p.amount,p.paid_amount,p.status,COALESCE((SELECT SUM(a.amount_delta) FROM purchase_payable_adjustments a WHERE a.payable_id=p.id),0) AS adjustment_total "
        f"FROM purchase_payables p WHERE p.organization_id=%s AND p.id IN ({placeholders})",
        (organization_id, *payable_ids),
    )
    payables = {int(row["id"]): row for row in cursor.fetchall()}
    for row, number in zip(rows, row_numbers):
        payable_id = _int(row.get("payable_id"))
        if not payable_id:
            continue
        payable = payables.get(payable_id)
        if payable is None:
            continue  # 已由关联校验报错
        if payable["status"] not in {"unpaid", "partial"}:
            errors.append(_error(number, "payable_id", f"应付账款当前状态（{payable['status']}）不能登记付款", row.get("payable_id")))
            continue
        balance = _decimal(payable["amount"]) + _decimal(payable["adjustment_total"]) - _decimal(payable["paid_amount"])
        if _decimal(row.get("amount")) > balance:
            errors.append(_error(number, "amount", f"付款金额不能超过应付余额 {balance}", row.get("amount")))


def _check_receipts(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    receivable_ids = sorted({value for value in (_int(row.get("receivable_id")) for row in rows) if value})
    if not receivable_ids:
        return
    placeholders = ",".join(["%s"] * len(receivable_ids))
    cursor.execute(f"SELECT id,status FROM sales_receivables WHERE organization_id=%s AND id IN ({placeholders})", (organization_id, *receivable_ids))
    receivables = {int(row["id"]): str(row["status"]) for row in cursor.fetchall()}
    for row, number in zip(rows, row_numbers):
        receivable_id = _int(row.get("receivable_id"))
        if not receivable_id or receivable_id not in receivables:
            continue
        if receivables[receivable_id] not in {"unpaid", "partial"}:
            errors.append(_error(number, "receivable_id", f"应收账款当前状态（{receivables[receivable_id]}）不能登记收款", row.get("receivable_id")))


def _check_warehouse_presence(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    for row, number in zip(rows, row_numbers):
        if _int(row.get("warehouse_id")) is None and _fetch(cursor, "SELECT id FROM warehouses WHERE organization_id=%s AND status='active' ORDER BY id LIMIT 1", (organization_id,)) is None:
            errors.append(_error(number, "warehouse_id", "企业没有可用仓库，请先在系统中维护仓库或填写仓库ID", row.get("warehouse_id")))


def _check_feed_task_pond(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    for row, number in zip(rows, row_numbers):
        if _int(row.get("pond_id")) is None and _fetch(cursor, "SELECT id FROM ponds WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,)) is None:
            errors.append(_error(number, "pond_id", "企业没有塘口，派工任务必须指定塘口", row.get("pond_id")))


def _check_sales_order(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    del cursor, organization_id
    for row, number in zip(rows, row_numbers):
        unit = _text(row.get("unit"))
        if unit and unit not in SALES_UNITS:
            errors.append(_error(number, "unit", f"销售单位仅支持：{'/'.join(sorted(SALES_UNITS))}", row.get("unit")))
        if _date(row.get("sold_at")) is None and _text(row.get("sold_at")):
            errors.append(_error(number, "sold_at", "日期格式必须为 YYYY-MM-DD", row.get("sold_at")))
        if _date(row.get("due_date")) is None and _text(row.get("due_date")):
            errors.append(_error(number, "due_date", "日期格式必须为 YYYY-MM-DD", row.get("due_date")))


def _check_receipt_method(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    del cursor, organization_id
    for row, number in zip(rows, row_numbers):
        method = _text(row.get("receipt_method"))
        if method and method not in RECEIPT_METHODS:
            errors.append(_error(number, "receipt_method", f"收款方式仅支持：{'/'.join(sorted(RECEIPT_METHODS))}", row.get("receipt_method")))


def _check_assets(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    del cursor, organization_id
    for row, number in zip(rows, row_numbers):
        asset_type = _text(row.get("asset_type"))
        if asset_type and asset_type not in ASSET_TYPES:
            errors.append(_error(number, "asset_type", f"资产类别仅支持：{'/'.join(sorted(ASSET_TYPES))}", row.get("asset_type")))


def _check_cost_category(cursor: Any, organization_id: int, rows: list[dict[str, Any]], row_numbers: list[int], errors: list[dict[str, Any]]) -> None:
    del organization_id
    codes = sorted({_text(row.get("category_code")) for row in rows if _text(row.get("category_code"))})
    if not codes:
        return
    placeholders = ",".join(["%s"] * len(codes))
    cursor.execute(f"SELECT code FROM cost_categories WHERE status='active' AND code IN ({placeholders})", tuple(codes))
    existing = {str(row["code"]) for row in cursor.fetchall()}
    for row, number in zip(rows, row_numbers):
        code = _text(row.get("category_code"))
        if code and code not in existing:
            errors.append(_error(number, "category_code", f"成本分类不存在或已停用：{code}", row.get("category_code")))


SPECIAL_CHECKS: dict[str, Any] = {
    "stocking": _check_stocking,
    "transfers": _check_transfer_targets,
    "warehouse-transfers": _check_warehouse_transfer,
    "payments": _check_payments,
    "customer-receipts": [_check_receipts, _check_receipt_method],
    "receipts": _check_warehouse_presence,
    "issues": _check_warehouse_presence,
    "returns": _check_warehouse_presence,
    "stocktakes": _check_warehouse_presence,
    "scraps": _check_warehouse_presence,
    "feed-tasks": _check_feed_task_pond,
    "sales-orders": _check_sales_order,
    "assets": [_check_assets, _check_cost_category],
    "leases": [_check_assets, _check_cost_category],
    "expenses": _check_cost_category,
}

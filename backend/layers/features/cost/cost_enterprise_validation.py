from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


EXPENSE_FIELDS = {
    "category_code", "amount", "occurred_on", "period_start", "period_end", "cost_nature",
    "source_type", "source_ref", "source_detail", "target_type", "target_id",
    "organization_id", "farm_id", "area_id", "evidence_attachment_ids",
}
ASSET_FIELDS = {
    "code", "name", "asset_type", "category_code", "purchase_date", "original_value",
    "salvage_value", "useful_life_months", "depreciation_start_date", "allocation_driver",
    "target_type", "target_id", "organization_id", "farm_id", "area_id", "note",
    "evidence_attachment_ids",
}


def clean_payload(payload: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DomainError("COST_PAYLOAD_INVALID", "请求内容必须是对象", 400)
    invalid = set(payload) - fields - {"expected_version"}
    if invalid:
        raise DomainError("COST_FIELD_INVALID", "请求包含不允许修改的字段", 400)
    return {key: value for key, value in payload.items() if key in fields and value != ""}


def money(value: Any, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError("COST_AMOUNT_INVALID", f"{field}金额无效", 400) from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero) or amount.quantize(Decimal("0.01")) != amount:
        raise DomainError("COST_AMOUNT_INVALID", f"{field}金额无效", 400)
    return amount


def positive_integer(value: Any, code: str, message: str) -> int:
    if isinstance(value, bool):
        raise DomainError(code, message, 400)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError(code, message, 400) from exc
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        raise DomainError(code, message, 400)
    return int(number)


def normalize_target(payload: dict[str, Any]) -> None:
    target_type, target_id = payload.get("target_type"), payload.get("target_id")
    if target_type is None and target_id is None:
        return
    if target_type not in {"farm", "area", "group", "pond", "batch"}:
        raise DomainError("COST_TARGET_INVALID", "成本归属对象类型无效", 400)
    payload["target_id"] = positive_integer(target_id, "COST_TARGET_INVALID", "成本归属对象编号无效")


def expense_payload(payload: Any, parse_dates: Any) -> dict[str, Any]:
    result = clean_payload(payload, EXPENSE_FIELDS)
    required = ("category_code", "amount", "occurred_on", "period_start", "period_end", "source_type", "source_ref")
    if not all(result.get(key) for key in required):
        raise DomainError("COST_REQUIRED_FIELDS", "费用必填信息不完整", 400)
    result["amount"] = money(result["amount"], "费用")
    start, end = parse_dates(result)
    try:
        occurred = date.fromisoformat(str(result["occurred_on"]))
    except ValueError as exc:
        raise DomainError("COST_DATE_INVALID", "费用日期格式无效", 400) from exc
    if not start <= occurred <= end:
        raise DomainError("COST_PERIOD_INVALID", "发生日期必须位于核算期间内", 400)
    result.update(occurred_on=occurred, period_start=start, period_end=end)
    normalize_target(result)
    return result


def asset_payload(payload: Any) -> dict[str, Any]:
    result = clean_payload(payload, ASSET_FIELDS)
    required = ("code", "name", "asset_type", "category_code", "purchase_date", "original_value", "useful_life_months", "depreciation_start_date")
    if not all(result.get(key) for key in required):
        raise DomainError("COST_ASSET_REQUIRED_FIELDS", "资产必填信息不完整", 400)
    result["original_value"] = money(result["original_value"], "资产原值")
    result["salvage_value"] = money(result.get("salvage_value", 0), "预计残值", allow_zero=True)
    if result["salvage_value"] >= result["original_value"]:
        raise DomainError("COST_ASSET_VALUE_INVALID", "预计残值必须小于资产原值", 400)
    result["useful_life_months"] = positive_integer(
        result["useful_life_months"], "COST_ASSET_LIFE_INVALID", "使用期限必须是大于零的整月数",
    )
    try:
        result["purchase_date"] = date.fromisoformat(str(result["purchase_date"]))
        result["depreciation_start_date"] = date.fromisoformat(str(result["depreciation_start_date"]))
    except (TypeError, ValueError) as exc:
        raise DomainError("COST_ASSET_DATE_INVALID", "资产日期无效", 400) from exc
    if result["depreciation_start_date"] < result["purchase_date"]:
        raise DomainError("COST_ASSET_DATE_INVALID", "折旧开始日不能早于购买日期", 400)
    normalize_target(result)
    return result

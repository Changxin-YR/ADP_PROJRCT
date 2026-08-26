from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def require_stock_measurement(payload: dict[str, Any], resource: str) -> None:
    values: list[Decimal] = []
    for field in ("quantity", "weight_kg"):
        value = payload.get(field)
        if value in (None, ""):
            values.append(Decimal("0")); continue
        try:
            values.append(Decimal(str(value)))
        except InvalidOperation as exc:
            raise DomainError("PRODUCTION_VALUE_INVALID", "数量和重量格式无效", 400) from exc
    if not any(value > 0 for value in values):
        raise DomainError("PRODUCTION_QUANTITY_REQUIRED", f"{resource}必须填写大于 0 的数量或重量", 400)


def validate_loss_reason(payload: dict[str, Any]) -> None:
    if not str(payload.get("reason") or payload.get("note") or "").strip():
        raise DomainError("PRODUCTION_LOSS_REASON_REQUIRED", "损耗必须填写原因", 400)


def validate_batch_seed(payload: dict[str, Any], *, creating: bool) -> None:
    quantity = Decimal(str(payload.get("initial_quantity") or 0))
    weight = Decimal(str(payload.get("initial_weight_kg") or 0))
    if quantity <= 0 and weight <= 0:
        raise DomainError("PRODUCTION_QUANTITY_REQUIRED", "批次必须填写大于 0 的初始数量或重量", 400)
    if creating and payload.get("batch_status") in {"closed", "pending_settlement"}:
        raise DomainError("PRODUCTION_BATCH_STATUS_INVALID", "新建批次不能直接进入关闭或待结算状态", 400)

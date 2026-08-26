from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.features.cost.calculation import summarize_costs, unit_production_cost


DRIVERS = {
    "area",
    "equipment_count",
    "runtime_hours",
    "direct_input",
    "direct_consumption",
    "work_scope",
    "manual_ratio",
    "equal",
}


class CostServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class CostService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def date_text(value: Any) -> str:
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    @classmethod
    def rule_payload(cls, version: dict[str, Any] | None) -> dict[str, Any] | None:
        if version is None:
            return None
        return {
            **version,
            "effective_from": cls.date_text(version["effective_from"]),
            "effective_to": cls.date_text(version["effective_to"]) if version.get("effective_to") else None,
        }

    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise CostServiceError("FORBIDDEN", "当前账号没有成本功能权限", 403)

    def structure(self, user: dict[str, Any], *, period_start: date, period_end: date) -> dict[str, Any]:
        self.require(user, "cost.view")
        rows = self.store.list_category_totals(period_start=period_start, period_end=period_end, user=user)
        result = summarize_costs(rows)
        facts = self.store.get_dashboard_facts(period_start=period_start, period_end=period_end, user=user)
        total = Decimal(result["total_amount"])
        output = Decimal(str(facts["output_weight_jin"]))
        income = Decimal(str(facts["income_amount"]))
        unit_cost = unit_production_cost(total, output)
        result.update(
            {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "confirmed_output_weight_jin": str(output.quantize(Decimal("0.001"))),
                "confirmed_income_amount": str(income.quantize(Decimal("0.01"))),
                "confirmed_profit_amount": str((income - total).quantize(Decimal("0.01"))),
                "unit_production_cost": unit_cost,
                "unit_cost_status": "available" if unit_cost is not None else "output_not_connected",
                "source_fact_counts": facts["source_fact_counts"],
                "source_quality": "legacy_import" if any(row.get("source_quality") == "legacy_import" for row in rows) else "verified",
            }
        )
        return result

    def entries(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "cost.view")
        result = self.store.list_entries(user=user, **query)
        return {
            **result,
            "items": [
                {
                    **item,
                    "amount": str(Decimal(str(item["amount"])).quantize(Decimal("0.01"))),
                    "occurred_on": self.date_text(item["occurred_on"]),
                    "period_start": self.date_text(item["period_start"]),
                    "period_end": self.date_text(item["period_end"]),
                }
                for item in result["items"]
            ],
        }

    @staticmethod
    def _entry_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CostServiceError("COST_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        try:
            amount = Decimal(str(payload.get("amount")))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise CostServiceError("COST_AMOUNT_INVALID", "金额必须是有效的正数", 400) from error
        if not amount.is_finite() or amount <= 0 or amount.quantize(Decimal("0.01")) != amount:
            raise CostServiceError("COST_AMOUNT_INVALID", "金额必须是大于 0 且最多两位小数", 400)
        try:
            occurred_on = date.fromisoformat(str(payload.get("occurred_on")))
            period_start = date.fromisoformat(str(payload.get("period_start")))
            period_end = date.fromisoformat(str(payload.get("period_end")))
        except ValueError as error:
            raise CostServiceError("COST_DATE_INVALID", "成本日期格式无效", 400) from error
        if period_start > period_end or not (period_start <= occurred_on <= period_end):
            raise CostServiceError("COST_PERIOD_INVALID", "发生日期必须位于核算期间内", 400)
        category_code = str(payload.get("category_code", "")).strip()
        source_type = str(payload.get("source_type", "")).strip()
        source_ref = str(payload.get("source_ref", "")).strip()
        if not category_code or not source_type or not source_ref:
            raise CostServiceError("COST_SOURCE_REQUIRED", "成本分类、来源类型和来源单号不能为空", 400)
        cost_nature = payload.get("cost_nature")
        if cost_nature is not None and cost_nature not in {"direct", "public"}:
            raise CostServiceError("COST_NATURE_INVALID", "成本性质只能是 direct 或 public", 400)
        target_type = payload.get("target_type")
        if target_type is not None and target_type not in {"farm", "area", "group", "pond", "batch"}:
            raise CostServiceError("COST_TARGET_INVALID", "成本归属对象类型无效", 400)
        try:
            target_id = int(payload["target_id"]) if payload.get("target_id") is not None else None
        except (TypeError, ValueError) as error:
            raise CostServiceError("COST_TARGET_INVALID", "成本归属对象编号无效", 400) from error
        return {
            "category_code": category_code,
            "amount": amount.quantize(Decimal("0.01")),
            "occurred_on": occurred_on,
            "period_start": period_start,
            "period_end": period_end,
            "cost_nature": cost_nature,
            "source_type": source_type,
            "source_ref": source_ref,
            "source_detail": payload.get("source_detail"),
            "target_type": target_type,
            "target_id": target_id,
        }

    @staticmethod
    def _entry_result(result: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(result)
        for field in ("amount",):
            if field in normalized and normalized[field] is not None:
                normalized[field] = str(Decimal(str(normalized[field])).quantize(Decimal("0.01")))
        for field in ("occurred_on", "period_start", "period_end", "confirmed_at", "created_at", "updated_at"):
            if normalized.get(field) is not None and hasattr(normalized[field], "isoformat"):
                normalized[field] = normalized[field].isoformat()
        return normalized

    def create_entry(self, user: dict[str, Any], payload: Any, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        result = self.store.create_entry(user_id=int(user["id"]), request_id=request_id, ip_address=ip_address, **self._entry_payload(payload))
        return self._entry_result(result)

    def update_draft(self, user: dict[str, Any], entry_id: int, payload: Any, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        try:
            result = self.store.update_draft(entry_id, user_id=int(user["id"]), request_id=request_id, ip_address=ip_address, **self._entry_payload(payload))
        except ValueError as error:
            raise CostServiceError("COST_DRAFT_EDIT_FAILED", str(error), 409) from error
        return self._entry_result(result)

    def submit_entry(self, user: dict[str, Any], entry_id: int, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        try:
            return self._entry_result(self.store.submit_entry(entry_id, user_id=int(user["id"]), request_id=request_id, ip_address=ip_address))
        except ValueError as error:
            raise CostServiceError("COST_SUBMIT_FAILED", str(error), 409) from error

    def confirm_entry(self, user: dict[str, Any], entry_id: int, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.verify")
        try:
            return self._entry_result(self.store.confirm_entry(entry_id, user_id=int(user["id"]), request_id=request_id, ip_address=ip_address))
        except ValueError as error:
            raise CostServiceError("COST_CONFIRM_FAILED", str(error), 409) from error

    def delete_draft(self, user: dict[str, Any], entry_id: int, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        try:
            return self._entry_result(self.store.delete_draft(entry_id, user_id=int(user["id"]), request_id=request_id, ip_address=ip_address))
        except ValueError as error:
            raise CostServiceError("COST_DRAFT_DELETE_FAILED", str(error), 409) from error

    def reverse_entry(self, user: dict[str, Any], entry_id: int, reason: Any, *, request_id: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
        self.require(user, "cost.entry.reverse")
        reason = str(reason or "").strip()
        if len(reason) < 2 or len(reason) > 500:
            raise CostServiceError("COST_REVERSAL_REASON_REQUIRED", "冲销必须填写 2-500 字的原因", 400)
        try:
            return self._entry_result(self.store.reverse_entry(entry_id, user_id=int(user["id"]), reason=reason, request_id=request_id, ip_address=ip_address))
        except ValueError as error:
            raise CostServiceError("COST_REVERSAL_FAILED", str(error), 409) from error

    def rules(self, user: dict[str, Any], *, effective_at: date) -> dict[str, Any] | None:
        self.require(user, "cost.view")
        return self.rule_payload(self.store.get_rule_version(effective_at=effective_at))

    def latest_rules(self, user: dict[str, Any]) -> dict[str, Any] | None:
        self.require(user, "cost.view")
        return self.rule_payload(self.store.get_latest_rule_version())

    def save_rules(self, user: dict[str, Any], payload: Any, *, ip_address: str) -> dict[str, Any] | None:
        self.require(user, "cost.allocation.manage")
        if not isinstance(payload, dict):
            raise CostServiceError("COST_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        rules = payload.get("rules") or []
        if not isinstance(rules, list) or any(not isinstance(item, dict) for item in rules):
            raise CostServiceError("COST_RULES_INCOMPLETE", "分摊规则必须完整覆盖全部启用成本类别", 400)
        try:
            category_ids = [int(item.get("category_id")) for item in rules]
        except (TypeError, ValueError) as error:
            raise CostServiceError("COST_RULES_INCOMPLETE", "分摊规则必须完整覆盖全部启用成本类别", 400) from error
        if not rules or any(item <= 0 for item in category_ids) or len(set(category_ids)) != len(rules):
            raise CostServiceError("COST_RULES_INCOMPLETE", "分摊规则必须完整覆盖全部启用成本类别", 400)
        for item, category_id in zip(rules, category_ids):
            item["category_id"] = category_id
        if any(item.get("driver") not in DRIVERS for item in rules):
            raise CostServiceError("COST_DRIVER_INVALID", "存在不支持的分摊依据", 400)
        for item in rules:
            ratios = item.get("manual_ratio_json")
            if item.get("driver") == "manual_ratio":
                try:
                    values = [Decimal(str(value)) for value in (ratios or {}).values()]
                except (AttributeError, InvalidOperation, ValueError):
                    values = []
                if not values or any(not value.is_finite() or value < 0 for value in values) or sum(values, Decimal("0")) != Decimal("1"):
                    raise CostServiceError("COST_MANUAL_RATIO_INVALID", "手工比例必须为非负数且合计为 1", 400)
            elif ratios is not None:
                item["manual_ratio_json"] = None
        reason = str(payload.get("change_reason", "")).strip()
        if len(reason) < 2 or len(reason) > 500:
            raise CostServiceError("COST_CHANGE_REASON_REQUIRED", "请填写 2-500 字的修改原因", 400)
        try:
            effective_from = date.fromisoformat(str(payload.get("effective_from")))
        except ValueError as error:
            raise CostServiceError("COST_DATE_INVALID", "生效日期格式无效", 400) from error
        first_next_month = (date.today().replace(day=28) + timedelta(days=4)).replace(day=1)
        if effective_from < first_next_month or effective_from.day != 1:
            raise CostServiceError("COST_EFFECTIVE_DATE_INVALID", "新规则必须从未来月份首日生效", 400)
        version = self.store.create_rule_version(
            user_id=int(user["id"]),
            ip_address=ip_address,
            effective_from=effective_from,
            change_reason=reason,
            rules=rules,
        )
        return self.rule_payload(version)

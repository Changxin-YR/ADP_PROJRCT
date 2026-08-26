from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, verify_version
from backend.layers.common.files.evidence import normalize_evidence_ids
from backend.layers.features.cost.cost_enterprise_validation import asset_payload, expense_payload


class CostEnterpriseService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有成本经营权限", 403)

    @staticmethod
    def expected(payload: Any) -> int:
        return parse_expected_version(payload)

    @staticmethod
    def dates(payload: Any) -> tuple[date, date]:
        try:
            start = date.fromisoformat(str(payload.get("period_start")))
            end = date.fromisoformat(str(payload.get("period_end")))
        except (AttributeError, TypeError, ValueError) as exc:
            raise DomainError("COST_DATE_INVALID", "成本期间格式无效", 400) from exc
        if start > end:
            raise DomainError("COST_PERIOD_INVALID", "开始日期不能晚于结束日期", 400)
        return start, end

    @classmethod
    def serialize(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value.quantize(Decimal("0.01")))
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: cls.serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls.serialize(item) for item in value]
        return value

    @staticmethod
    def evidence_ids(payload: Any) -> list[int]:
        try:
            values = (payload or {}).get("evidence_attachment_ids")
        except AttributeError as exc:
            raise DomainError("EVIDENCE_INVALID", "请求内容必须是对象", 400) from exc
        return normalize_evidence_ids(values)

    @classmethod
    def result(cls, row: dict[str, Any], user: dict[str, Any], kind: str) -> dict[str, Any]:
        permissions, status = set(user.get("permissions") or []), str(row.get("status"))
        actions = ["view"]
        if status == "draft" and f"cost.{kind}.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif status == "submitted":
            if f"cost.{kind}.manage" in permissions:
                actions.append("edit")
            if f"cost.{kind}.verify" in permissions:
                actions.append("verify")
        elif status == "verified" and f"cost.{kind}.confirm" in permissions:
            actions.append("confirm")
        elif status == "confirmed":
            if kind == "asset" and "cost.asset.manage" in permissions:
                actions.append("depreciate")
            automated = kind == "entry" and row.get("source_type") in {"asset_depreciation", "warehouse_ledger"}
            if kind != "asset" and not automated and f"cost.{kind}.reverse" in permissions:
                actions.append("reverse")
        return cls.serialize({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})

    def page(self, page: dict[str, Any], user: dict[str, Any], kind: str) -> dict[str, Any]:
        return {**page, "items": [self.result(row, user, kind) for row in page["items"]]}

    def list_expenses(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.page(self.store.list_expenses(user=user, **query), user, "entry")

    def create_expense(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        return self.result(self.store.create_expense(expense_payload(payload, self.dates), user=user, user_id=int(user["id"])), user, "entry")

    def _record(self, user: dict[str, Any], record_id: int, kind: str) -> dict[str, Any]:
        store_kind = "expense" if kind == "entry" else kind
        row = getattr(self.store, f"get_{store_kind}")(record_id, user=user)
        if row is None:
            codes = {"entry": ("COST_ENTRY_NOT_FOUND", "费用记录不存在"), "asset": ("COST_ASSET_NOT_FOUND", "资产不存在"), "settlement": ("COST_SETTLEMENT_NOT_FOUND", "结算记录不存在")}
            code, message = codes[kind]
            raise DomainError(code, message, 404)
        return row

    def get_expense(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.result(self._record(user, record_id, "entry"), user, "entry")

    def update_expense(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        current, expected = self._record(user, record_id, "entry"), self.expected(payload)
        if current["status"] not in {"draft", "submitted"}:
            raise DomainError("RECORD_READ_ONLY", "已核验费用只允许查看或冲销", 409)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        row = self.store.update_expense(record_id, expense_payload(payload, self.dates), expected_version=expected, user=user, user_id=int(user["id"]))
        return self.result(row, user, "entry")

    def _transition(self, user: dict[str, Any], record_id: int, payload: Any, *, kind: str, before: str, after: str, permission: str) -> dict[str, Any]:
        self.require(user, permission)
        current, expected = self._record(user, record_id, kind), self.expected(payload)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前成本状态不允许执行该操作", 409)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        if after == "verified" and int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "经办人与核验人必须分离", 403)
        evidence = self.evidence_ids(payload)
        row = getattr(self.store, f"transition_{'expense' if kind == 'entry' else kind}")(
            record_id, after, expected_version=expected, evidence_attachment_ids=evidence,
            user=user, user_id=int(user["id"]),
        )
        return self.result(row, user, kind)

    def submit_expense(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="entry", before="draft", after="submitted", permission="cost.entry.manage")

    def verify_expense(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="entry", before="submitted", after="verified", permission="cost.entry.verify")

    def confirm_expense(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="entry", before="verified", after="confirmed", permission="cost.entry.confirm")

    def delete_expense(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.entry.manage")
        return self.result(self.store.delete_expense(record_id, user=user, user_id=int(user["id"])), user, "entry")

    def reverse_expense(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.entry.reverse")
        current = self._record(user, record_id, "entry")
        if current.get("source_type") in {"asset_depreciation", "warehouse_ledger"}:
            raise DomainError("COST_REVERSAL_NOT_ALLOWED", "自动成本来源不能通过费用接口冲销", 409)
        reason = str((payload or {}).get("reason") or "").strip()
        if len(reason) < 2:
            raise DomainError("COST_REVERSAL_REASON_REQUIRED", "冲销必须填写原因", 400)
        row = self.store.reverse_expense(record_id, reason=reason, user=user, user_id=int(user["id"]))
        return self.result(row, user, "entry")

    def list_assets(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.page(self.store.list_assets(user=user, **query), user, "asset")

    def create_asset(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "cost.asset.manage")
        return self.result(self.store.create_asset(asset_payload(payload), user=user, user_id=int(user["id"])), user, "asset")

    def get_asset(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.result(self._record(user, record_id, "asset"), user, "asset")

    def update_asset(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.asset.manage"); current, expected = self._record(user, record_id, "asset"), self.expected(payload)
        if current["status"] not in {"draft", "submitted"}: raise DomainError("RECORD_READ_ONLY", "已核验资产不可编辑", 409)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.result(self.store.update_asset(record_id, asset_payload(payload), expected_version=expected, user=user, user_id=int(user["id"])), user, "asset")

    def submit_asset(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]: return self._transition(user, record_id, payload, kind="asset", before="draft", after="submitted", permission="cost.asset.manage")
    def verify_asset(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]: return self._transition(user, record_id, payload, kind="asset", before="submitted", after="verified", permission="cost.asset.verify")
    def confirm_asset(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]: return self._transition(user, record_id, payload, kind="asset", before="verified", after="confirmed", permission="cost.asset.confirm")
    def delete_asset(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.asset.manage"); return self.result(self.store.delete_asset(record_id, user=user, user_id=int(user["id"])), user, "asset")

    def depreciate_asset(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.asset.manage")
        period = str((payload or {}).get("period") or "")
        try:
            date.fromisoformat(f"{period}-01")
        except ValueError as exc:
            raise DomainError("DEPRECIATION_PERIOD_INVALID", "折旧期间格式无效", 400) from exc
        return self.serialize(self.store.depreciate_asset(record_id, period=period, user=user, user_id=int(user["id"])))

    def run_allocation(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "cost.allocation.manage")
        start, end = self.dates(payload)
        try:
            farm_id = int(payload.get("farm_id"))
            area_id = int(payload["area_id"]) if payload.get("area_id") not in {None, ""} else None
        except (AttributeError, TypeError, ValueError) as exc:
            raise DomainError("COST_ALLOCATION_SCOPE_REQUIRED", "成本分摊必须指定基地，可选指定区域", 400) from exc
        if farm_id <= 0 or (area_id is not None and area_id <= 0):
            raise DomainError("COST_ALLOCATION_SCOPE_REQUIRED", "成本分摊必须指定有效基地和区域", 400)
        return self.serialize(self.store.run_allocation(
            period_start=start, period_end=end, farm_id=farm_id, area_id=area_id,
            user=user, user_id=int(user["id"]),
        ))

    def list_settlements(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.page(self.store.list_settlements(user=user, **query), user, "settlement")

    def create_settlement(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "cost.settlement.manage")
        start, end = self.dates(payload)
        try:
            allocation_run_id = int(payload.get("allocation_run_id"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise DomainError("COST_ALLOCATION_RUN_INVALID", "分摊结果编号无效", 400) from exc
        if allocation_run_id <= 0:
            raise DomainError("COST_ALLOCATION_RUN_INVALID", "分摊结果编号无效", 400)
        clean = {"period_start": start, "period_end": end, "allocation_run_id": allocation_run_id, "name": str(payload.get("name") or f"{start:%Y-%m} 期间结算")}
        return self.result(self.store.create_settlement(clean, user=user, user_id=int(user["id"])), user, "settlement")

    def get_settlement(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.view")
        return self.result(self._record(user, record_id, "settlement"), user, "settlement")

    def update_settlement(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.settlement.manage")
        if not isinstance(payload, dict) or set(payload) - {"name", "expected_version"}:
            raise DomainError("COST_SETTLEMENT_FIELD_INVALID", "结算草稿仅允许修改名称", 400)
        name, expected = str(payload.get("name") or "").strip(), self.expected(payload)
        if not 2 <= len(name) <= 120:
            raise DomainError("COST_SETTLEMENT_NAME_INVALID", "结算名称必须为 2-120 个字符", 400)
        current = self._record(user, record_id, "settlement")
        if current["status"] not in {"draft", "submitted"}:
            raise DomainError("RECORD_READ_ONLY", "结算核验后只允许查看或反结算", 409)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        row = self.store.update_settlement(record_id, name, expected_version=expected, user=user, user_id=int(user["id"]))
        return self.result(row, user, "settlement")

    def delete_settlement(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "cost.settlement.manage")
        return self.result(self.store.delete_settlement(record_id, user=user, user_id=int(user["id"])), user, "settlement")

    def submit_settlement(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="settlement", before="draft", after="submitted", permission="cost.settlement.manage")

    def verify_settlement(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="settlement", before="submitted", after="verified", permission="cost.settlement.verify")

    def confirm_settlement(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, record_id, payload, kind="settlement", before="verified", after="confirmed", permission="cost.settlement.confirm")

    def reverse_settlement(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "cost.settlement.reverse")
        reason = str((payload or {}).get("reason") or "").strip()
        if len(reason) < 2:
            raise DomainError("COST_SETTLEMENT_REVERSAL_REASON_REQUIRED", "反结算必须填写原因", 400)
        current, expected = self._record(user, record_id, "settlement"), self.expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.result(self.store.reverse_settlement(record_id, expected_version=expected, reason=reason, user=user, user_id=int(user["id"])), user, "settlement")

    def net_report(self, user: dict[str, Any], query: Any) -> dict[str, Any]:
        self.require(user, "cost.view")
        start, end = self.dates(query)
        return self.serialize(self.store.net_report(period_start=start, period_end=end, user=user))

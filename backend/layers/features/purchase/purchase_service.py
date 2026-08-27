from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, require_deletable, require_editable, verify_version
from backend.layers.common.files.evidence import evidence_from_payload


ORDER_FIELDS = {
    "code", "name", "supplier_id", "material_id", "warehouse_id", "quantity", "unit_price",
    "expected_delivery_date", "due_date", "note", "evidence_attachment_ids",
}
PAYMENT_CREATE_FIELDS = {"code", "name", "payable_id", "amount", "paid_at", "payment_method", "note", "evidence_attachment_ids"}
PAYMENT_FIELDS = PAYMENT_CREATE_FIELDS - {"payable_id"}
PAYMENT_METHODS = {"bank_transfer", "cash", "check", "digital_wallet", "other"}


class PurchaseService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有采购付款业务权限", 403)

    @staticmethod
    def _expected(payload: Any) -> int:
        return parse_expected_version(payload)

    @staticmethod
    def _clean(payload: Any, fields: set[str]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DomainError("PURCHASE_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        if set(payload) - fields - {"expected_version", "cancellation_reason"}:
            raise DomainError("PURCHASE_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in fields and value != ""}

    @staticmethod
    def _positive(row: dict[str, Any], *fields: str) -> None:
        try:
            values = [Decimal(str(row.get(field, 0))) for field in fields]
            if any(not value.is_finite() or value <= 0 for value in values):
                raise ValueError
        except (InvalidOperation, ValueError) as exc:
            raise DomainError("PURCHASE_AMOUNT_INVALID", "数量、单价和金额必须大于零", 400) from exc

    @staticmethod
    def _validate_dates(row: dict[str, Any]) -> None:
        try:
            expected = date.fromisoformat(str(row["expected_delivery_date"])) if row.get("expected_delivery_date") else None
            due = date.fromisoformat(str(row["due_date"])) if row.get("due_date") else None
        except (TypeError, ValueError) as exc:
            raise DomainError("PURCHASE_DATE_INVALID", "采购日期格式无效", 400) from exc
        if expected and due and due < expected:
            raise DomainError("PURCHASE_DATE_INVALID", "付款到期日不能早于预计到货日", 400)

    @classmethod
    def order_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions = set(user.get("permissions") or [])
        actions = ["view"]
        if row.get("status") == "draft" and "purchase.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "purchase.manage" in permissions:
                actions.append("edit")
            if "purchase.verify" in permissions:
                actions += ["approve", "cancel"]
        elif row.get("status") in {"approved", "partially_received"}:
            if "warehouse.manage" in permissions:
                actions.append("receive")
            if row.get("status") == "approved" and "purchase.verify" in permissions:
                actions.append("cancel")
        result = {**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions}
        return cls._dates(result)

    @classmethod
    def payment_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions = set(user.get("permissions") or [])
        actions = ["view"]
        if row.get("status") == "draft" and "finance.payment.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "finance.payment.manage" in permissions:
                actions.append("edit")
            if "finance.payment.verify" in permissions:
                actions += ["verify", "cancel"]
        elif row.get("status") == "verified" and not row.get("reversal_id") and "finance.payment.verify" in permissions:
            actions.append("reverse")
        return cls._dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})

    @staticmethod
    def _dates(row: dict[str, Any]) -> dict[str, Any]:
        for key, value in list(row.items()):
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
        return row

    def list_orders(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "purchase.view")
        page = self.store.list_orders(user=user, **query)
        return {**page, "items": [self.order_result(row, user) for row in page["items"]]}

    def create_order(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage"); clean = self._clean(payload, ORDER_FIELDS)
        if not all(str(clean.get(key, "")).strip() for key in ("code", "name")) or not all(clean.get(key) for key in ("supplier_id", "material_id", "warehouse_id", "due_date")):
            raise DomainError("PURCHASE_REQUIRED_FIELDS", "单号、名称、供应商、物料、收货仓和到期日不能为空", 400)
        self._positive(clean, "quantity", "unit_price")
        self._validate_dates(clean)
        return self.order_result(self.store.create_order(clean, user=user, user_id=int(user["id"])), user)

    def _order(self, user: dict[str, Any], order_id: int) -> dict[str, Any]:
        row = self.store.get_order(order_id, user=user)
        if row is None:
            raise DomainError("PURCHASE_ORDER_NOT_FOUND", "采购单不存在", 404)
        return row

    def update_order(self, user: dict[str, Any], order_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage"); current = self._order(user, order_id); require_editable(str(current["status"])); expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"])); clean = self._clean(payload, ORDER_FIELDS)
        if not clean:
            raise DomainError("PURCHASE_NO_CHANGES", "没有可保存的修改", 400)
        self._positive({**current, **clean}, "quantity", "unit_price")
        self._validate_dates({**current, **clean})
        return self.order_result(self.store.update_order(order_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)

    def submit_order(self, user: dict[str, Any], order_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage")
        return self._order_transition(user, order_id, payload, "draft", "submitted")

    def approve_order(self, user: dict[str, Any], order_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.verify"); current = self._order(user, order_id)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "采购经办人与审批人必须分离", 403)
        return self._order_transition(user, order_id, payload, "submitted", "approved")

    def _order_transition(self, user: dict[str, Any], order_id: int, payload: Any, before: str, after: str) -> dict[str, Any]:
        current = self._order(user, order_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前采购状态不允许执行该操作", 409)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.order_result(self.store.set_order_status(order_id, after, expected_version=expected, user=user, user_id=int(user["id"])), user)

    def cancel_order(self, user: dict[str, Any], order_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.verify"); current = self._order(user, order_id)
        if current["status"] not in {"submitted", "approved"}:
            raise DomainError("INVALID_STATE_TRANSITION", "当前采购状态不能取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason:
            raise DomainError("CANCELLATION_REASON_REQUIRED", "取消采购单必须填写原因", 400)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.order_result(self.store.cancel_order(order_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason), user)

    def delete_order(self, user: dict[str, Any], order_id: int) -> dict[str, Any]:
        self.require(user, "purchase.manage"); current = self._order(user, order_id); require_deletable(str(current["status"]), has_references=False)
        return self.order_result(self.store.delete_order_draft(order_id, user=user, user_id=int(user["id"])), user)

    def list_payables(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "finance.payable.view"); page = self.store.list_payables(user=user, **query)
        return {**page, "items": [self._dates(dict(row)) for row in page["items"]]}

    def list_payments(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "finance.payable.view"); page = self.store.list_payments(user=user, **query)
        return {**page, "items": [self.payment_result(row, user) for row in page["items"]]}

    def create_payment(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.manage"); clean = self._clean(payload, PAYMENT_CREATE_FIELDS)
        if not all(clean.get(key) for key in ("code", "name", "payable_id", "paid_at", "payment_method")):
            raise DomainError("PAYMENT_REQUIRED_FIELDS", "付款单号、名称、应付来源、付款日期和方式不能为空", 400)
        if clean["payment_method"] not in PAYMENT_METHODS:
            raise DomainError("PAYMENT_METHOD_INVALID", "付款方式不在允许范围内", 400)
        self._positive(clean, "amount")
        return self.payment_result(self.store.create_payment(clean, user=user, user_id=int(user["id"])), user)

    def _payment(self, user: dict[str, Any], payment_id: int) -> dict[str, Any]:
        row = self.store.get_payment(payment_id, user=user)
        if row is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        return row

    def update_payment(self, user: dict[str, Any], payment_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.manage"); current = self._payment(user, payment_id); require_editable(str(current["status"])); expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"])); clean = self._clean(payload, PAYMENT_FIELDS); self._positive({**current, **clean}, "amount")
        if clean.get("payment_method") not in PAYMENT_METHODS | {None}:
            raise DomainError("PAYMENT_METHOD_INVALID", "付款方式不在允许范围内", 400)
        return self.payment_result(self.store.update_payment(payment_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)

    def submit_payment(self, user: dict[str, Any], payment_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.manage"); return self._payment_transition(user, payment_id, payload, "draft", "submitted")

    def verify_payment(self, user: dict[str, Any], payment_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.verify"); current = self._payment(user, payment_id); evidence = evidence_from_payload(payload, current.get("evidence_attachment_ids"))
        if not evidence:
            raise DomainError("EVIDENCE_REQUIRED", "付款核验必须上传付款凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "付款经办人与核验人必须分离", 403)
        return self._payment_transition(user, payment_id, payload, "submitted", "verified", evidence=list(evidence))

    def _payment_transition(self, user: dict[str, Any], payment_id: int, payload: Any, before: str, after: str, *, evidence: list[int] | None = None) -> dict[str, Any]:
        current = self._payment(user, payment_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前付款状态不允许执行该操作", 409)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.payment_result(self.store.set_payment_status(payment_id, after, expected_version=expected, user=user, user_id=int(user["id"]), evidence_attachment_ids=evidence), user)

    def cancel_payment(self, user: dict[str, Any], payment_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.verify"); current = self._payment(user, payment_id)
        if current["status"] != "submitted":
            raise DomainError("INVALID_STATE_TRANSITION", "仅待核验付款可以取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason:
            raise DomainError("CANCELLATION_REASON_REQUIRED", "取消付款必须填写原因", 400)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.payment_result(self.store.cancel_payment(payment_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason), user)

    def delete_payment(self, user: dict[str, Any], payment_id: int) -> dict[str, Any]:
        self.require(user, "finance.payment.manage"); current = self._payment(user, payment_id); require_deletable(str(current["status"]), has_references=False)
        return self.payment_result(self.store.delete_payment_draft(payment_id, user=user, user_id=int(user["id"])), user)

    def reverse_payment(self, user: dict[str, Any], payment_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.payment.verify"); current = self._payment(user, payment_id)
        if current["status"] != "verified" or current.get("reversal_id"):
            raise DomainError("PAYMENT_NOT_REVERSIBLE", "仅未冲销的已核验付款可以冲销", 409)
        evidence = evidence_from_payload(payload)
        reason = str((payload or {}).get("reversal_reason") or "").strip()
        if not reason:
            raise DomainError("REVERSAL_REASON_REQUIRED", "冲销付款必须填写原因", 400)
        if not evidence:
            raise DomainError("EVIDENCE_REQUIRED", "冲销付款必须上传退回或冲销凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "付款经办人不能冲销本人付款", 403)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        self.store.reverse_payment(payment_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason, evidence_attachment_ids=evidence)
        return self.payment_result(self._payment(user, payment_id), user)

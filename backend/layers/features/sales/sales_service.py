from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, require_deletable, require_editable, verify_version
from backend.layers.common.files.evidence import evidence_from_payload
ORDER_FIELDS = {"code", "name", "customer_id", "pond_id", "batch_id", "species", "quantity", "unit", "unit_price", "sold_at", "due_date", "note", "evidence_attachment_ids"}
DELIVERY_FIELDS = {"code", "name", "sales_order_id", "quantity", "delivered_at", "transport_info", "acceptance_note", "harvest_document_id", "evidence_attachment_ids"}
RECEIPT_CREATE_FIELDS = {"code", "name", "receivable_id", "amount", "received_at", "receipt_method", "note", "evidence_attachment_ids"}
RECEIPT_FIELDS = RECEIPT_CREATE_FIELDS - {"receivable_id"}
RECEIPT_METHODS = {"bank_transfer", "cash", "check", "digital_wallet", "other"}
class SalesService:
    def __init__(self, store: Any) -> None:
        self.store = store
    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有销售收款业务权限", 403)
    @staticmethod
    def expected(payload: Any) -> int:
        return parse_expected_version(payload)
    @staticmethod
    def clean(payload: Any, fields: set[str], *, extra: set[str] | None = None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DomainError("SALES_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        allowed = fields | {"expected_version"} | (extra or set())
        if set(payload) - allowed:
            raise DomainError("SALES_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in fields and value != ""}
    @staticmethod
    def positive(row: dict[str, Any], *fields: str) -> None:
        try:
            values = [Decimal(str(row.get(field, 0))) for field in fields]
            if any(not value.is_finite() or value <= 0 for value in values):
                raise ValueError
        except (InvalidOperation, ValueError) as exc:
            raise DomainError("SALES_AMOUNT_INVALID", "数量、单价和金额必须大于零", 400) from exc
    @staticmethod
    def validate_dates(row: dict[str, Any]) -> None:
        try:
            sold = date.fromisoformat(str(row["sold_at"])) if row.get("sold_at") else None
            due = date.fromisoformat(str(row["due_date"])) if row.get("due_date") else None
        except (TypeError, ValueError) as exc:
            raise DomainError("SALES_DATE_INVALID", "销售日期格式无效", 400) from exc
        if sold and due and due < sold:
            raise DomainError("SALES_DATE_INVALID", "收款到期日不能早于销售日期", 400)
    @staticmethod
    def dates(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for key, value in list(result.items()):
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        return result
    @classmethod
    def order_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions, actions = set(user.get("permissions") or []), ["view"]
        if row.get("status") == "draft" and "sales.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "sales.manage" in permissions: actions.append("edit")
            if "sales.verify" in permissions: actions += ["approve", "cancel"]
        elif row.get("status") in {"approved", "partially_delivered"} and "sales.manage" in permissions:
            actions.append("deliver")
        return cls.dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})
    @classmethod
    def delivery_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions, actions = set(user.get("permissions") or []), ["view"]
        if row.get("status") == "draft" and "sales.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "sales.manage" in permissions: actions.append("edit")
            if "sales.verify" in permissions: actions += ["verify", "cancel"]
        elif row.get("status") == "verified" and not row.get("correction_id") and "sales.manage" in permissions:
            actions.append("correct")
        return cls.dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})
    @classmethod
    def receipt_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions, actions = set(user.get("permissions") or []), ["view"]
        if row.get("status") == "draft" and "finance.receipt.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "finance.receipt.manage" in permissions: actions.append("edit")
            if "finance.receipt.verify" in permissions: actions += ["verify", "cancel"]
        elif row.get("status") == "verified" and not row.get("reversal_id") and "finance.receipt.verify" in permissions:
            actions.append("reverse")
        return cls.dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})
    def _page(self, page: dict[str, Any], user: dict[str, Any], result: Any) -> dict[str, Any]:
        return {**page, "items": [result(row, user) for row in page["items"]]}
    def list_orders(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "sales.view"); return self._page(self.store.list_orders(user=user, **query), user, self.order_result)
    def create_order(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); clean = self.clean(payload, ORDER_FIELDS)
        required = ("code", "name", "customer_id", "pond_id", "batch_id", "species", "quantity", "unit", "unit_price", "sold_at", "due_date")
        if not all(clean.get(key) for key in required):
            raise DomainError("SALES_REQUIRED_FIELDS", "销售单必填信息不完整", 400)
        if clean["unit"] not in {"kg", "jin", "tail"}:
            raise DomainError("SALES_UNIT_INVALID", "销售单位仅支持 kg、jin 或 tail", 400)
        self.positive(clean, "quantity", "unit_price")
        self.validate_dates(clean)
        return self.order_result(self.store.create_order(clean, user=user, user_id=int(user["id"])), user)
    def order(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        row = self.store.get_order(record_id, user=user)
        if row is None: raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
        return row
    def update_order(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); current = self.order(user, record_id); require_editable(str(current["status"])); expected = self.expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"])); clean = self.clean(payload, ORDER_FIELDS)
        if not clean: raise DomainError("SALES_NO_CHANGES", "没有可保存的修改", 400)
        self.positive({**current, **clean}, "quantity", "unit_price")
        self.validate_dates({**current, **clean})
        return self.order_result(self.store.update_order(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)
    def order_transition(self, user: dict[str, Any], record_id: int, payload: Any, before: str, after: str) -> dict[str, Any]:
        current = self.order(user, record_id)
        if current["status"] != before: raise DomainError("INVALID_STATE_TRANSITION", "当前销售状态不允许执行该操作", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.order_result(self.store.set_order_status(record_id, after, expected_version=expected, user=user, user_id=int(user["id"])), user)
    def submit_order(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); return self.order_transition(user, record_id, payload, "draft", "submitted")
    def approve_order(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.verify"); current = self.order(user, record_id)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "销售经办人与审批人必须分离", 403)
        return self.order_transition(user, record_id, payload, "submitted", "approved")
    def cancel_order(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.verify"); current = self.order(user, record_id)
        if current["status"] not in {"submitted", "approved"}: raise DomainError("INVALID_STATE_TRANSITION", "当前销售状态不能取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason: raise DomainError("CANCELLATION_REASON_REQUIRED", "取消销售单必须填写原因", 400)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.order_result(self.store.cancel_order(record_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason), user)
    def delete_order(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "sales.manage"); current = self.order(user, record_id); require_deletable(str(current["status"]))
        return self.order_result(self.store.delete_order_draft(record_id, user=user, user_id=int(user["id"])), user)
    def list_deliveries(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "sales.view"); return self._page(self.store.list_deliveries(user=user, **query), user, self.delivery_result)
    def delivery(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        row = self.store.get_delivery(record_id, user=user)
        if row is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
        return row
    def create_delivery(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); clean = self.clean(payload, DELIVERY_FIELDS)
        if not all(clean.get(key) for key in ("code", "name", "sales_order_id", "harvest_document_id", "quantity", "delivered_at")):
            raise DomainError("DELIVERY_REQUIRED_FIELDS", "交付单、销售来源和已核验出塘单不能为空", 400)
        self.positive(clean, "quantity"); self.order(user, int(clean["sales_order_id"]))
        return self.delivery_result(self.store.create_delivery(clean, user=user, user_id=int(user["id"])), user)
    def update_delivery(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); current = self.delivery(user, record_id); require_editable(str(current["status"])); expected = self.expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"])); clean = self.clean(payload, DELIVERY_FIELDS - {"sales_order_id"})
        self.positive({**current, **clean}, "quantity")
        return self.delivery_result(self.store.update_delivery(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)
    def delivery_transition(self, user: dict[str, Any], record_id: int, payload: Any, before: str, after: str, evidence: list[int] | None = None) -> dict[str, Any]:
        current = self.delivery(user, record_id)
        if current["status"] != before: raise DomainError("INVALID_STATE_TRANSITION", "当前交付状态不允许执行该操作", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        row = self.store.set_delivery_status(record_id, after, expected_version=expected, user=user, user_id=int(user["id"]), evidence_attachment_ids=evidence)
        return self.delivery_result(row, user)
    def submit_delivery(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); return self.delivery_transition(user, record_id, payload, "draft", "submitted")
    def verify_delivery(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.verify"); current = self.delivery(user, record_id); evidence = evidence_from_payload(payload, current.get("evidence_attachment_ids"))
        if not evidence: raise DomainError("EVIDENCE_REQUIRED", "交付核验必须上传客户验收凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "交付经办人与核验人必须分离", 403)
        return self.delivery_transition(user, record_id, payload, "submitted", "verified", evidence)
    def correct_delivery(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.manage"); current = self.delivery(user, record_id)
        if current["status"] != "verified": raise DomainError("INVALID_STATE_TRANSITION", "仅已核验交付可以更正", 409)
        clean = self.clean(payload, DELIVERY_FIELDS - {"sales_order_id"}, extra={"correction_reason"})
        reason = str((payload or {}).get("correction_reason") or "").strip()
        if not reason or not clean.get("code") or clean["code"] == current.get("code"):
            raise DomainError("CORRECTION_REQUIRED", "更正单必须填写新单号和原因", 400)
        try:
            harvest_id = int(clean.get("harvest_document_id") or 0)
        except (TypeError, ValueError):
            harvest_id = 0
        if harvest_id <= 0 or harvest_id == int(current.get("harvest_document_id") or 0):
            raise DomainError("CORRECTION_HARVEST_REQUIRED", "更正交付必须关联新的已核验出塘单", 400)
        clean["harvest_document_id"] = harvest_id
        clean["correction_reason"] = reason; expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.delivery_result(self.store.create_delivery_correction(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)
    def delete_delivery(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "sales.manage"); current = self.delivery(user, record_id); require_deletable(str(current["status"]))
        return self.delivery_result(self.store.delete_delivery_draft(record_id, user=user, user_id=int(user["id"])), user)
    def cancel_delivery(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "sales.verify"); current = self.delivery(user, record_id)
        if current["status"] != "submitted": raise DomainError("INVALID_STATE_TRANSITION", "仅待核验交付可以取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason: raise DomainError("CANCELLATION_REASON_REQUIRED", "取消交付必须填写原因", 400)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.delivery_result(self.store.cancel_delivery(record_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason), user)
    def list_receivables(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "finance.receivable.view"); page = self.store.list_receivables(user=user, **query)
        return {**page, "items": [self.dates(row) for row in page["items"]]}
    def list_receipts(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "finance.receivable.view"); return self._page(self.store.list_receipts(user=user, **query), user, self.receipt_result)
    def receipt(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        row = self.store.get_receipt(record_id, user=user)
        if row is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        return row
    def create_receipt(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.manage"); clean = self.clean(payload, RECEIPT_CREATE_FIELDS)
        if not all(clean.get(key) for key in ("code", "name", "receivable_id", "amount", "received_at", "receipt_method")):
            raise DomainError("RECEIPT_REQUIRED_FIELDS", "收款单必填信息不完整", 400)
        if clean["receipt_method"] not in RECEIPT_METHODS:
            raise DomainError("RECEIPT_METHOD_INVALID", "收款方式不在允许范围内", 400)
        self.positive(clean, "amount")
        return self.receipt_result(self.store.create_receipt(clean, user=user, user_id=int(user["id"])), user)
    def update_receipt(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.manage"); current = self.receipt(user, record_id); require_editable(str(current["status"])); expected = self.expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"])); clean = self.clean(payload, RECEIPT_FIELDS); self.positive({**current, **clean}, "amount")
        if clean.get("receipt_method") not in RECEIPT_METHODS | {None}: raise DomainError("RECEIPT_METHOD_INVALID", "收款方式不在允许范围内", 400)
        return self.receipt_result(self.store.update_receipt(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)
    def receipt_transition(self, user: dict[str, Any], record_id: int, payload: Any, before: str, after: str, evidence: list[int] | None = None) -> dict[str, Any]:
        current = self.receipt(user, record_id)
        if current["status"] != before: raise DomainError("INVALID_STATE_TRANSITION", "当前收款状态不允许执行该操作", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.receipt_result(self.store.set_receipt_status(record_id, after, expected_version=expected, user=user, user_id=int(user["id"]), evidence_attachment_ids=evidence), user)
    def submit_receipt(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.manage"); return self.receipt_transition(user, record_id, payload, "draft", "submitted")
    def verify_receipt(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.verify"); current = self.receipt(user, record_id); evidence = evidence_from_payload(payload, current.get("evidence_attachment_ids"))
        if not evidence: raise DomainError("EVIDENCE_REQUIRED", "收款核验必须上传收款凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "收款经办人与核验人必须分离", 403)
        return self.receipt_transition(user, record_id, payload, "submitted", "verified", evidence)
    def cancel_receipt(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.verify"); current = self.receipt(user, record_id)
        if current["status"] != "submitted": raise DomainError("INVALID_STATE_TRANSITION", "仅待核验收款可以取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason: raise DomainError("CANCELLATION_REASON_REQUIRED", "取消收款必须填写原因", 400)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.receipt_result(self.store.cancel_receipt(record_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason), user)
    def reverse_receipt(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "finance.receipt.verify"); current = self.receipt(user, record_id)
        if current["status"] != "verified" or current.get("reversal_id"): raise DomainError("RECEIPT_NOT_REVERSIBLE", "仅未冲销的已核验收款可以冲销", 409)
        if self.store.receipt_was_handled_by(record_id, int(user["id"])):
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "收款经办人不能冲销自己经办的正式收款", 403)
        evidence = evidence_from_payload(payload); reason = str((payload or {}).get("reversal_reason") or "").strip()
        if not reason: raise DomainError("REVERSAL_REASON_REQUIRED", "冲销收款必须填写原因", 400)
        if not evidence: raise DomainError("EVIDENCE_REQUIRED", "冲销收款必须上传退回凭据", 400)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        self.store.reverse_receipt(record_id, expected_version=expected, user=user, user_id=int(user["id"]), reason=reason, evidence_attachment_ids=evidence)
        return self.receipt_result(self.receipt(user, record_id), user)
    def delete_receipt(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "finance.receipt.manage"); current = self.receipt(user, record_id); require_deletable(str(current["status"]))
        return self.receipt_result(self.store.delete_receipt_draft(record_id, user=user, user_id=int(user["id"])), user)
    def list_returns(self, user: dict[str, Any], **query: Any) -> dict[str, Any]: self.require(user, "sales.view"); return self.store.list_returns("sales", user=user, **query)
    def create_return(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        if not ({"sales.return.manage", "sales.manage"} & set(user.get("permissions") or [])): raise DomainError("FORBIDDEN", "当前账号没有销售退货权限", 403)
        if not isinstance(payload, dict) or not all(str(payload.get(k) or "").strip() for k in ("code", "name", "reason")): raise DomainError("RETURN_REQUIRED_FIELDS", "退货单号、名称和原因不能为空", 400)
        return self.store.create_return("sales", payload, user=user, user_id=int(user["id"]))
    def _return_transition(self, user: dict[str, Any], record_id: int, payload: Any, before: str, after: str) -> dict[str, Any]:
        current = self.store.get_return("sales", record_id, user=user)
        if current is None: raise DomainError("RETURN_NOT_FOUND", "销售退货单不存在", 404)
        if current.get("status") != before: raise DomainError("INVALID_STATE_TRANSITION", "当前退货状态不允许执行该操作", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"])); return self.store.set_return_status("sales", record_id, after, expected_version=expected, user=user, user_id=int(user["id"]))
    def submit_return(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        if not ({"sales.return.manage", "sales.manage"} & set(user.get("permissions") or [])): raise DomainError("FORBIDDEN", "当前账号没有销售退货权限", 403)
        return self._return_transition(user, record_id, payload, "draft", "submitted")
    def verify_return(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        if not ({"sales.return.verify", "sales.verify"} & set(user.get("permissions") or [])): raise DomainError("FORBIDDEN", "当前账号没有销售退货核验权限", 403)
        return self._return_transition(user, record_id, payload, "submitted", "verified")
    def cancel_return(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        if not ({"sales.return.verify", "sales.verify"} & set(user.get("permissions") or [])): raise DomainError("FORBIDDEN", "当前账号没有销售退货核验权限", 403)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason: raise DomainError("CANCELLATION_REASON_REQUIRED", "取消退货必须填写原因", 400)
        return self._return_transition(user, record_id, payload, "submitted", "cancelled")
    def delete_return(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        if not ({"sales.return.manage", "sales.manage"} & set(user.get("permissions") or [])): raise DomainError("FORBIDDEN", "当前账号没有销售退货权限", 403)
        return self.store.delete_return("sales", record_id, user=user, user_id=int(user["id"]))

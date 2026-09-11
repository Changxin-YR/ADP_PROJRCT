from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import (
    DomainError,
    parse_expected_version,
    require_deletable,
    require_editable,
    verify_version,
)


REQUISITION_FIELDS = {"code", "name", "material_id", "quantity", "warehouse_id", "reason", "alert_key"}
REQUISITION_CONVERT_FIELDS = {"supplier_id", "unit_price", "due_date", "expected_delivery_date", "warehouse_id"}


class RequisitionService:
    """请购单：库存预警 → 请购 → 采购单 的中间环节。

    store 需实现 create_requisition/update_requisition/set_requisition_status/
    convert_requisition/delete_requisition_draft（MySqlPurchaseStore 已转发）。
    """

    def __init__(self, store: Any, order_service: Any = None) -> None:
        self.store = store
        # 转换结果里要复用采购单的字段与动作计算，避免两套格式化逻辑漂移。
        self.order_service = order_service

    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有采购请购业务权限", 403)

    @staticmethod
    def _expected(payload: Any) -> int:
        return parse_expected_version(payload)

    @staticmethod
    def _clean(payload: Any, fields: set[str]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DomainError("PURCHASE_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        if set(payload) - fields - {"expected_version", "cancellation_reason", "reversal_reason", "note"}:
            raise DomainError("PURCHASE_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in fields and value != ""}

    @staticmethod
    def _positive(row: dict[str, Any], *fields: str) -> None:
        try:
            values = [Decimal(str(row.get(field, 0))) for field in fields]
        except Exception as exc:
            raise DomainError("PURCHASE_AMOUNT_INVALID", "数量、单价和金额必须大于零", 400) from exc
        if any(not value.is_finite() or value <= 0 for value in values):
            raise DomainError("PURCHASE_AMOUNT_INVALID", "数量、单价和金额必须大于零", 400)

    @staticmethod
    def _dates(row: dict[str, Any]) -> dict[str, Any]:
        for key, value in list(row.items()):
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
        return row

    @classmethod
    def requisition_result(cls, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        permissions = set(user.get("permissions") or [])
        actions = ["view"]
        if row.get("status") == "draft" and "purchase.manage" in permissions:
            actions += ["edit", "delete", "submit"]
        elif row.get("status") == "submitted":
            if "purchase.manage" in permissions:
                actions.append("edit")
            if "purchase.verify" in permissions:
                actions += ["approve", "cancel"]
        elif row.get("status") == "approved":
            if "purchase.manage" in permissions:
                actions.append("convert")
            if "purchase.verify" in permissions:
                actions.append("cancel")
        return cls._dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions})

    def order_result(self, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if self.order_service is not None:
            return self.order_service.order_result(row, user)
        return self._dates({**row, "version": int(row.get("row_version", 1)), "allowed_actions": ["view"]})

    def list_requisitions(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "purchase.view")
        page = self.store.list_requisitions(user=user, **query)
        return {**page, "items": [self.requisition_result(row, user) for row in page["items"]]}

    def _requisition(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        row = self.store.get_requisition(record_id, user=user)
        if row is None:
            raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
        return row

    def create_requisition(self, user: dict[str, Any], payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage"); clean = self._clean(payload, REQUISITION_FIELDS)
        if not all(str(clean.get(key, "")).strip() for key in ("code", "name", "reason")) \
                or not clean.get("material_id") or clean.get("quantity") is None:
            raise DomainError("PURCHASE_REQUISITION_REQUIRED_FIELDS", "请购单号、名称和请购原因不能为空", 400)
        self._positive(clean, "quantity")
        return self.requisition_result(self.store.create_requisition(clean, user=user, user_id=int(user["id"])), user)

    def update_requisition(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage"); current = self._requisition(user, record_id)
        require_editable(str(current["status"])); expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self._clean(payload, REQUISITION_FIELDS)
        if not clean:
            raise DomainError("PURCHASE_REQUISITION_NO_CHANGES", "没有可保存的修改", 400)
        if not str({**current, **clean}.get("reason") or "").strip():
            raise DomainError("PURCHASE_REQUISITION_REQUIRED_FIELDS", "请购单号、名称和请购原因不能为空", 400)
        self._positive({**current, **clean}, "quantity")
        return self.requisition_result(
            self.store.update_requisition(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user)

    def _transition(self, user: dict[str, Any], record_id: int, payload: Any, before: str, after: str) -> dict[str, Any]:
        current = self._requisition(user, record_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前请购状态不允许执行该操作", 409)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.requisition_result(
            self.store.set_requisition_status(record_id, after, expected_version=expected, user=user, user_id=int(user["id"])), user)

    def submit_requisition(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage")
        return self._transition(user, record_id, payload, "draft", "submitted")

    def approve_requisition(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.verify"); current = self._requisition(user, record_id)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "请购经办人与审批人必须分离", 403)
        return self._transition(user, record_id, payload, "submitted", "approved")

    def cancel_requisition(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.verify"); current = self._requisition(user, record_id)
        if current["status"] not in {"draft", "submitted", "approved"}:
            raise DomainError("INVALID_STATE_TRANSITION", "当前请购状态不能取消", 409)
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason:
            raise DomainError("CANCELLATION_REASON_REQUIRED", "取消请购单必须填写原因", 400)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.requisition_result(
            self.store.set_requisition_status(record_id, "cancelled", expected_version=expected, user=user,
                                             user_id=int(user["id"]), reason=reason), user)

    def convert_requisition(self, user: dict[str, Any], record_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "purchase.manage"); current = self._requisition(user, record_id)
        if current["status"] == "converted" or current.get("converted_order_id"):
            raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409)
        if current["status"] != "approved":
            raise DomainError("INVALID_STATE_TRANSITION", "仅已审批的请购单可以转换为采购单", 409)
        expected = self._expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self._clean(payload, REQUISITION_CONVERT_FIELDS)
        if not all(clean.get(key) for key in ("supplier_id", "unit_price", "due_date")) \
                or not (current.get("warehouse_id") or clean.get("warehouse_id")):
            raise DomainError("PURCHASE_REQUISITION_CONVERT_FIELDS", "转换采购单必须填写供应商、单价、交货仓和到期日", 400)
        self._positive(clean, "unit_price")
        converted = self.store.convert_requisition(record_id, clean, expected_version=expected, user=user, user_id=int(user["id"]))
        return {**converted, "record": self.order_result(converted["record"], user),
                "requisition": self.requisition_result(converted["requisition"], user)}

    def delete_requisition(self, user: dict[str, Any], record_id: int) -> dict[str, Any]:
        self.require(user, "purchase.manage"); current = self._requisition(user, record_id)
        require_deletable(str(current["status"]), has_references=False)
        return self.requisition_result(
            self.store.delete_requisition_draft(record_id, user=user, user_id=int(user["id"])), user)

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, require_deletable, require_editable, verify_version
from backend.layers.common.files.evidence import evidence_from_payload


RESOURCES = {"receipts", "issue-requests", "issues", "returns", "transfers", "stocktakes", "scraps"}
EVIDENCE_REQUIRED = {"receipts", "stocktakes", "scraps"}
FIELDS = {
    "organization_id", "farm_id", "area_id", "warehouse_id", "target_warehouse_id",
    "material_id", "inventory_lot_id", "source_document_id", "purchase_order_id", "pond_id",
    "batch_id", "task_id", "code", "name", "scene", "quantity", "unit_cost", "lot_no",
    "production_date", "expiry_date", "location", "reason", "override_reason", "happened_at",
    "evidence_attachment_ids", "note", "correction_reason",
}


class WarehouseService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def resource(value: str) -> str:
        if value not in RESOURCES:
            raise DomainError("WAREHOUSE_RESOURCE_NOT_FOUND", "仓储业务类型不存在", 404)
        return value

    @staticmethod
    def require(user: dict[str, Any], action: str) -> None:
        if f"warehouse.{action}" not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有仓储业务权限", 403)

    @classmethod
    def result(cls, row: dict[str, Any], user: dict[str, Any], resource: str | None = None) -> dict[str, Any]:
        actions = {
            "draft": ["view", "edit", "delete", "submit"],
            "submitted": ["view", "edit", "verify"],
            "verified": ["view", "correct"],
            "corrected": ["view"],
            "in_transit": ["view", "receive", "cancel"],
        }.get(str(row.get("status")), ["view"])
        if resource == "transfers" and row.get("status") == "submitted":
            actions = ["view", "edit", "dispatch", "cancel"]
        permissions = set(user.get("permissions") or [])
        verification_actions = {"verify", "dispatch", "receive", "cancel"}
        actions = [item for item in actions if item == "view" or f"warehouse.{'verify' if item in verification_actions else 'manage'}" in permissions]
        result = {**row, "version": int(row.get("row_version", 1)), "allowed_actions": actions}
        for key, value in list(result.items()):
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        return result

    @staticmethod
    def clean(payload: Any, *, version: bool = False) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DomainError("WAREHOUSE_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        accepted = FIELDS | ({"expected_version"} if version else set())
        if set(payload) - accepted:
            raise DomainError("WAREHOUSE_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in FIELDS}

    def current(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        row = self.store.get_record(resource, record_id)
        if row is None:
            raise DomainError("WAREHOUSE_RECORD_NOT_FOUND", "仓储记录不存在", 404)
        self._scope(user, row)
        return row

    @staticmethod
    def _scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        scopes = user.get("data_scopes") or []
        if not scopes or any(item.get("scope_type") == "farm" for item in scopes):
            return
        allowed = {int(item["area_id"]) for item in scopes if item.get("area_id")}
        actual = {int(row[key]) for key in ("area_id", "_target_area_id") if row.get(key)}
        if actual and actual <= allowed:
            return
        if not actual:
            personal = any(item.get("scope_type") == "personal" for item in scopes)
            if not personal or int(row.get("created_by") or 0) != int(user["id"]):
                raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的仓储记录", 403)
            return
        if any(item.get("scope_type") == "personal" for item in scopes) and int(row.get("created_by") or 0) == int(user["id"]):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的仓储记录", 403)

    @staticmethod
    def expected(payload: Any) -> int:
        return parse_expected_version(payload)

    def list_records(self, user: dict[str, Any], resource: str, **query: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "view")
        page = self.store.list_records(resource, user=user, **query)
        return {**page, "items": [self.result(row, user, resource) for row in page["items"]]}

    def get(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "view")
        return self.result(self.current(user, resource, record_id), user, resource)

    def create(self, user: dict[str, Any], resource: str, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "manage"); clean = self.clean(payload)
        if not all(str(clean.get(key, "")).strip() for key in ("code", "name")) or not clean.get("warehouse_id") or not clean.get("material_id"):
            raise DomainError("WAREHOUSE_REQUIRED_FIELDS", "单号、名称、仓库和物料不能为空", 400)
        self._validate(resource, clean)
        return self.result(self.store.create_record(resource, clean, user=user, user_id=int(user["id"])), user, resource)

    def update(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "manage"); current = self.current(user, resource, record_id)
        require_editable(str(current["status"])); expected = self.expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self.clean(payload, version=True); self._validate(resource, {**current, **clean})
        return self.result(self.store.update_record(resource, record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user, resource)

    def correct(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "manage"); current = self.current(user, resource, record_id)
        if current["status"] != "verified":
            raise DomainError("INVALID_STATE_TRANSITION", "仅已核验仓储单据可以发起更正", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self.clean(payload, version=True)
        if not str(clean.get("code", "")).strip() or clean.get("code") == current.get("code"):
            raise DomainError("CORRECTION_CODE_REQUIRED", "更正单必须使用新的单号", 400)
        if not str(clean.get("correction_reason", "")).strip():
            raise DomainError("CORRECTION_REASON_REQUIRED", "更正单必须填写更正原因", 400)
        self._validate(resource, {**current, **clean})
        row = self.store.create_correction(resource, record_id, clean, expected_version=expected, user=user, user_id=int(user["id"]))
        return self.result(row, user, resource)

    @staticmethod
    def _validate(resource: str, row: dict[str, Any]) -> None:
        try:
            quantity = Decimal(str(row.get("quantity") or 0))
        except InvalidOperation as exc:
            raise DomainError("WAREHOUSE_QUANTITY_INVALID", "数量格式无效", 400) from exc
        if not quantity.is_finite():
            raise DomainError("WAREHOUSE_QUANTITY_INVALID", "数量格式无效", 400)
        if quantity <= 0:
            raise DomainError("WAREHOUSE_QUANTITY_INVALID", "数量必须大于 0", 400)
        if resource == "transfers" and row.get("warehouse_id") == row.get("target_warehouse_id"):
            raise DomainError("WAREHOUSE_TRANSFER_TARGET_INVALID", "调入仓不能与调出仓相同", 400)
        if resource in {"issues", "issue-requests"} and row.get("scene") in {"feed", "medicine"} and not row.get("pond_id"):
            raise DomainError("WAREHOUSE_POND_REQUIRED", "投喂和用药领用必须关联塘口", 400)
        if resource == "returns" and not all(row.get(key) for key in ("source_document_id", "inventory_lot_id")):
            raise DomainError("WAREHOUSE_RETURN_SOURCE_REQUIRED", "退库必须关联原出库单和物料批次", 400)
        if resource == "issues" and not row.get("source_document_id"):
            raise DomainError("WAREHOUSE_ISSUE_REQUEST_REQUIRED", "实际出库必须关联已核验领用申请", 400)
        if resource in {"stocktakes", "scraps"}:
            if not row.get("inventory_lot_id"):
                raise DomainError("WAREHOUSE_LOT_REQUIRED", "盘点和报损必须选择具体物料批次", 400)
        # BUG-M4-02 顺手项：日期与单价格式预校验，非法输入 400 而非 500。
        for field in ("happened_at", "production_date", "expiry_date"):
            if row.get(field) not in (None, ""):
                try:
                    text = str(row[field]).strip()
                    datetime.fromisoformat(text.replace("Z", "+00:00")) if field == "happened_at" else date.fromisoformat(text)
                except (TypeError, ValueError) as exc:
                    raise DomainError("WAREHOUSE_DATE_INVALID", f"字段 {field} 日期格式无效", 400) from exc
        if row.get("unit_cost") not in (None, ""):
            try:
                cost = Decimal(str(row["unit_cost"]))
            except InvalidOperation as exc:
                raise DomainError("WAREHOUSE_COST_INVALID", "单价格式无效", 400) from exc
            if not cost.is_finite():
                raise DomainError("WAREHOUSE_COST_INVALID", "单价格式无效", 400)
            if cost < 0:
                raise DomainError("WAREHOUSE_COST_INVALID", "单价不能为负数", 400)

    def submit(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        return self._transition(user, resource, record_id, payload, "draft", "submitted")

    def verify(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "verify"); current = self.current(user, resource, record_id)
        if resource == "transfers":
            raise DomainError("TRANSFER_DISPATCH_REQUIRED", "调拨单必须先发出并进入在途，再办理接收", 409)
        evidence = evidence_from_payload(payload, current.get("evidence_attachment_ids"))
        if resource in EVIDENCE_REQUIRED and not evidence:
            raise DomainError("EVIDENCE_REQUIRED", "该仓储业务核验必须上传凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "仓储业务禁止经办人自审", 403)
        return self._transition(user, resource, record_id, payload, "submitted", "verified", evidence=evidence)

    def _transition(self, user: dict[str, Any], resource: str, record_id: int, payload: Any, before: str, after: str, *, evidence: list[int] | None = None) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "verify" if after == "verified" else "manage")
        current = self.current(user, resource, record_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前状态不允许执行该操作", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.result(self.store.set_status(resource, record_id, after, expected_version=expected, user=user, user_id=int(user["id"]), evidence_attachment_ids=evidence), user, resource)

    def dispatch(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "verify")
        if resource != "transfers":
            raise DomainError("TRANSFER_RESOURCE_REQUIRED", "只有调拨单可以办理发出", 404)
        current = self.current(user, resource, record_id)
        if current["status"] != "submitted":
            raise DomainError("INVALID_STATE_TRANSITION", "当前调拨状态不能发出", 409)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "调拨申请人与发出核验人必须分离", 403)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.result(self.store.dispatch_transfer(record_id, expected_version=expected, user_id=int(user["id"])), user, resource)

    def receive(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "verify")
        if resource != "transfers":
            raise DomainError("TRANSFER_RESOURCE_REQUIRED", "只有调拨单可以办理接收", 404)
        current = self.current(user, resource, record_id)
        if current["status"] != "in_transit":
            raise DomainError("INVALID_STATE_TRANSITION", "当前调拨状态不能接收", 409)
        if int(user["id"]) == int(current.get("dispatched_by") or 0):
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "调拨发出人与接收人必须分离", 403)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        try:
            received = Decimal(str((payload or {}).get("received_quantity", current.get("quantity"))))
        except (InvalidOperation, AttributeError) as exc:
            raise DomainError("TRANSFER_RECEIPT_QUANTITY_INVALID", "接收数量格式无效", 400) from exc
        sent = Decimal(str(current.get("quantity") or 0))
        if not received.is_finite() or received < 0 or received > sent:
            raise DomainError("TRANSFER_RECEIPT_QUANTITY_INVALID", "接收数量必须介于零和发出数量之间", 400)
        reason = str((payload or {}).get("receipt_difference_reason") or "").strip() or None
        if received != sent and not reason:
            raise DomainError("TRANSFER_DIFFERENCE_REASON_REQUIRED", "接收数量与发出数量不一致时必须填写差异处理原因", 400)
        row = self.store.receive_transfer(record_id, expected_version=expected, user_id=int(user["id"]), received_quantity=received, difference_reason=reason)
        return self.result(row, user, resource)

    def cancel_transfer(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "verify")
        if resource != "transfers":
            raise DomainError("TRANSFER_RESOURCE_REQUIRED", "只有调拨单可以办理取消", 404)
        current = self.current(user, resource, record_id)
        if current["status"] not in {"submitted", "in_transit"}:
            raise DomainError("INVALID_STATE_TRANSITION", "当前调拨状态不能取消", 409)
        expected = self.expected(payload); verify_version(expected_version=expected, current_version=int(current["row_version"]))
        reason = str((payload or {}).get("cancellation_reason") or "").strip()
        if not reason:
            raise DomainError("TRANSFER_CANCELLATION_REASON_REQUIRED", "取消调拨必须填写原因", 400)
        row = self.store.cancel_transfer(record_id, expected_version=expected, user_id=int(user["id"]), reason=reason)
        return self.result(row, user, resource)

    def delete(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource); self.require(user, "manage"); current = self.current(user, resource, record_id)
        require_deletable(str(current["status"]), has_references=bool(current.get("has_references")))
        return self.result(self.store.delete_draft(resource, record_id, user_id=int(user["id"])), user, resource)

    def ledger(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        self.require(user, "view")
        return self.store.list_ledger(user, **query)

    def alerts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        self.require(user, "view")
        return self.store.list_alerts(user)

    def handle_alert(self, user: dict[str, Any], alert_key: str, payload: Any) -> dict[str, Any]:
        self.require(user, "manage")
        if not isinstance(payload, dict):
            raise DomainError("WAREHOUSE_ALERT_PAYLOAD_INVALID", "预警处理内容必须是对象", 400)
        action = str(payload.get("action_code") or "").strip()
        if action not in {"replenish", "transfer", "scrap", "recheck", "threshold"}:
            raise DomainError("WAREHOUSE_ALERT_ACTION_INVALID", "请选择补货、调拨、报废、复核或阈值调整", 400)
        note = str(payload.get("resolution_note") or "").strip()
        if not note:
            raise DomainError("WAREHOUSE_ALERT_NOTE_REQUIRED", "处理预警必须填写处理结论", 400)
        return self.store.handle_alert(user, alert_key, action_code=action, resolution_note=note, user_id=int(user["id"]))

    def warehouses(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        self.require(user, "view")
        return self.store.list_warehouses(user)

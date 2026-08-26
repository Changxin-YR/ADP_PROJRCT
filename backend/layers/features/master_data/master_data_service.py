from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, require_deletable, require_editable, verify_version
from backend.layers.common.security.data_scope import require_active_scope, unrestricted
RESOURCES = {"farms", "areas", "pond-groups", "ponds", "materials", "suppliers", "customers", "settings"}
RESERVED_FIELDS = {"id", "status", "row_version", "version", "allowed_actions", "created_by", "updated_by", "created_at", "updated_at", "has_references"}
MASTER_FIELDS = {
    "farms": {"organization_id", "code", "name"},
    "areas": {"organization_id", "farm_id", "parent_id", "code", "name", "sort_order"},
    "pond-groups": {"organization_id", "farm_id", "area_id", "code", "name", "description"},
    "ponds": {"organization_id", "farm_id", "area_id", "pond_group_id", "code", "name", "description", "location_text", "species", "manager_name", "capacity_mu", "pond_status", "aerator_count", "stocking_spec", "current_spec", "stock_quantity", "stock_quantity_source"},
    "materials": {"organization_id", "farm_id", "area_id", "code", "name", "category", "specification", "unit", "safety_stock", "shelf_life_days", "default_supplier_id"},
    "suppliers": {"organization_id", "farm_id", "area_id", "code", "name", "contact_name", "phone", "address", "settlement_days", "credit_limit", "note"},
    "customers": {"organization_id", "farm_id", "area_id", "code", "name", "contact_name", "phone", "address", "settlement_days", "credit_limit", "note"},
    "settings": {"organization_id", "farm_id", "area_id", "code", "name", "group_code", "value_text", "note"},
}
POND_STATUS_TRANSITIONS = {
    "build": {"stocked"}, "stocked": {"farming"}, "farming": {"rest", "clean"},
    "rest": {"stocked", "rebuild"}, "clean": {"rest", "rebuild"}, "rebuild": {"build"},
}
# 塘口档案业务约束（BUG-007 / BUG-M4-01 / BUG-M4-04 / BUG-M4-02）
MAX_CAPACITY_MU = Decimal("100000")
MAX_MASTER_QUANTITY = Decimal("999999999999999.999")
STOCK_QUANTITY_SOURCES = {"estimated", "manual", "measured", "sampled", "corrected"}
CREATE_POND_STATUSES = {"build", "stocked"}
ALL_POND_STATUSES = set(POND_STATUS_TRANSITIONS) | set().union(*POND_STATUS_TRANSITIONS.values())


class MasterDataService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def can(user: dict[str, Any], resource: str, action: str) -> bool:
        permissions = set(user.get("permissions") or [])
        resource_code = resource.replace("-", "_")
        return f"master_data.{action}" in permissions or f"master_data.{resource_code}.{action}" in permissions

    @classmethod
    def require(cls, user: dict[str, Any], resource: str, action: str) -> None:
        if not cls.can(user, resource, action):
            raise DomainError("FORBIDDEN", "当前账号没有主数据权限", 403)

    @staticmethod
    def resource(value: str) -> str:
        if value not in RESOURCES:
            raise DomainError("MASTER_RESOURCE_NOT_FOUND", "主数据类型不存在", 404)
        return value

    @classmethod
    def result(cls, row: dict[str, Any], user: dict[str, Any], resource: str) -> dict[str, Any]:
        status = str(row.get("status", "draft"))
        actions = {
            "draft": ["view", "edit", "delete", "submit"],
            "submitted": ["view", "edit", "verify"],
            "verified": ["view"],
            "archived": ["view"],
        }.get(status, ["view"])
        actions = [action for action in actions if action == "view" or cls.can(user, resource, "verify" if action == "verify" else "manage")]
        normalized = {**row, "version": int(row.get("row_version", row.get("version", 1))), "allowed_actions": actions}
        for key, value in list(normalized.items()):
            if hasattr(value, "isoformat"):
                normalized[key] = value.isoformat()
        return normalized

    def list_records(self, user: dict[str, Any], resource: str, **query: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "view")
        page = self.store.list_records(resource, user=user, **query)
        return {**page, "items": [self.result(item, user, resource) for item in page["items"]]}

    def get(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "view")
        row, timeline = self.store.get_detail(resource, record_id)
        if row is None:
            raise DomainError("MASTER_RECORD_NOT_FOUND", "主数据记录不存在", 404)
        self._require_record_scope(user, resource, row)
        normalized = self.result(row, user, resource)
        normalized["timeline_preview"] = [self._normalize(item) for item in timeline]
        if resource == "ponds":
            pending = self.store.get_pending_pond_status_change(record_id)
            normalized["pending_status_change"] = self._normalize(pending) if pending else None
            normalized["status_change_targets"] = sorted(POND_STATUS_TRANSITIONS.get(str(row.get("pond_status")), set()))
            normalized["can_request_status_change"] = row["status"] == "verified" and pending is None and self.can(user, resource, "manage")
            normalized["can_verify_status_change"] = bool(pending and int(pending["requested_by"]) != int(user["id"]) and self.can(user, resource, "verify"))
        return normalized

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}

    def create(self, user: dict[str, Any], resource: str, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        if not isinstance(payload, dict):
            raise DomainError("MASTER_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        clean = self._clean(resource, payload)
        clean = self._scope_payload(user, resource, clean)
        if not str(clean.get("code", "")).strip() or not str(clean.get("name", "")).strip():
            raise DomainError("MASTER_REQUIRED_FIELDS", "编码和名称不能为空", 400)
        if resource == "ponds":
            self._validate_ponds_fields(clean, creating=True)
        self._validate_business_fields(resource, clean)
        return self.result(self.store.create_record(resource, clean, user_id=int(user["id"])), user, resource)

    @staticmethod
    def _validate_ponds_fields(clean: dict[str, Any], *, creating: bool = False) -> None:
        """塘口字段预校验：非法值一律 400，不落库产生 500（BUG-M4-01/02/04、BUG-007）。"""
        if "name" in clean and clean.get("name") is not None:
            if len(str(clean["name"])) > 120:
                raise DomainError("FIELD_INVALID", "字段 name 超长，最多 120 个字符", 400)
        if "pond_status" in clean and clean.get("pond_status") not in (None, ""):
            status = str(clean["pond_status"])
            if creating and status not in CREATE_POND_STATUSES:
                raise DomainError("POND_STATUS_INVALID", "新建塘口状态只能是筹建(build)或已放养(stocked)", 400)
            if status not in ALL_POND_STATUSES:
                raise DomainError("POND_STATUS_INVALID", "塘口状态取值无效", 400)
        if "capacity_mu" in clean and clean.get("capacity_mu") not in (None, ""):
            try:
                capacity = Decimal(str(clean["capacity_mu"]))
            except InvalidOperation as exc:
                raise DomainError("FIELD_INVALID", "字段 capacity_mu 必须是有效数字", 400) from exc
            if not capacity.is_finite() or capacity <= 0 or capacity > MAX_CAPACITY_MU:
                raise DomainError("FIELD_INVALID", f"字段 capacity_mu 必须是 0 到 {MAX_CAPACITY_MU} 之间的正数", 400)
        if "aerator_count" in clean and clean.get("aerator_count") not in (None, ""):
            try:
                aerators = int(str(clean["aerator_count"]).strip())
            except (TypeError, ValueError) as exc:
                raise DomainError("FIELD_INVALID", "字段 aerator_count 必须是非负整数", 400) from exc
            if aerators < 0 or aerators > 9999:
                raise DomainError("FIELD_INVALID", "字段 aerator_count 必须在 0 到 9999 之间", 400)
        for field in ("stocking_spec", "current_spec"):
            if field in clean and clean.get(field) not in (None, ""):
                if len(str(clean[field])) > 40:
                    raise DomainError("FIELD_INVALID", f"字段 {field} 超长，最多 40 个字符", 400)
        if "stock_quantity" in clean and clean.get("stock_quantity") not in (None, ""):
            try:
                quantity = Decimal(str(clean["stock_quantity"]))
            except InvalidOperation as exc:
                raise DomainError("FIELD_INVALID", "字段 stock_quantity 必须是有效数字", 400) from exc
            if not quantity.is_finite() or quantity < 0 or quantity > MAX_MASTER_QUANTITY:
                raise DomainError("FIELD_INVALID", f"字段 stock_quantity 必须在 0 到 {MAX_MASTER_QUANTITY} 之间", 400)
        if "stock_quantity_source" in clean and clean.get("stock_quantity_source") not in (None, ""):
            if str(clean["stock_quantity_source"]) not in STOCK_QUANTITY_SOURCES:
                raise DomainError(
                    "FIELD_INVALID",
                    f"字段 stock_quantity_source 取值必须是 {'/'.join(sorted(STOCK_QUANTITY_SOURCES))}",
                    400,
                )

    @staticmethod
    def _validate_business_fields(resource: str, clean: dict[str, Any]) -> None:
        if resource == "materials" and clean.get("safety_stock") not in (None, ""):
            try:
                value = Decimal(str(clean["safety_stock"]))
            except InvalidOperation as exc:
                raise DomainError("SAFETY_STOCK_INVALID", "安全库存必须是非负数字", 400) from exc
            if not value.is_finite() or value < 0:
                raise DomainError("SAFETY_STOCK_INVALID", "安全库存必须是非负数字", 400)
        if resource in {"suppliers", "customers"}:
            if clean.get("credit_limit") not in (None, ""):
                try:
                    credit = Decimal(str(clean["credit_limit"]))
                except InvalidOperation as exc:
                    raise DomainError("CREDIT_LIMIT_INVALID", "信用额度必须是非负数字", 400) from exc
                if not credit.is_finite() or credit < 0:
                    raise DomainError("CREDIT_LIMIT_INVALID", "信用额度必须是非负数字", 400)
            if clean.get("phone") not in (None, ""):
                phone = str(clean["phone"]).strip()
                if not re.fullmatch(r"[0-9+()\-\.\s#xX]{3,40}", phone) or not re.search(r"\d", phone):
                    raise DomainError("PHONE_INVALID", "联系电话格式无效", 400)

    @staticmethod
    def _clean(resource: str, payload: dict[str, Any], *, allow_version: bool = False) -> dict[str, Any]:
        accepted = MASTER_FIELDS[resource] | ({"expected_version"} if allow_version else set())
        if set(payload) - accepted or set(payload) & RESERVED_FIELDS:
            raise DomainError("MASTER_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in MASTER_FIELDS[resource]}

    @staticmethod
    def _scope_payload(user: dict[str, Any], resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return payload
        areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
        if areas:
            if resource == "farms" or (resource == "areas" and payload.get("area_id") is None):
                raise DomainError("DATA_SCOPE_FORBIDDEN", "当前数据范围不允许维护该主数据", 403)
            try:
                requested = int(payload["area_id"]) if payload.get("area_id") is not None else None
            except (TypeError, ValueError) as exc:
                raise DomainError("FIELD_INVALID", "区域编号必须是正整数", 400) from exc
            if requested is not None and requested < 1:
                raise DomainError("FIELD_INVALID", "区域编号必须是正整数", 400)
            if requested is not None and requested not in areas:
                raise DomainError("DATA_SCOPE_FORBIDDEN", "不能写入授权区域之外的数据", 403)
            if requested is None and len(areas) == 1:
                payload = {**payload, "area_id": next(iter(areas))}
        if any(item.get("scope_type") == "personal" for item in scopes):
            if not areas:
                raise DomainError("DATA_SCOPE_FORBIDDEN", "仅本人数据范围不能维护跨区域主数据", 403)
        return payload

    @staticmethod
    def _require_record_scope(user: dict[str, Any], resource: str, row: dict[str, Any]) -> None:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return
        areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
        area_id = int(row["id"]) if resource == "areas" else int(row.get("area_id") or 0)
        personal = any(item.get("scope_type") == "personal" for item in scopes)
        if (areas and area_id in areas) or (personal and int(row.get("created_by") or 0) == int(user["id"])):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的数据", 403)

    def _current(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        row = self.store.get_record(self.resource(resource), record_id)
        if row is None:
            raise DomainError("MASTER_RECORD_NOT_FOUND", "主数据记录不存在", 404)
        self._require_record_scope(user, resource, row)
        return row

    @staticmethod
    def _expected(payload: Any) -> int:
        return parse_expected_version(payload)

    def update(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        if resource == "ponds" and isinstance(payload, dict) and "pond_status" in payload:
            raise DomainError("POND_STATUS_CHANGE_REQUIRES_REVIEW", "塘口状态必须通过独立申请与核验流程变更", 409)
        current = self._current(user, resource, record_id)
        require_editable(str(current["status"]))
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self._clean(resource, payload, allow_version=True)
        clean = self._scope_payload(user, resource, clean)
        if not clean:
            raise DomainError("MASTER_NO_CHANGES", "没有可保存的修改", 400)
        if resource == "ponds":
            self._validate_ponds_fields(clean, creating=False)
        self._validate_business_fields(resource, clean)
        return self.result(self.store.update_record(resource, record_id, clean, expected_version=expected, user_id=int(user["id"])), user, resource)

    def submit(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        return self._transition(user, resource, record_id, payload, "draft", "submitted")

    def verify(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "verify")
        current = self._current(user, resource, record_id)
        if self._expected(payload) != int(current["row_version"]):
            return self._transition(user, resource, record_id, payload, "submitted", "verified")
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "主数据禁止经办人自审", 403)
        return self._transition(user, resource, record_id, payload, "submitted", "verified")

    def _transition(self, user: dict[str, Any], resource: str, record_id: int, payload: Any, before: str, after: str) -> dict[str, Any]:
        current = self._current(user, resource, record_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前状态不允许执行该操作", 409)
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        return self.result(self.store.set_status(resource, record_id, after, expected_version=expected, user_id=int(user["id"])), user, resource)

    def delete(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        current = self._current(user, resource, record_id)
        require_deletable(str(current["status"]), has_references=bool(current.get("has_references")))
        return self.result(self.store.delete_draft(resource, record_id, user_id=int(user["id"])), user, resource)

    def request_pond_status_change(self, user: dict[str, Any], pond_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "ponds", "manage")
        current = self._current(user, "ponds", pond_id)
        if current["status"] != "verified":
            raise DomainError("POND_NOT_VERIFIED", "塘口资料核验后才能申请状态变更", 409)
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        target = str((payload or {}).get("to_status", ""))
        reason = str((payload or {}).get("reason", "")).strip()
        if target not in POND_STATUS_TRANSITIONS.get(str(current.get("pond_status")), set()):
            raise DomainError("INVALID_POND_STATUS_TRANSITION", "该塘口状态流转不符合业务规则", 409)
        if not reason or len(reason) > 500:
            raise DomainError("POND_STATUS_REASON_REQUIRED", "必须填写 1 到 500 字的状态变更原因", 400)
        return self._normalize(self.store.request_pond_status_change(pond_id, to_status=target, reason=reason, expected_pond_version=expected, user_id=int(user["id"])))
    def verify_pond_status_change(self, user: dict[str, Any], pond_id: int, request_id: int, payload: Any) -> dict[str, Any]:
        self.require(user, "ponds", "verify")
        self._current(user, "ponds", pond_id)
        expected = self._expected(payload)
        expected_pond = parse_expected_version(payload, "expected_pond_version")
        pond, change = self.store.verify_pond_status_change(pond_id, request_id, expected_version=expected, expected_pond_version=expected_pond, user_id=int(user["id"]))
        return {"record": self.result(pond, user, "ponds"), "status_change": self._normalize(change)}

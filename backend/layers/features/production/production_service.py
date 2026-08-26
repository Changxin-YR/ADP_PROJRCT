from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError, parse_expected_version, require_deletable, require_editable, verify_version
from backend.layers.features.production.daily_operation_rules import normalize_daily_operation_payload
from backend.layers.common.files.evidence import evidence_from_payload


RESOURCES = {
    "batches", "samplings", "transfers", "losses", "harvests",
    "feed-plans", "feed-tasks", "feed-logs", "daily-operations",
}
HIGH_RISK = {"transfers", "losses", "harvests"}
COMMON_FIELDS = {
    "organization_id", "farm_id", "area_id", "code", "name", "pond_id", "batch_id",
    "target_pond_id", "quantity", "weight_kg", "happened_at", "note", "payload",
    "evidence_attachment_ids", "material_id", "assigned_user_id", "planned_at",
    "feed_plan_id", "feed_task_id", "material_issue_request_id",
}
FIELDS = {
    resource: set(COMMON_FIELDS) | ({"operation_type"} if resource == "daily-operations" else set())
    for resource in RESOURCES - {"batches"}
} | {
    "batches": {
        "organization_id", "farm_id", "area_id", "code", "name", "pond_id", "species",
        "initial_quantity", "initial_weight_kg", "stocked_at", "expected_harvest_date", "note",
        "batch_status",
    },
}
RESERVED = {"id", "status", "row_version", "version", "allowed_actions", "created_by", "updated_by", "verified_by", "created_at", "updated_at"}

# DECIMAL(18,3) 上限：批次 1e18 等超界数量在服务层直接拒绝（BUG-M4-02）。
MAX_PRODUCTION_QUANTITY = Decimal("999999999999999.999")


class ProductionService:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def resource(value: str) -> str:
        if value not in RESOURCES:
            raise DomainError("PRODUCTION_RESOURCE_NOT_FOUND", "生产业务类型不存在", 404)
        return value

    @staticmethod
    def can(user: dict[str, Any], resource: str, action: str) -> bool:
        permissions = set(user.get("permissions") or [])
        code = resource.replace("-", "_")
        return f"production.{action}" in permissions or f"production.{code}.{action}" in permissions

    @classmethod
    def require(cls, user: dict[str, Any], resource: str, action: str) -> None:
        if not cls.can(user, resource, action):
            raise DomainError("FORBIDDEN", "当前账号没有生产业务权限", 403)

    @classmethod
    def result(cls, row: dict[str, Any], user: dict[str, Any], resource: str) -> dict[str, Any]:
        actions = {
            "draft": ["view", "edit", "delete", "submit"],
            "submitted": ["view", "edit", "verify"],
            "verified": ["view", "correct"],
            "corrected": ["view"],
        }.get(str(row.get("status")), ["view"])
        actions = [action for action in actions if action == "view" or cls.can(user, resource, "verify" if action == "verify" else "manage")]
        result = {**row, "version": int(row.get("row_version", row.get("version", 1))), "allowed_actions": actions}
        for key, value in list(result.items()):
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        return result

    @staticmethod
    def _clean(resource: str, payload: Any, *, allow_version: bool = False) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DomainError("PRODUCTION_PAYLOAD_INVALID", "请求内容必须是对象", 400)
        accepted = FIELDS[resource] | ({"expected_version"} if allow_version else set())
        if set(payload) - accepted or set(payload) & RESERVED:
            raise DomainError("PRODUCTION_FIELD_INVALID", "请求包含不允许修改的字段", 400)
        return {key: value for key, value in payload.items() if key in FIELDS[resource]}

    @staticmethod
    def _positive(payload: dict[str, Any], *fields: str) -> None:
        for field in fields:
            if payload.get(field) is None:
                continue
            try:
                value = Decimal(str(payload[field]))
            except InvalidOperation as exc:
                raise DomainError("PRODUCTION_VALUE_INVALID", "数量和重量格式无效", 400) from exc
            if not value.is_finite():
                raise DomainError("PRODUCTION_VALUE_INVALID", "数量和重量格式无效", 400)
            if value < 0:
                raise DomainError("PRODUCTION_VALUE_INVALID", "数量和重量不能为负数", 400)
            if value > MAX_PRODUCTION_QUANTITY:
                raise DomainError("PRODUCTION_VALUE_INVALID", "数量或重量超出允许范围", 400)

    @staticmethod
    def _validate_batch_dates(clean: dict[str, Any]) -> None:
        """放苗日期/预计出塘日期格式校验 + 顺序校验（BUG-M4-06/07、2026-02-30 等非法日期 400）。"""
        stocked: datetime | None = None
        harvest: date | None = None
        stocked_text = clean.get("stocked_at")
        if stocked_text not in (None, ""):
            try:
                stocked = datetime.fromisoformat(str(stocked_text).replace("Z", "+00:00"))
            except ValueError as exc:
                raise DomainError("PRODUCTION_DATE_INVALID", "放苗日期格式无效", 400) from exc
        harvest_text = clean.get("expected_harvest_date")
        if harvest_text not in (None, ""):
            try:
                harvest = harvest_text if isinstance(harvest_text, date) and not isinstance(harvest_text, datetime) else date.fromisoformat(str(harvest_text))
            except (TypeError, ValueError) as exc:
                raise DomainError("PRODUCTION_DATE_INVALID", "预计出塘日期格式无效", 400) from exc
        if stocked is not None and harvest is not None and harvest < stocked.date():
            raise DomainError("PRODUCTION_DATE_INVALID", "预计出塘日期不能早于放苗日期", 400)

    def _validate_batches(self, clean: dict[str, Any], *, creating: bool) -> None:
        self._positive(clean, "initial_quantity", "initial_weight_kg")
        if clean.get("initial_quantity") not in (None, ""):
            try:
                quantity = Decimal(str(clean["initial_quantity"]))
            except InvalidOperation as exc:
                raise DomainError("PRODUCTION_VALUE_INVALID", "放苗数量格式无效", 400) from exc
            if quantity <= 0:
                raise DomainError("PRODUCTION_QUANTITY_INVALID", "放苗数量必须大于 0", 400)
        self._validate_batch_dates(clean)

    @staticmethod
    def _normalize_daily_operation(clean: dict[str, Any], current_payload: dict[str, Any] | None) -> None:
        """日常作业类型化（BUG-012）：枚举与关键参数校验见 daily_operation_rules。"""
        normalize_daily_operation_payload(clean, current_payload)

    def list_records(self, user: dict[str, Any], resource: str, **query: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "view")
        page = self.store.list_records(resource, user=user, **query)
        return {**page, "items": [self.result(row, user, resource) for row in page["items"]]}

    def get(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "view")
        return self.result(self._current(user, resource, record_id), user, resource)

    def create(self, user: dict[str, Any], resource: str, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        clean = self._clean(resource, payload)
        if not str(clean.get("code", "")).strip() or not str(clean.get("name", "")).strip():
            raise DomainError("PRODUCTION_REQUIRED_FIELDS", "单号和名称不能为空", 400)
        if resource == "batches":
            if not clean.get("pond_id") or not str(clean.get("species", "")).strip():
                raise DomainError("PRODUCTION_REQUIRED_FIELDS", "批次必须填写塘口和品种", 400)
            self._validate_batches(clean, creating=True)
        else:
            self._positive(clean, "quantity", "weight_kg")
            if resource in {"transfers", "losses", "harvests", "feed-logs"} and clean.get("quantity") not in (None, ""):
                if Decimal(str(clean["quantity"])) <= 0:
                    raise DomainError("PRODUCTION_QUANTITY_INVALID", "业务数量必须大于 0", 400)
        if resource == "daily-operations":
            self._normalize_daily_operation(clean, current_payload=None)
        if resource == "transfers" and clean.get("pond_id") == clean.get("target_pond_id"):
            raise DomainError("TRANSFER_TARGET_INVALID", "转入塘口不能与转出塘口相同", 400)
        return self.result(self.store.create_record(resource, clean, user=user, user_id=int(user["id"])), user, resource)

    @staticmethod
    def _require_record_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        scopes = user.get("data_scopes") or []
        if not scopes or any(item.get("scope_type") == "farm" for item in scopes):
            return
        areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
        personal = any(item.get("scope_type") == "personal" for item in scopes)
        if (areas and int(row.get("area_id") or 0) in areas) or (personal and int(row.get("created_by") or 0) == int(user["id"])):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的生产记录", 403)

    def _current(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        row = self.store.get_record(resource, record_id)
        if row is None:
            raise DomainError("PRODUCTION_RECORD_NOT_FOUND", "生产记录不存在", 404)
        self._require_record_scope(user, row)
        return row

    @staticmethod
    def _expected(payload: Any) -> int:
        return parse_expected_version(payload)

    def update(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        current = self._current(user, resource, record_id)
        require_editable(str(current["status"]))
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self._clean(resource, payload, allow_version=True)
        if not clean:
            raise DomainError("PRODUCTION_NO_CHANGES", "没有可保存的修改", 400)
        self._positive(clean, "quantity", "weight_kg", "initial_quantity", "initial_weight_kg")
        if resource == "batches":
            self._validate_batches({**current, **clean}, creating=False)
        elif resource in {"transfers", "losses", "harvests", "feed-logs"} and clean.get("quantity") not in (None, ""):
            if Decimal(str(clean["quantity"])) <= 0:
                raise DomainError("PRODUCTION_QUANTITY_INVALID", "业务数量必须大于 0", 400)
        if resource == "daily-operations":
            self._normalize_daily_operation(clean, current_payload=current.get("payload") if isinstance(current.get("payload"), dict) else None)
        return self.result(self.store.update_record(resource, record_id, clean, expected_version=expected, user=user, user_id=int(user["id"])), user, resource)

    def correct(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        current = self._current(user, resource, record_id)
        if current["status"] != "verified":
            raise DomainError("INVALID_STATE_TRANSITION", "仅已核验记录可以发起更正", 409)
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        clean = self._clean(resource, payload, allow_version=True)
        if not str(clean.get("code", "")).strip() or clean.get("code") == current.get("code"):
            raise DomainError("CORRECTION_CODE_REQUIRED", "更正单必须使用新的单号", 400)
        if not str(clean.get("note", "")).strip():
            raise DomainError("CORRECTION_REASON_REQUIRED", "更正单必须填写更正原因", 400)
        self._positive(clean, "quantity", "weight_kg", "initial_quantity", "initial_weight_kg")
        if resource == "batches":
            self._validate_batches({**current, **clean}, creating=False)
        elif resource in {"transfers", "losses", "harvests", "feed-logs"} and clean.get("quantity") not in (None, ""):
            if Decimal(str(clean["quantity"])) <= 0:
                raise DomainError("PRODUCTION_QUANTITY_INVALID", "业务数量必须大于 0", 400)
        if resource == "daily-operations":
            self._normalize_daily_operation(clean, current_payload=current.get("payload") if isinstance(current.get("payload"), dict) else None)
        row = self.store.create_correction(
            resource, record_id, clean, expected_version=expected, user=user, user_id=int(user["id"]),
        )
        return self.result(row, user, resource)

    def submit(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        return self._transition(user, resource, record_id, payload, "draft", "submitted")

    def verify(self, user: dict[str, Any], resource: str, record_id: int, payload: Any) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "verify")
        current = self._current(user, resource, record_id)
        evidence = evidence_from_payload(payload, current.get("evidence_attachment_ids"))
        if resource in HIGH_RISK and not evidence:
            raise DomainError("EVIDENCE_REQUIRED", "转塘、损耗和出塘核验必须上传现场凭据", 400)
        if int(user["id"]) in {int(current.get("created_by") or 0), int(current.get("updated_by") or 0)}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "生产业务禁止经办人自审", 403)
        if resource == "feed-logs" and not all(current.get(key) for key in ("feed_task_id", "material_issue_request_id")):
            raise DomainError("FEED_LOG_LINKS_REQUIRED", "投喂记录核验前必须关联投喂任务和领料申请", 409)
        return self._transition(user, resource, record_id, payload, "submitted", "verified", evidence=evidence)

    def _transition(self, user: dict[str, Any], resource: str, record_id: int, payload: Any, before: str, after: str, *, evidence: list[int] | None = None) -> dict[str, Any]:
        current = self._current(user, resource, record_id)
        if current["status"] != before:
            raise DomainError("INVALID_STATE_TRANSITION", "当前状态不允许执行该操作", 409)
        expected = self._expected(payload)
        verify_version(expected_version=expected, current_version=int(current["row_version"]))
        row = self.store.set_status(resource, record_id, after, expected_version=expected, user_id=int(user["id"]), evidence_attachment_ids=evidence)
        return self.result(row, user, resource)

    def delete(self, user: dict[str, Any], resource: str, record_id: int) -> dict[str, Any]:
        resource = self.resource(resource)
        self.require(user, resource, "manage")
        current = self._current(user, resource, record_id)
        require_deletable(str(current["status"]), has_references=bool(current.get("has_references")))
        return self.result(self.store.delete_draft(resource, record_id, user_id=int(user["id"])), user, resource)

    def reconcile(self, user: dict[str, Any], batch_id: int) -> dict[str, Any]:
        self.require(user, "batches", "view")
        self._current(user, "batches", batch_id)
        return self.store.reconcile_batch(batch_id)

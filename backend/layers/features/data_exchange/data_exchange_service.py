from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.layers.common.files.attachments import prepare_attachment, save_private_file
from backend.layers.common.files.malware_scanner import MalwareScanner
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.template_catalog import all_templates, get_template
from backend.layers.features.data_exchange.workbooks import error_workbook, export_pdf_stream, export_workbook_stream, preview_workbook, template_workbook
from backend.layers.features.data_exchange.attachment_scope import attachment_permission_allows
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


COMMON_EXPORT_FILTERS = {"status", "search", "created_from", "created_to", "business_date_from", "business_date_to"}


class DataExchangeService:
    EXPORT_FILTERS = {"status", "search", "area_id", "pond_id", "warehouse_id", "supplier_id", "customer_id", "batch_id", "created_from", "created_to", "business_date_from", "business_date_to"}
    EXPORT_FILTERS_BY_RESOURCE = {
        resource: set(COMMON_EXPORT_FILTERS) for resource in {
            "materials", "imports", "farms", "areas", "pond-groups", "ponds", "suppliers", "customers", "business-settings",
            "batches", "samplings", "transfers", "losses", "harvests", "feed-plans", "feed-tasks", "feed-logs", "daily-operations",
            "receipts", "issues", "warehouse-transfers", "returns", "stocktakes", "scraps", "inventory-ledger", "stock-alerts",
            "purchase-orders", "payables", "payments", "sales-orders", "sales-deliveries", "receivables", "customer-receipts",
            "expenses", "cost-adjustments", "assets", "leases", "settlements",
        }
    }
    for _resource in ("pond-groups", "ponds", "batches", "samplings", "transfers", "losses", "harvests", "feed-plans", "feed-tasks", "feed-logs", "daily-operations"):
        EXPORT_FILTERS_BY_RESOURCE[_resource].update({"area_id", "pond_id"})
    for _resource in ("receipts", "issues", "warehouse-transfers", "returns", "stocktakes", "scraps"):
        EXPORT_FILTERS_BY_RESOURCE[_resource].update({"area_id", "warehouse_id", "batch_id"})
    EXPORT_FILTERS_BY_RESOURCE["inventory-ledger"].update({"warehouse_id", "batch_id"})
    EXPORT_FILTERS_BY_RESOURCE["stock-alerts"].update({"warehouse_id"})
    EXPORT_FILTERS_BY_RESOURCE["purchase-orders"].update({"area_id", "warehouse_id", "supplier_id"})
    EXPORT_FILTERS_BY_RESOURCE["payables"].update({"area_id", "supplier_id"})
    EXPORT_FILTERS_BY_RESOURCE["payments"].update({"area_id"})
    EXPORT_FILTERS_BY_RESOURCE["sales-orders"].update({"area_id", "pond_id", "batch_id", "customer_id"})
    EXPORT_FILTERS_BY_RESOURCE["sales-deliveries"].update({"area_id"})
    EXPORT_FILTERS_BY_RESOURCE["receivables"].update({"area_id", "customer_id"})
    EXPORT_FILTERS_BY_RESOURCE["customer-receipts"].update({"area_id"})
    EXPORT_FILTERS_BY_RESOURCE["expenses"].add("area_id")
    EXPORT_FILTERS_BY_RESOURCE["cost-adjustments"].add("area_id")
    EXPORT_FILTERS_BY_RESOURCE["assets"].add("area_id")
    EXPORT_FILTERS_BY_RESOURCE["leases"].add("area_id")
    EXPORT_FILTERS_BY_RESOURCE["settlements"].add("area_id")
    RESOURCE_PERMISSIONS = {
        "purchase-orders": "purchase.view", "payables": "finance.payable.view", "payments": "finance.payable.view",
        "sales-orders": "sales.view", "sales-deliveries": "sales.view", "receivables": "finance.receivable.view", "customer-receipts": "finance.receivable.view",
        "expenses": "cost.view", "cost-adjustments": "cost.view", "assets": "cost.view", "leases": "cost.view", "settlements": "cost.view",
        "receipts": "warehouse.view", "issues": "warehouse.view", "warehouse-transfers": "warehouse.view", "returns": "warehouse.view", "stocktakes": "warehouse.view", "scraps": "warehouse.view", "inventory-ledger": "warehouse.view", "stock-alerts": "warehouse.view",
        "batches": "production.view", "samplings": "production.view", "transfers": "production.view", "losses": "production.view", "harvests": "production.view", "feed-plans": "production.view", "feed-tasks": "production.view", "feed-logs": "production.view", "daily-operations": "production.view",
    }

    def __init__(self, store: Any, attachment_root: Path, scanner: MalwareScanner | None = None) -> None:
        self.store = store
        self.attachment_root = attachment_root
        self.scanner = scanner

    @staticmethod
    def require(user: dict[str, Any], permission: str) -> None:
        if permission not in set(user.get("permissions") or []):
            raise DomainError("FORBIDDEN", "当前账号没有数据交换权限", 403)

    @staticmethod
    def scope(user: dict[str, Any], organization_id: int) -> None:
        if organization_id < 1:
            raise DomainError("ORGANIZATION_REQUIRED", "必须选择所属企业", 400)
        scopes = require_active_scope(user)
        roles = {str(item.get("code")) for item in user.get("roles") or [] if isinstance(item, dict)}
        if "super_admin" in roles and any(item.get("scope_type") == "farm" and not item.get("organization_id") for item in scopes):
            return
        if not unrestricted(user) and organization_id not in {int(item["organization_id"]) for item in scopes if item.get("organization_id")}:
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问该企业的数据", 403)

    def templates(self, user: dict[str, Any]) -> list[dict[str, object]]:
        self.require(user, "data_exchange.view")
        return all_templates()

    def template_file(self, user: dict[str, Any], code: str) -> tuple[bytes, str]:
        self.require(user, "data_exchange.view")
        template = get_template(code)
        return template_workbook(template), template.version

    def preview(self, user: dict[str, Any], *, organization_id: int, template_code: str, file_name: str, content: bytes) -> dict[str, Any]:
        self.require(user, "data_exchange.import"); self.scope(user, organization_id)
        template = get_template(template_code)
        if template_code == "inventory-ledger":
            raise DomainError("IMPORT_TEMPLATE_NOT_IMPLEMENTED", "库存流水由系统自动生成（只追加账本），不支持外部导入，请使用导出功能获取流水", 409)
        if not template.importable:
            raise DomainError("IMPORT_TEMPLATE_NOT_CONNECTED", "该模板当前仅支持下载，尚未开放业务写入", 409)
        digest = hashlib.sha256(content).hexdigest()
        if self.store.find_import_hash(organization_id, template_code, digest):
            raise DomainError("IMPORT_FILE_DUPLICATE", "同一模板下该文件已上传，不允许重复导入", 409)
        result = preview_workbook(template, content)
        row_numbers = result.pop("row_numbers", [])
        format_bad_rows = {item["row"] for item in result["errors"]}
        clean_rows = [row for row, number in zip(result["preview_rows"], row_numbers) if number not in format_bad_rows]
        clean_numbers = [number for number in row_numbers if number not in format_bad_rows]
        business_errors = self.store.validate_rows(user, organization_id, template.code, clean_rows, clean_numbers) if clean_rows else []
        errors = result["errors"] + business_errors
        bad_rows = {item["row"] for item in errors}
        result.update(
            errors=errors,
            passed_rows=len([number for number in row_numbers if number not in bad_rows]),
            failed_rows=len(bad_rows),
            status="invalid" if errors else "ready",
        )
        return self.store.create_import({
            **result, "organization_id": organization_id, "template_code": template.code,
            "template_name": template.name, "template_version": template.version,
            "file_name": Path(file_name.replace("\\", "/")).name[:255], "file_sha256": digest,
            "imported_by": int(user["id"]),
        })

    def list_imports(self, user: dict[str, Any], *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self.require(user, "data_exchange.view")
        result = self.store.list_imports(user, page=page, page_size=page_size)
        if isinstance(result, list):
            return {"items": [self._decorate(row) for row in result], "page": 1, "page_size": len(result), "total": len(result), "has_next": False}
        return {**result, "items": [self._decorate(row) for row in result.get("items", [])]}

    def confirm(self, user: dict[str, Any], batch_id: int) -> dict[str, Any]:
        self.require(user, "data_exchange.import")
        row = self._current(user, batch_id); self.scope(user, int(row["organization_id"]))
        if row["status"] != "ready" or row.get("errors"):
            raise DomainError("IMPORT_NOT_READY", "仅校验全部通过的批次可以确认导入", 409)
        return self._decorate(self.store.confirm_import(batch_id, user))

    def revoke(self, user: dict[str, Any], batch_id: int) -> dict[str, Any]:
        self.require(user, "data_exchange.import")
        row = self._current(user, batch_id); self.scope(user, int(row["organization_id"]))
        if row["status"] != "imported":
            raise DomainError("IMPORT_NOT_IMPORTED", "仅已导入的批次可以撤销", 409)
        return self._decorate(self.store.revoke_import(batch_id, user))

    def errors(self, user: dict[str, Any], batch_id: int) -> bytes:
        self.require(user, "data_exchange.view")
        row = self._current(user, batch_id)
        if not row.get("errors"):
            raise DomainError("IMPORT_ERRORS_EMPTY", "该批次没有错误明细", 404)
        return error_workbook(row["errors"])

    def export(self, user: dict[str, Any], *, organization_id: int, resource: str, file_format: str, filters: Any, request_id: str) -> tuple[bytes, int]:
        self.require(user, "data_exchange.export"); self.scope(user, organization_id)
        required = self.RESOURCE_PERMISSIONS.get(resource)
        if required:
            roles = {str(item.get("code")) for item in user.get("roles") or [] if isinstance(item, dict)}
            if "super_admin" not in roles:
                self.require(user, required)
        if file_format not in {"xlsx", "pdf"} or not isinstance(filters, dict):
            raise DomainError("EXPORT_REQUEST_INVALID", "导出格式或筛选条件无效", 400)
        supported = self.EXPORT_FILTERS_BY_RESOURCE.get(resource, COMMON_EXPORT_FILTERS)
        unknown = set(filters) - supported
        if unknown:
            raise DomainError("EXPORT_FILTER_INVALID", f"不支持的导出筛选条件：{', '.join(sorted(unknown))}", 400)
        for key in ("area_id", "pond_id", "warehouse_id", "supplier_id", "customer_id", "batch_id"):
            if filters.get(key) not in (None, ""):
                try:
                    if int(filters[key]) < 1: raise ValueError
                except (TypeError, ValueError):
                    raise DomainError("EXPORT_FILTER_INVALID", f"筛选条件 {key} 必须为正整数", 400)
        for key in ("created_from", "created_to", "business_date_from", "business_date_to"):
            if filters.get(key) not in (None, ""):
                try: date.fromisoformat(str(filters[key]))
                except ValueError as exc: raise DomainError("EXPORT_FILTER_INVALID", f"筛选条件 {key} 日期格式无效", 400) from exc
        query = {str(key): value for key, value in filters.items()}
        generated_at = datetime.now(timezone.utc).isoformat()
        metadata = {"resource": resource, "generated_at": generated_at, "actor": user.get("name") or user["id"], "filters": query, "request_id": request_id}
        render = export_workbook_stream if file_format == "xlsx" else export_pdf_stream
        stream = getattr(self.store, "export_stream", None)
        export_filters = {**query, "_organization_id": organization_id}
        if callable(stream):
            with stream(user, resource, export_filters) as rows:
                artifact = render(rows, metadata)
        else:
            artifact = render(self.store.export_rows(user, resource, export_filters), metadata)
        export_id = self.store.record_export({"organization_id": organization_id, "resource": resource, "format": file_format, "filters": query, "row_count": artifact.row_count, "request_id": request_id, "exported_by": int(user["id"])})
        return artifact.content, export_id

    def upload_attachment(self, user: dict[str, Any], *, organization_id: int, entity_type: str, entity_id: int, file_name: str, media_type: str, content: bytes) -> dict[str, Any]:
        self.require(user, "attachment.manage"); self.scope(user, organization_id)
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}:[a-z][a-z0-9_-]{1,31}", entity_type) or entity_id < 1:
            raise DomainError("ATTACHMENT_TARGET_INVALID", "附件业务对象无效", 400)
        if not self.store.attachment_target_exists(organization_id, entity_type, entity_id):
            raise DomainError("ATTACHMENT_TARGET_NOT_FOUND", "附件关联的业务记录不存在或无权访问", 404)
        if not self.store.attachment_target_accessible(user, organization_id, entity_type, entity_id):
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问附件关联的业务记录", 403)
        if not attachment_permission_allows(user, entity_type):
            raise DomainError("FORBIDDEN", "当前账号没有查看该业务附件的权限", 403)
        metadata = prepare_attachment(original_name=file_name, media_type=media_type, content=content)
        if self.scanner is not None:
            self.scanner.scan(content=content, original_name=metadata.original_name)
        if self.store.find_attachment_hash(organization_id, entity_type, entity_id, metadata.sha256):
            raise DomainError("ATTACHMENT_DUPLICATE", "该业务记录已上传相同内容的附件", 409)
        path = save_private_file(self.attachment_root, metadata, content)
        try:
            payload = {**metadata.__dict__, "organization_id": organization_id, "entity_type": entity_type, "entity_id": entity_id, "uploaded_by": int(user["id"])}
            atomic = getattr(self.store, "create_scoped_attachment", None)
            return atomic(user, payload) if atomic else self.store.create_attachment(payload)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def attachments(self, user: dict[str, Any], entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        self.require(user, "attachment.manage")
        if not attachment_permission_allows(user, entity_type):
            raise DomainError("FORBIDDEN", "当前账号没有查看该业务附件的权限", 403)
        return self.store.list_attachments(user, entity_type, entity_id)

    def attachment_file(self, user: dict[str, Any], attachment_id: int) -> tuple[Path, dict[str, Any]]:
        self.require(user, "attachment.manage")
        row = self.store.get_attachment(user, attachment_id)
        if not row:
            raise DomainError("ATTACHMENT_NOT_FOUND", "附件不存在或无权访问", 404)
        if not attachment_permission_allows(user, str(row.get("entity_type") or "")):
            raise DomainError("FORBIDDEN", "当前账号没有查看该业务附件的权限", 403)
        path = self.attachment_root.resolve() / row["storage_name"]
        if path.parent != self.attachment_root.resolve() or not path.is_file():
            raise DomainError("ATTACHMENT_FILE_MISSING", "附件文件不存在", 404)
        return path, row

    def _current(self, user: dict[str, Any], batch_id: int) -> dict[str, Any]:
        row = self.store.get_import(batch_id, user)
        if not row:
            raise DomainError("IMPORT_BATCH_NOT_FOUND", "导入批次不存在或无权访问", 404)
        return row

    @staticmethod
    def _decorate(row: dict[str, Any]) -> dict[str, Any]:
        template = get_template(str(row["template_code"]))
        return {**row, "template_name": template.name}

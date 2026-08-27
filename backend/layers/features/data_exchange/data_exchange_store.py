from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator
import pymysql
from backend.config.settings import Settings
from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.query_guard import sql_identifier
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.export_queries import EXPORT_AREA_COLUMNS, EXPORT_PERSONAL_COLUMNS, EXPORT_QUERIES
# 表名与列名只允许来自本模块固定映射，动态值一律参数绑定（见 query_guard.py）。
from backend.layers.features.data_exchange.attachment_scope import attachment_target, create_scoped_attachment, target_scope_allows
from backend.layers.features.data_exchange.import_scope_validation import validate_import_scope
from backend.layers.features.data_exchange.import_validation import validate_rows as validate_import_rows
from backend.layers.features.data_exchange.importers import get_importer
from backend.layers.common.security.data_scope import require_active_scope, unrestricted
class MySqlDataExchangeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditLogger()

    @staticmethod
    def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for source, target in (("preview_rows_json", "preview_rows"), ("errors_json", "errors")):
            value = result.pop(source, None)
            result[target] = json.loads(value) if isinstance(value, str) else (value or [])
        for key, value in list(result.items()):
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        return result
    @staticmethod
    def _organizations(user: dict[str, Any]) -> set[int] | None:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return None
        roles = {str(item.get("code")) for item in user.get("roles") or [] if isinstance(item, dict)}
        if "super_admin" in roles and any(item.get("scope_type") == "farm" and not item.get("organization_id") for item in scopes):
            return None
        return {int(item["organization_id"]) for item in scopes if item.get("organization_id")} if scopes else set()

    def find_import_hash(self, organization_id: int, template_code: str, sha256: str) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM data_import_batches WHERE organization_id=%s AND template_code=%s AND file_sha256=%s", (organization_id, template_code, sha256))
            return self._decode(cursor.fetchone())

    def create_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO data_import_batches (organization_id,template_code,template_version,file_name,file_sha256,total_rows,passed_rows,failed_rows,status,preview_rows_json,errors_json,imported_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (payload["organization_id"], payload["template_code"], payload["template_version"], payload["file_name"], payload["file_sha256"], payload["total_rows"], payload["passed_rows"], payload["failed_rows"], payload["status"], json.dumps(payload["preview_rows"], ensure_ascii=False), json.dumps(payload["errors"], ensure_ascii=False), payload["imported_by"]),
                )
            except pymysql.IntegrityError as exc:
                raise DomainError("IMPORT_FILE_DUPLICATE", "同一模板下该文件已上传，不允许重复导入", 409) from exc
            batch_id = int(cursor.lastrowid)
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s", (batch_id,))
            row = self._decode(cursor.fetchone()) or {}
            self._audit(connection, int(payload["imported_by"]), "preview_import", batch_id, after=row)
            return row

    def list_imports(self, user: dict[str, Any], *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        organizations = self._organizations(user)
        where, params = ("", ()) if organizations is None else (f" WHERE organization_id IN ({','.join(['%s'] * len(organizations))})", tuple(organizations))
        if organizations == set():
            return {"items": [], "page": max(1, int(page)), "page_size": max(1, min(100, int(page_size))), "total": 0, "has_next": False}
        page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM data_import_batches{where}", params)
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT * FROM data_import_batches{where} ORDER BY id DESC LIMIT %s OFFSET %s", params + (page_size, (page - 1) * page_size))
            items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}
    def get_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s", (batch_id,))
            row = self._decode(cursor.fetchone())
        allowed = self._organizations(user)
        return row if row and (allowed is None or int(row["organization_id"]) in allowed) else None
    def validate_rows(self, user: dict[str, Any], organization_id: int, template_code: str, rows: list[dict[str, Any]], row_numbers: list[int]) -> list[dict[str, Any]]:
        """预览阶段业务校验（编号唯一、关联对象存在、非法状态等），错误逐行列+中文原因。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            errors = validate_import_rows(cursor, organization_id, template_code, rows, row_numbers)
            return errors + validate_import_scope(cursor, user, organization_id, template_code, rows, row_numbers)
    def confirm_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s FOR UPDATE", (batch_id,))
            before = self._decode(cursor.fetchone())
            if not before or before["status"] != "ready":
                raise DomainError("IMPORT_NOT_READY", "仅校验全部通过的批次可以确认导入", 409)
            inserted = self._insert_rows(cursor, before, user)
            cursor.execute("UPDATE data_import_batches SET status='imported',imported_count=%s,imported_at=NOW() WHERE id=%s", (len(inserted), batch_id))
            for entity_type, entity_id in inserted:
                cursor.execute("INSERT INTO data_import_items (import_batch_id,entity_type,entity_id) VALUES (%s,%s,%s)", (batch_id, entity_type, entity_id))
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s", (batch_id,))
            after = self._decode(cursor.fetchone()) or {}
            self._audit(connection, int(user["id"]), "confirm_import", batch_id, before=before, after=after)
            return after

    def _insert_rows(self, cursor: Any, batch: dict[str, Any], user: dict[str, Any]) -> list[tuple[str, int]]:
        code, organization_id, user_id = batch["template_code"], int(batch["organization_id"]), int(user["id"])
        importer = get_importer(code)
        if importer is None:
            raise DomainError("IMPORT_TEMPLATE_NOT_CONNECTED", "该模板当前仅支持下载，尚未开放业务写入", 409)
        inserted: list[tuple[str, int]] = []
        try:
            for row in batch["preview_rows"]:
                entity_type, entity_id = importer(cursor, row, organization_id=organization_id, user=user, user_id=user_id)
                inserted.append((entity_type, entity_id))
        except pymysql.IntegrityError as exc:
            raise DomainError("IMPORT_RECORD_CONFLICT", "导入内容与已有正式或草稿记录冲突，整批已回滚", 409) from exc
        return inserted
    # 撤销：entity_type -> (业务表, 是否为只追加账本)
    REVOKE_TARGETS = {
        "master:ponds": ("ponds", False), "master:materials": ("materials", False),
        "master:suppliers": ("business_partners", False), "master:customers": ("business_partners", False),
        "master:business-settings": ("business_settings", False),
        "production:batches": ("production_batches", False),
        "production:samplings": ("production_documents", False), "production:transfers": ("production_documents", False),
        "production:losses": ("production_documents", False), "production:harvests": ("production_documents", False),
        "production:feed-plans": ("production_documents", False), "production:feed-tasks": ("production_documents", False),
        "production:feed-logs": ("production_documents", False), "production:daily-operations": ("production_documents", False),
        "production:stocking": ("batch_stock_records", True),
        "warehouse:receipts": ("warehouse_documents", False), "warehouse:issues": ("warehouse_documents", False),
        "warehouse:transfers": ("warehouse_documents", False), "warehouse:returns": ("warehouse_documents", False),
        "warehouse:stocktakes": ("warehouse_documents", False), "warehouse:scraps": ("warehouse_documents", False),
        "purchase:orders": ("purchase_orders", False), "purchase:payments": ("purchase_payments", False),
        "sales:orders": ("sales_orders", False), "sales:receipts": ("sales_receipts", False),
        "cost:entries": ("cost_entries", False), "cost:assets": ("cost_assets", False),
        "cost:adjustments": ("cost_entries", False),
    }
    def revoke_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any]:
        """撤销已导入批次：事务删除该批次创建的草稿并置 undone；被引用或已流转→409。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s FOR UPDATE", (batch_id,))
            before = self._decode(cursor.fetchone())
            if not before:
                raise DomainError("IMPORT_BATCH_NOT_FOUND", "导入批次不存在或无权访问", 404)
            if before["status"] != "imported":
                raise DomainError("IMPORT_NOT_IMPORTED", "仅已导入的批次可以撤销", 409)
            cursor.execute("SELECT entity_type,entity_id FROM data_import_items WHERE import_batch_id=%s ORDER BY id DESC", (batch_id,))
            items = [dict(row) for row in cursor.fetchall()]
            for item in items:
                table, ledger = self.REVOKE_TARGETS.get(str(item["entity_type"]), (None, False))
                if table is None:
                    raise DomainError("IMPORT_REVOKE_REFERENCED", "批次内存在无法撤销的记录类型，不能撤销", 409)
                if ledger:
                    raise DomainError("IMPORT_REVOKE_LEDGER", "批次包含库存/投苗流水（只追加账本），不能撤销，请使用业务更正流程", 409)
                cursor.execute(f"SELECT status FROM {table} WHERE id=%s", (int(item["entity_id"]),))
                current = cursor.fetchone()
                if current is None or current["status"] != "draft":
                    raise DomainError("IMPORT_REVOKE_REFERENCED", "批次内记录已被后续业务引用或已提交核验，不能撤销", 409)
            try:
                for item in items:
                    table, _ledger = self.REVOKE_TARGETS[str(item["entity_type"])]
                    cursor.execute(f"DELETE FROM {table} WHERE id=%s AND status='draft'", (int(item["entity_id"]),))
                    if cursor.rowcount != 1:
                        raise DomainError("IMPORT_REVOKE_REFERENCED", "批次内记录已被后续业务引用或已提交核验，不能撤销", 409)
            except pymysql.IntegrityError as exc:
                raise DomainError("IMPORT_REVOKE_REFERENCED", "批次内记录已被后续业务引用，不能撤销", 409) from exc
            cursor.execute("DELETE FROM data_import_items WHERE import_batch_id=%s", (batch_id,))
            cursor.execute("UPDATE data_import_batches SET status='undone',imported_count=0 WHERE id=%s", (batch_id,))
            cursor.execute("SELECT * FROM data_import_batches WHERE id=%s", (batch_id,))
            after = self._decode(cursor.fetchone()) or {}
            self._audit(connection, int(user["id"]), "revoke_import", batch_id, before=before, after=after)
            return after
    @staticmethod
    def _export_scope(user: dict[str, Any], resource: str) -> tuple[str, list[Any]]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        if areas:
            column = EXPORT_AREA_COLUMNS.get(resource)
            if column:
                placeholders = ",".join(["%s"] * len(areas))
                return f" AND {column} IN ({placeholders})", areas
            own = EXPORT_PERSONAL_COLUMNS.get(resource)
            if own:
                return f" AND {own}=%s", [int(user["id"])]
            raise DomainError("DATA_SCOPE_FORBIDDEN", "该导出资源无法按当前数据范围安全过滤", 403)
        own = EXPORT_PERSONAL_COLUMNS.get(resource)
        if own:
            return f" AND {own}=%s", [int(user["id"])]
        return " AND 1=0", []
    @staticmethod
    def _matches_export_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        status = str(filters.get("status") or "")
        if status and str(row.get("status")) != status:
            return False
        for key in ("area_id", "pond_id", "warehouse_id", "supplier_id", "customer_id", "batch_id"):
            value = filters.get(key)
            if value not in (None, "") and str(row.get(key)) != str(value):
                return False
        created = str(row.get("created_at") or row.get("happened_at") or row.get("sold_at") or "")[:10]
        if filters.get("created_from") and created < str(filters["created_from"]):
            return False
        if filters.get("created_to") and created > str(filters["created_to"]):
            return False
        business = str(row.get("happened_at") or row.get("sold_at") or row.get("paid_at") or row.get("received_at") or row.get("occurred_on") or "")[:10]
        if filters.get("business_date_from") and business < str(filters["business_date_from"]):
            return False
        if filters.get("business_date_to") and business > str(filters["business_date_to"]):
            return False
        search = str(filters.get("search") or "").strip().lower()
        return not search or search in " ".join(
            str(value) for value in row.values() if value is not None
        ).lower()
    @contextmanager
    def export_stream(
        self,
        user: dict[str, Any],
        resource: str,
        filters: dict[str, Any],
        *,
        batch_size: int = 1000,
    ) -> Iterator[Iterator[dict[str, Any]]]:
        if resource not in EXPORT_QUERIES:
            raise DomainError("EXPORT_RESOURCE_INVALID", "不支持导出该业务类型", 400)
        criteria = dict(filters)
        organization_id = int(criteria.pop("_organization_id"))
        scope_sql, scope_params = self._export_scope(user, resource)
        sql = EXPORT_QUERIES[resource].format(scope=scope_sql)
        with get_connection(self.settings) as connection, connection.cursor(pymysql.cursors.SSDictCursor) as cursor:
            cursor.execute(sql, (organization_id, *scope_params))

            def generate() -> Iterator[dict[str, Any]]:
                while batch := cursor.fetchmany(batch_size):
                    for raw_row in batch:
                        row = dict(raw_row)
                        if self._matches_export_filters(row, criteria):
                            yield row

            yield generate()
    def export_rows(self, user: dict[str, Any], resource: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        with self.export_stream(user, resource, filters) as rows:
            return list(rows)
    def record_export(self, payload: dict[str, Any]) -> int:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO data_export_audits (organization_id,resource_code,format,filters_json,row_count,request_id,exported_by) VALUES (%s,%s,%s,%s,%s,%s,%s)", (payload["organization_id"], payload["resource"], payload["format"], json.dumps(payload["filters"], ensure_ascii=False), payload["row_count"], payload["request_id"], payload["exported_by"]))
            export_id = int(cursor.lastrowid)
            self._audit(connection, int(payload["exported_by"]), "export_data", export_id, after=payload)
            return export_id
    _target_scope_allows = staticmethod(target_scope_allows)

    def attachment_target_exists(self, organization_id: int, entity_type: str, entity_id: int) -> bool:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            return attachment_target(cursor, organization_id, entity_type, entity_id) is not None

    def attachment_target_accessible(self, user: dict[str, Any], organization_id: int, entity_type: str, entity_id: int) -> bool:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            target = attachment_target(cursor, organization_id, entity_type, entity_id)
            return bool(target and target_scope_allows(user, target))

    def find_attachment_hash(self, organization_id: int, entity_type: str, entity_id: int, sha256: str) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM attachments WHERE organization_id=%s AND entity_type=%s AND entity_id=%s AND sha256=%s", (organization_id, entity_type, entity_id, sha256))
            return self._decode(cursor.fetchone())

    def create_attachment(self, payload: dict[str, Any]) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (payload["organization_id"], payload["entity_type"], payload["entity_id"], payload["sha256"], payload["storage_name"], payload["original_name"], payload["media_type"], payload["size_bytes"], payload["uploaded_by"]))
            attachment_id = int(cursor.lastrowid)
            cursor.execute("SELECT * FROM attachments WHERE id=%s", (attachment_id,))
            row = self._decode(cursor.fetchone()) or {}
            self._audit(connection, int(payload["uploaded_by"]), "upload_attachment", attachment_id, after=row)
            return row

    def create_scoped_attachment(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return create_scoped_attachment(self.settings, self.audit, user, payload)

    def list_attachments(self, user: dict[str, Any], entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        organizations = self._organizations(user)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM attachments WHERE entity_type=%s AND entity_id=%s ORDER BY id", (entity_type, entity_id))
            rows = [self._decode(row) or {} for row in cursor.fetchall()]
            return [
                row for row in rows
                if (organizations is None or int(row["organization_id"]) in organizations)
                and (target := attachment_target(cursor, int(row["organization_id"]), entity_type, entity_id)) is not None
                and target_scope_allows(user, target)
            ]

    def get_attachment(self, user: dict[str, Any], attachment_id: int) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM attachments WHERE id=%s", (attachment_id,))
            row = self._decode(cursor.fetchone())
            allowed = self._organizations(user)
            target = attachment_target(cursor, int(row["organization_id"]), str(row["entity_type"]), int(row["entity_id"])) if row else None
            if row and target and (allowed is None or int(row["organization_id"]) in allowed) and target_scope_allows(user, target):
                self._audit(connection, int(user["id"]), "download_attachment", attachment_id, after={"entity_type": row["entity_type"], "entity_id": row["entity_id"]})
                return row
            return None

    def _audit(self, connection: Any, user_id: int, action: str, object_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=action, object_type="data_exchange", object_id=object_id, object_ref=f"data_exchange:{object_id}", result="success", ip_address=None, module_code="data_exchange", before=before, after=after)

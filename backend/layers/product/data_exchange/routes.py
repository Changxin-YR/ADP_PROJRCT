from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request, send_file

from backend.config.settings import Settings
from backend.layers.common.files.attachments import AttachmentError
from backend.layers.common.files.malware_scanner import CommandMalwareScanner
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.data_exchange.data_exchange_service import DataExchangeService


def create_data_exchange_blueprint(settings: Settings, auth_store: Any, exchange_store: Any) -> Blueprint:
    blueprint = Blueprint("data_exchange", __name__, url_prefix="/api/v1/data-exchange")
    auth = AuthService(auth_store, settings)
    scanner = (
        CommandMalwareScanner(
            settings.attachment_scanner_argv,
            timeout_seconds=settings.attachment_scanner_timeout_seconds,
            threat_exit_codes=settings.attachment_scanner_threat_exit_codes,
        )
        if settings.attachment_scanner_argv
        else None
    )
    service = DataExchangeService(exchange_store, Path(settings.attachment_root), scanner)

    def user() -> dict[str, Any]:
        return auth.current_user(request.cookies.get("adp_session"), request_id=getattr(g, "request_id", None))

    def error(exc: Exception) -> tuple[Response, int]:
        if type(exc) in (TypeError, ValueError):
            exc = DomainError("REQUEST_FIELD_INVALID", "请求字段格式无效", 400)
        status = 403 if isinstance(exc, CsrfError) else int(getattr(exc, "status", 400))
        code = getattr(exc, "code", "ATTACHMENT_INVALID" if isinstance(exc, AttachmentError) else "DATA_EXCHANGE_FAILED")
        return jsonify(fail(code, getattr(exc, "message", str(exc)), status)), status

    def protect(operation: Callable[[], Response | tuple[Response, int]]) -> Response | tuple[Response, int]:
        try:
            return operation()
        except (AuthServiceError, CsrfError, DomainError, AttachmentError, TypeError, ValueError) as exc:
            return error(exc)

    def csrf() -> None:
        require_csrf()

    @blueprint.get("/templates")
    def templates() -> Response | tuple[Response, int]:
        return protect(lambda: jsonify(ok({"items": service.templates(user())})))

    @blueprint.get("/templates/<code>/download")
    def download_template(code: str) -> Response | tuple[Response, int]:
        def operation() -> Response:
            content, version = service.template_file(user(), code)
            response = send_file(BytesIO(content), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"{code}-{version}.xlsx")
            response.headers["X-Template-Version"] = version
            return response
        return protect(operation)

    @blueprint.get("/imports")
    def imports() -> Response | tuple[Response, int]:
        return protect(lambda: jsonify(ok({"items": service.list_imports(user())})))

    @blueprint.post("/imports/preview")
    def preview() -> Response | tuple[Response, int]:
        def operation() -> tuple[Response, int]:
            csrf(); uploaded = request.files.get("file")
            if not uploaded:
                raise DomainError("IMPORT_FILE_REQUIRED", "请选择 Excel 文件", 400)
            row = service.preview(user(), organization_id=int(request.form.get("organization_id", 0)), template_code=request.form.get("template_code", ""), file_name=uploaded.filename or "import.xlsx", content=uploaded.read())
            return jsonify(ok({"batch": service._decorate(row)})), 201
        return protect(operation)

    @blueprint.post("/imports/<int:batch_id>/confirm")
    def confirm(batch_id: int) -> Response | tuple[Response, int]:
        def operation() -> Response:
            csrf(); return jsonify(ok({"batch": service.confirm(user(), batch_id)}, message="整批数据已写入草稿台账"))
        return protect(operation)

    @blueprint.post("/imports/<int:batch_id>/revoke")
    def revoke(batch_id: int) -> Response | tuple[Response, int]:
        def operation() -> Response:
            csrf(); return jsonify(ok({"batch": service.revoke(user(), batch_id)}, message="导入批次已撤销，草稿数据已删除"))
        return protect(operation)

    @blueprint.get("/imports/<int:batch_id>/errors")
    def errors(batch_id: int) -> Response | tuple[Response, int]:
        return protect(lambda: send_file(BytesIO(service.errors(user(), batch_id)), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"import-{batch_id}-errors.xlsx"))

    @blueprint.post("/exports")
    def export() -> Response | tuple[Response, int]:
        def operation() -> Response:
            csrf(); payload = json_object(); file_format = str(payload.get("format", ""))
            content, export_id = service.export(user(), organization_id=int(payload.get("organization_id", 0)), resource=str(payload.get("resource", "")), file_format=file_format, filters=payload.get("filters", {}), request_id=str(getattr(g, "request_id", "")))
            response = send_file(BytesIO(content), mimetype="application/pdf" if file_format == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"adp-export-{export_id}.{file_format}")
            response.headers["X-Export-ID"] = str(export_id)
            return response
        return protect(operation)

    @blueprint.post("/attachments")
    def upload_attachment() -> Response | tuple[Response, int]:
        def operation() -> tuple[Response, int]:
            csrf(); uploaded = request.files.get("file")
            if not uploaded:
                raise DomainError("ATTACHMENT_FILE_REQUIRED", "请选择附件", 400)
            row = service.upload_attachment(user(), organization_id=int(request.form.get("organization_id", 0)), entity_type=request.form.get("entity_type", ""), entity_id=int(request.form.get("entity_id", 0)), file_name=uploaded.filename or "attachment", media_type=uploaded.mimetype, content=uploaded.read())
            return jsonify(ok({"attachment": row})), 201
        return protect(operation)

    @blueprint.get("/attachments")
    def attachments() -> Response | tuple[Response, int]:
        return protect(lambda: jsonify(ok({"items": service.attachments(user(), request.args.get("entity_type", ""), int(request.args.get("entity_id", 0)))})))

    @blueprint.get("/attachments/<int:attachment_id>/download")
    def download_attachment(attachment_id: int) -> Response | tuple[Response, int]:
        def operation() -> Response:
            path, row = service.attachment_file(user(), attachment_id)
            return send_file(path, mimetype=row["media_type"], as_attachment=True, download_name=row["original_name"])
        return protect(operation)

    return blueprint

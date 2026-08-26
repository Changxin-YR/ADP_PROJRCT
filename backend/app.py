from __future__ import annotations

import re
from typing import Any, Mapping
from uuid import uuid4

import pymysql
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.config.settings import Settings
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.headers import register_security_headers
from backend.layers.common.db.repositories.mysql_store import MySqlAuthStore
from backend.layers.common.db.connection import begin_request_connection_scope, end_request_connection_scope
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.layers.features.purchase.purchase_store import MySqlPurchaseStore
from backend.layers.features.sales.sales_store import MySqlSalesStore
from backend.layers.features.data_exchange.data_exchange_store import MySqlDataExchangeStore
from backend.layers.product.auth.routes import create_auth_blueprint
from backend.layers.product.admin.routes import create_admin_blueprint
from backend.layers.product.cost.routes import create_cost_blueprint
from backend.layers.product.workbench.routes import create_workbench_blueprint
from backend.layers.product.master_data.routes import create_master_data_blueprint
from backend.layers.product.production.routes import create_production_blueprint
from backend.layers.product.warehouse.routes import create_warehouse_blueprint
from backend.layers.product.purchase.routes import create_purchase_blueprint
from backend.layers.product.sales.routes import create_sales_blueprint
from backend.layers.product.data_exchange.routes import create_data_exchange_blueprint


def _mysql_error_field(message: str) -> str | None:
    for pattern in (r"column '([^']+)'", r"value for column '([^']+)'"):
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return None


def create_app(
    settings: Settings | None = None,
    *,
    env: Mapping[str, str] | None = None,
    store: Any | None = None,
    cost_store: Any | None = None,
    master_store: Any | None = None,
    production_store: Any | None = None,
    warehouse_store: Any | None = None,
    purchase_store: Any | None = None,
    sales_store: Any | None = None,
    data_exchange_store: Any | None = None,
) -> Flask:
    resolved = settings or Settings.from_env(env)
    auth_store = store or MySqlAuthStore(resolved)
    resolved_cost_store = cost_store or MySqlCostStore(resolved)
    resolved_master_store = master_store or MySqlMasterDataStore(resolved)
    resolved_production_store = production_store or MySqlProductionStore(resolved)
    resolved_warehouse_store = warehouse_store or MySqlWarehouseStore(resolved)
    resolved_purchase_store = purchase_store or MySqlPurchaseStore(resolved)
    resolved_sales_store = sales_store or MySqlSalesStore(resolved)
    resolved_data_exchange_store = data_exchange_store or MySqlDataExchangeStore(resolved)
    app = Flask(__name__)
    if resolved.trusted_proxy_hops:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=resolved.trusted_proxy_hops,
            x_proto=resolved.trusted_proxy_hops,
        )
    app.config.update(
        APP_ENV=resolved.app_env,
        SECRET_KEY=resolved.flask_secret_key,
        SETTINGS=resolved,
        JSON_SORT_KEYS=False,
        SESSION_COOKIE_SECURE=resolved.session_cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=21 * 1024 * 1024,
    )
    register_security_headers(app)

    @app.before_request
    def bind_request_id() -> None:
        begin_request_connection_scope()
        candidate = request.headers.get("X-Request-ID", "").strip()
        g.request_id = candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,32}", candidate) else uuid4().hex

    @app.teardown_request
    def close_request_connection(error: BaseException | None) -> None:
        end_request_connection_scope(rollback=error is not None)

    @app.after_request
    def expose_request_id(response: Any) -> Any:
        response.headers["X-Request-ID"] = str(getattr(g, "request_id", uuid4().hex))
        return response

    app.register_blueprint(create_auth_blueprint(resolved, auth_store))
    app.register_blueprint(create_admin_blueprint(resolved, auth_store))
    app.register_blueprint(create_cost_blueprint(resolved, auth_store, resolved_cost_store))
    app.register_blueprint(create_workbench_blueprint(resolved, auth_store))
    app.register_blueprint(create_master_data_blueprint(resolved, auth_store, resolved_master_store))
    app.register_blueprint(create_production_blueprint(resolved, auth_store, resolved_production_store))
    app.register_blueprint(create_warehouse_blueprint(resolved, auth_store, resolved_warehouse_store))
    app.register_blueprint(create_purchase_blueprint(resolved, auth_store, resolved_purchase_store))
    app.register_blueprint(create_sales_blueprint(resolved, auth_store, resolved_sales_store))
    app.register_blueprint(create_data_exchange_blueprint(resolved, auth_store, resolved_data_exchange_store))

    @app.get("/api/v1/health")
    def health() -> Any:
        return jsonify(ok({"status": "ok", "environment": resolved.app_env}, message="服务正常"))

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> Any:
        status = error.code or 500
        codes = {
            400: ("BAD_REQUEST", "请求格式无效"),
            401: ("UNAUTHENTICATED", "请先登录"),
            403: ("FORBIDDEN", "当前账号无权执行该操作"),
            404: ("NOT_FOUND", "请求的资源不存在"),
            405: ("METHOD_NOT_ALLOWED", "请求方法不受支持"),
            409: ("CONFLICT", "请求与当前数据状态冲突"),
            413: ("PAYLOAD_TOO_LARGE", "上传内容过大，单次请求不能超过 21 MB"),
            422: ("VALIDATION_ERROR", "请求内容未通过校验"),
            429: ("RATE_LIMITED", "请求过于频繁，请稍后重试"),
        }
        code, message = codes.get(status, ("HTTP_ERROR", "请求暂时无法处理"))
        return jsonify(fail(code, message, status)), status

    @app.errorhandler(pymysql.err.IntegrityError)
    def handle_mysql_integrity_error(error: pymysql.err.IntegrityError) -> Any:
        """唯一键/外键冲突等约束错误 → 400/409 中文业务提示，绝不 500。"""
        request_id = str(getattr(g, "request_id", uuid4().hex))
        errno = int(error.args[0]) if error.args else 0
        if errno == 1062:
            app.logger.warning("MySQL duplicate key %s [request_id=%s]", errno, request_id)
            return jsonify(fail("DUPLICATE_CODE", "编码已存在", 409, request_id=request_id)), 409
        if errno == 1452:
            app.logger.warning("MySQL missing relation %s [request_id=%s]", errno, request_id)
            return jsonify(fail("FIELD_INVALID", "关联对象不存在或已删除", 400, request_id=request_id)), 400
        app.logger.warning("MySQL integrity error %s [request_id=%s]", errno, request_id)
        return jsonify(fail("DATA_CONFLICT", "数据冲突，请检查后重试", 409, request_id=request_id)), 409

    @app.errorhandler(pymysql.err.DataError)
    def handle_mysql_data_error(error: pymysql.err.DataError) -> Any:
        """字段超长 / 非法值 / 枚举越界 / 日期无效 → 400 FIELD_INVALID 带字段名。"""
        request_id = str(getattr(g, "request_id", uuid4().hex))
        errno = int(error.args[0]) if error.args else 0
        app.logger.warning("MySQL data error %s [request_id=%s]", errno, request_id)
        field = _mysql_error_field(str(error))
        message = f"字段 {field} 的值无效或超出允许范围" if field else "字段值无效或超出允许范围"
        return jsonify(fail("FIELD_INVALID", message, 400, request_id=request_id)), 400

    @app.errorhandler(pymysql.err.OperationalError)
    def handle_mysql_operational_error(error: pymysql.err.OperationalError) -> Any:
        request_id = str(getattr(g, "request_id", uuid4().hex))
        errno = int(error.args[0]) if error.args else 0
        app.logger.warning("MySQL operational error %s [request_id=%s]", errno, request_id)
        if errno in (1205, 1213):
            return jsonify(fail("DB_CONFLICT", "数据正在被其他操作处理，请稍后重试", 409, request_id=request_id)), 409
        return jsonify(fail("DB_UNAVAILABLE", "数据库服务暂时不可用，请稍后重试", 503, request_id=request_id)), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> Any:
        request_id = str(getattr(g, "request_id", uuid4().hex))
        app.logger.exception("Unhandled exception [request_id=%s]", request_id, exc_info=error)
        return jsonify(fail("INTERNAL_ERROR", "服务器暂时无法处理请求", 500, request_id=request_id)), 500

    return app


app = create_app()

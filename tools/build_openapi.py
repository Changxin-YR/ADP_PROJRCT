from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import app  # noqa: E402


HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/csrf",
    "/api/v1/auth/login",
    "/api/v1/auth/register/options",
    "/api/v1/auth/register",
}
ACTION_NAMES = {
    "approve": "审批",
    "cancel": "取消",
    "confirm": "确认入账",
    "correct": "创建更正单",
    "corrections": "创建更正单",
    "delete": "删除未提交草稿",
    "depreciate": "计提折旧",
    "dispatch": "发出调拨",
    "download": "下载文件",
    "handle": "处理预警",
    "preview": "预检导入",
    "receive": "接收调拨",
    "reject": "驳回",
    "reset_password": "重置密码",
    "reverse": "冲销",
    "submit": "提交核验",
    "update": "更新",
    "verify": "核验",
}
TAG_TITLES = {
    "admin": "账号与权限",
    "auth": "认证与注册",
    "cost": "成本与结算",
    "data-exchange": "数据交换与附件",
    "health": "平台健康",
    "master-data": "主数据",
    "production": "生产养殖",
    "purchase": "采购与应付",
    "sales": "销售与应收",
    "warehouse": "仓储库存",
    "workbench": "工作台",
}


def openapi_path(rule: str) -> str:
    pattern = r"<(?:int|path):([^>]+)>|<([^>]+)>"
    return re.sub(pattern, lambda match: "{" + (match.group(1) or match.group(2)) + "}", rule)


def route_tag(path: str) -> str:
    segment = path.split("/")[3] if len(path.split("/")) > 3 else "health"
    if segment in {"work-items", "notifications"}:
        return "workbench"
    return segment


def operation_summary(endpoint: str, method: str, path: str) -> str:
    action = endpoint.split(".")[-1]
    for key, label in ACTION_NAMES.items():
        if key in action:
            return label
    if method == "GET":
        return "查询详情" if "{" in path else "查询列表"
    if method == "POST":
        return "新建记录"
    return {"PATCH": "更新记录", "PUT": "保存配置", "DELETE": "删除未提交草稿"}[method]


def path_parameters(rule: Any) -> list[dict[str, Any]]:
    parameters = []
    for name in sorted(rule.arguments):
        marker = next((part for part in rule.rule.split("/") if f"{name}>" in part), "")
        schema = {"type": "integer", "minimum": 1} if marker.startswith("<int:") else {"type": "string"}
        parameters.append({"name": name, "in": "path", "required": True, "schema": schema})
    return parameters


def query_parameters(method: str, path: str) -> list[dict[str, Any]]:
    if method != "GET" or "{" in path or path.endswith(("/health", "/csrf", "/me", "/workbench", "/summary")):
        return []
    return [
        {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
        {"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
        {"name": "keyword", "in": "query", "schema": {"type": "string", "maxLength": 100}},
        {"name": "status", "in": "query", "schema": {"type": "string"}},
    ]


def request_body(method: str, path: str) -> dict[str, Any] | None:
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if path.endswith("/attachments") or path.endswith("/imports/preview"):
        return {"required": True, "content": {"multipart/form-data": {"schema": {"$ref": "#/components/schemas/FileUpload"}}}}
    schema = "MutationRequest"
    if path.endswith("/auth/login"):
        schema = "LoginRequest"
    elif path.endswith("/auth/register"):
        schema = "RegistrationRequest"
    return {"required": method != "DELETE", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}}}


def operation(rule: Any, method: str, path: str) -> dict[str, Any]:
    endpoint = rule.endpoint
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    result: dict[str, Any] = {
        "tags": [route_tag(path)],
        "summary": operation_summary(endpoint, method, path),
        "description": "核验完成的数据只读；DELETE 仅适用于从未提交且无业务引用的草稿。",
        "operationId": f"{endpoint.replace('.', '_')}_{method.lower()}_{normalized}",
        "parameters": path_parameters(rule) + query_parameters(method, path),
        "responses": {
            "200": {"description": "成功", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SuccessEnvelope"}}}},
            "default": {"$ref": "#/components/responses/ErrorResponse"},
        },
    }
    if method == "POST" and (path.endswith("/register") or "{" not in path and not path.endswith(("/submit", "/verify"))):
        result["responses"]["201"] = result["responses"].pop("200")
    body = request_body(method, path)
    if body:
        result["requestBody"] = body
    if path in PUBLIC_PATHS:
        result["security"] = [] if method == "GET" else [{"CsrfSession": [], "CsrfToken": []}]
    else:
        result["security"] = [{"CookieAuth": [], "CsrfToken": []}] if method != "GET" else [{"CookieAuth": []}]
    return result


def components() -> dict[str, Any]:
    envelope = {
        "type": "object",
        "required": ["code", "message", "data", "request_id"],
        "properties": {
            "code": {"type": "string", "example": "OK"},
            "message": {"type": "string", "example": "操作成功"},
            "data": {},
            "request_id": {"type": "string", "example": "request-example-001"},
        },
    }
    return {
        "securitySchemes": {
            "CookieAuth": {"type": "apiKey", "in": "cookie", "name": "adp_session"},
            "CsrfSession": {"type": "apiKey", "in": "cookie", "name": "session"},
            "CsrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
        },
        "schemas": {
            "SuccessEnvelope": envelope,
            "ErrorEnvelope": {**envelope, "properties": {**envelope["properties"], "code": {"type": "string", "example": "VERSION_CONFLICT"}}},
            "MutationRequest": {"type": "object", "properties": {"expected_version": {"type": "integer", "minimum": 1}, "evidence_attachment_ids": {"type": "array", "items": {"type": "integer"}}}, "additionalProperties": True},
            "LoginRequest": {"type": "object", "required": ["identifier", "password"], "properties": {"identifier": {"type": "string", "example": "api-user"}, "password": {"type": "string", "format": "password", "example": "<PASSWORD>"}}},
            "RegistrationRequest": {"type": "object", "required": ["username", "password", "confirm_password"], "properties": {"username": {"type": "string", "example": "api-user"}, "password": {"type": "string", "format": "password", "example": "<PASSWORD>"}, "confirm_password": {"type": "string", "format": "password", "example": "<PASSWORD>"}}},
            "FileUpload": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}, "entity_type": {"type": "string"}, "entity_id": {"type": "integer"}}},
        },
        "responses": {"ErrorResponse": {"description": "统一错误；以 code 和 request_id 定位问题", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}}},
    }


def build() -> dict[str, Any]:
    paths: dict[str, Any] = {}
    fragments: dict[str, dict[str, Any]] = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: (item.rule, item.endpoint)):
        if not rule.rule.startswith("/api/v1"):
            continue
        path = openapi_path(rule.rule)
        for method in sorted(rule.methods & HTTP_METHODS):
            item = operation(rule, method, path)
            paths.setdefault(path, {})[method.lower()] = item
            fragments.setdefault(route_tag(path), {}).setdefault(path, {})[method.lower()] = item
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "ADP 鱼塘养殖企业 API", "version": "1.0.0", "description": "网站二正式业务接口。提交后可修改并递增版本，核验后只读。"},
        "servers": [{"url": "https://1.14.148.15", "description": "生产环境"}],
        "tags": [{"name": key, "description": value} for key, value in TAG_TITLES.items()],
        "paths": paths,
        "components": components(),
    }
    source = ROOT / "docs" / "api" / "openapi"
    source.mkdir(parents=True, exist_ok=True)
    for tag, fragment in fragments.items():
        (source / f"{tag}.yaml").write_text(json.dumps({"paths": fragment}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "api-docs"
    output.mkdir(exist_ok=True)
    (output / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return spec


if __name__ == "__main__":
    built = build()
    print(f"Built {sum(len(item) for item in built['paths'].values())} API operations")

from __future__ import annotations

from typing import Any
from uuid import uuid4

from flask import g, has_request_context


def _request_id() -> str:
    if has_request_context():
        request_id = getattr(g, "request_id", None)
        if request_id:
            return str(request_id)
    return uuid4().hex


def ok(data: Any = None, message: str = "操作成功", code: str = "OK", status: int = 200) -> dict[str, Any]:
    """返回统一成功结构；status 供路由层作为 HTTP 状态码使用。"""
    del status
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": _request_id(),
    }


def fail(code: str, message: str, status: int, data: Any = None, request_id: str | None = None) -> dict[str, Any]:
    """返回统一错误结构；不把异常堆栈放进响应。"""
    del status
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or _request_id(),
    }

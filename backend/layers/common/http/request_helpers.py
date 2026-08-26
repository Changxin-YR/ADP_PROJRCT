from __future__ import annotations

from typing import Any, Mapping

from flask import request, session

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.csrf import validate_csrf_token


def require_csrf() -> None:
    validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))


def json_object() -> dict[str, Any]:
    raw = request.get_data(cache=True)
    if not raw.strip():
        return {}
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError("REQUEST_BODY_INVALID", "请求内容必须是 JSON 对象", 400)
    return payload


def pagination(
    values: Mapping[str, Any] | None = None,
    *,
    default_page_size: int = 20,
    code: str = "PAGINATION_INVALID",
) -> tuple[int, int]:
    source = values if values is not None else request.args
    try:
        page = int(source.get("page", 1))
        page_size = int(source.get("page_size", default_page_size))
    except (TypeError, ValueError) as exc:
        raise DomainError(code, "分页参数无效", 400) from exc
    if page < 1 or page_size < 1:
        raise DomainError(code, "分页参数无效", 400)
    return page, min(100, page_size)

"""In-process dispatch of a fixed agent tool to its checked-in business route.

Kept separate from the blueprint so the HTTP layer stays inside the 300-line source
budget; the behaviour is identical to the previous inline implementation.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from flask import current_app, request

from backend.config.settings import Settings
from backend.layers.common.db.connection import _request_state
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_tool_registry import AgentTool

_PATH_PARAMETER = re.compile(r"\{([^}]+)\}")

def _internal_base_url(settings: Settings | None) -> str | None:
    """Reuse the caller's origin: the domain cutover answers 421 for any other Host."""
    try:
        host_url = request.host_url.rstrip("/")
    except RuntimeError:
        host_url = ""
    if host_url:
        return host_url
    server_name = getattr(settings, "server_name", "") if settings is not None else ""
    return f"https://{server_name}" if server_name else None


def dispatch_fixed_tool(tool: AgentTool, arguments: dict[str, Any], context: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Dispatch only to the path fixed in the checked-in agent registry."""
    payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else dict(arguments)
    path = tool.path_template
    path_params = set(_PATH_PARAMETER.findall(path))
    for name in path_params:
        value = arguments.get(name, payload.get(name))
        if value is None and name == "resource":
            value = arguments.get("resource_type", payload.get("resource_type"))
        if value is None:
            raise AgentGatewayError("VALIDATION_ERROR", f"缺少路径参数 {name}", 400)
        if name == "resource" and value == "feeding":
            value = "feed-logs"
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    body = dict(payload)
    for name in path_params:
        body.pop(name, None)
        if name == "resource":
            body.pop("resource_type", None)
    if tool.method == "GET":
        # Agent reads are deliberately bounded. The model can paginate, but a
        # single turn must not receive an unbounded business-object payload.
        try:
            body["page_size"] = min(50, max(1, int(body.get("page_size", 20))))
        except (TypeError, ValueError):
            raise AgentGatewayError("VALIDATION_ERROR", "page_size 必须是正整数", 400)
    query = body if tool.method == "GET" else {}
    if tool.method == "GET":
        body = {}
    token = context.get("session_token")
    if not token:
        raise AgentGatewayError("UNAUTHENTICATED", "当前会话不能用于业务调用", 401)
    headers = {"Authorization": f"Bearer {token}", "X-Request-ID": str(context.get("request_id") or "")}
    if context.get("idempotency_key"):
        headers["Idempotency-Key"] = str(context["idempotency_key"])
    cookie = request.headers.get("Cookie")
    if cookie:
        headers["Cookie"] = cookie
    outer_scope = _request_state.get()
    base_url = _internal_base_url(settings)
    request_kwargs: dict[str, Any] = {"base_url": base_url} if base_url else {}
    try:
        response = current_app.test_client().open(path, method=tool.method, query_string=query, json=None if tool.method == "GET" else body, headers=headers, **request_kwargs)
    finally:
        _request_state.set(outer_scope)
    result = response.get_json(silent=True)
    if response.status_code >= 400:
        if isinstance(result, dict):
            raise AgentGatewayError(str(result.get("code") or "BUSINESS_ERROR"), str(result.get("message") or "业务操作未完成"), response.status_code, result.get("data"))
        raise AgentGatewayError("BUSINESS_ERROR", "业务操作未完成", response.status_code)
    if isinstance(result, dict):
        return result.get("data") if "data" in result else result
    return {"status": response.status_code}


# Backwards-compatible alias used by the tests and older call sites.
_dispatch_fixed_tool = dispatch_fixed_tool

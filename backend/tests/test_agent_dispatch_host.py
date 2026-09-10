from __future__ import annotations

from typing import Any

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.agent.agent_tool_registry import AgentTool
from backend.layers.product.agent.routes import _dispatch_fixed_tool


def _settings() -> Settings:
    return Settings.from_env(
        {
            "APP_ENV": "test",
            "ADP_SERVER_NAME": "adp.test",
            "FLASK_SECRET_KEY": "test-flask-secret",
            "CSRF_SECRET_KEY": "test-csrf-secret",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_DATABASE": "adp_test",
            "MYSQL_USER": "adp_test",
            "MYSQL_PASSWORD": "test-password",
            "SESSION_COOKIE_SECURE": "false",
        }
    )


def _app(settings: Settings) -> Any:
    dependency = object()
    return create_app(
        settings,
        store=dependency,
        cost_store=dependency,
        master_store=dependency,
        production_store=dependency,
        warehouse_store=dependency,
        purchase_store=dependency,
        sales_store=dependency,
        data_exchange_store=dependency,
        agent_gateway=dependency,
        agent_sidecar=dependency,
    )


def _health_tool() -> AgentTool:
    return AgentTool(
        name="api.health_get_api_v1_health",
        description="health",
        method="GET",
        path_template="/api/v1/health",
        parameters={},
        required_permission=None,
        risk="read",
        requires_data_scope=False,
    )


def test_in_process_agent_dispatch_keeps_the_callers_host() -> None:
    """Regression: the domain cutover answered 421 for every agent tool call.

    ``_dispatch_fixed_tool`` runs business reads through the in-process test
    client. Without forwarding the caller's origin that request looks like a
    misdirected Host and every tool call fails with HOST_NOT_ALLOWED, which made
    the model invent "认证服务未连接" instead of answering.
    """
    settings = _settings()
    app = _app(settings)

    with app.test_request_context("/api/v1/agent/query", headers={"Host": "adp.test"}):
        result = _dispatch_fixed_tool(_health_tool(), {}, {"session_token": "probe"}, settings)

    assert result == {"status": "ok", "environment": "test"}


def test_host_binding_still_rejects_foreign_domains() -> None:
    """The fix must not weaken the domain binding the cutover introduced."""
    app = _app(_settings())
    response = app.test_client().get("/api/v1/health", headers={"Host": "1.14.148.15"})

    assert response.status_code == 421
    assert response.get_json()["code"] == "HOST_NOT_ALLOWED"

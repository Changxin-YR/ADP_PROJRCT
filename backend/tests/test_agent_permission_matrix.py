from __future__ import annotations

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.agent.agent_tool_registry import build_agent_catalog, build_registry
from tools.build_agent_permission_matrix import build_matrix


def test_agent_permission_matrix_covers_every_business_route() -> None:
    app = create_app(Settings.from_env({"APP_ENV": "test"}))
    rows = build_matrix(app)

    # 断言"矩阵覆盖全部已注册工具"而不是硬编码条数：新增路由时本测试应继续有效，
    # 而不是因为常量过期变红（真正的路由覆盖检查在 test_agent_catalog_coverage.py）。
    registered = build_registry().tools
    assert len(rows) == len(registered), (len(rows), len(registered))
    assert len(rows) == build_agent_catalog(app)["registered_count"]
    assert all(row["tool"] for row in rows)
    assert all(row["agent_permission"] for row in rows)
    assert all(row["status"] == "PASS" for row in rows)

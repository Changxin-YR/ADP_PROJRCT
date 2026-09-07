from __future__ import annotations

from backend.app import create_app
from backend.config.settings import Settings
from tools.build_agent_permission_matrix import build_matrix


def test_agent_permission_matrix_covers_every_business_route() -> None:
    app = create_app(Settings.from_env({"APP_ENV": "test"}))
    rows = build_matrix(app)

    assert len(rows) == 171
    assert all(row["tool"] for row in rows)
    assert all(row["agent_permission"] for row in rows)
    assert all(row["status"] == "PASS" for row in rows)

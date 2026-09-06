from pathlib import Path

import pytest

from backend.config.settings import ConfigError, Settings


def test_agent_settings_defaults_and_sidecar_paths() -> None:
    settings = Settings.from_env({"APP_ENV": "test"})
    assert settings.agent_request_timeout_seconds == 30
    assert settings.agent_confirmation_ttl_seconds == 120
    assert settings.agent_sidecar_home
    assert settings.agent_sidecar_cwd
    assert settings.agent_sidecar_command


@pytest.mark.parametrize(
    ("name", "value"),
    [("AGENT_REQUEST_TIMEOUT_SECONDS", "61"), ("AGENT_CONFIRMATION_TTL_SECONDS", "601")],
)
def test_agent_settings_enforce_upper_bounds(name: str, value: str) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env({"APP_ENV": "test", name: value})


def test_production_requires_agent_sidecar_home() -> None:
    with pytest.raises(ConfigError, match="AGENT_SIDECAR_HOME"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "FLASK_SECRET_KEY": "flask",
                "CSRF_SECRET_KEY": "csrf",
                "MYSQL_PASSWORD": "mysql",
                "SESSION_COOKIE_SECURE": "true",
            }
        )


def test_agent_confirmation_migration_declares_atomic_claim_contract() -> None:
    sql = (Path(__file__).parents[2] / "database/migrations/031_agent_confirmations.sql").read_text().lower()
    for field in ("token_hash char(64)", "user_id", "session_hash char(64)", "conversation_id", "request_id", "tool_name", "payload_json json", "expires_at", "used_at"):
        assert field in sql
    assert "status enum('pending','confirmed','cancelled','expired')" in sql
    assert "unique" in sql
    assert "default 'pending'" in sql

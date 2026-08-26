from __future__ import annotations

import json
import os
from typing import Any, Callable

import pymysql
from pymysql.cursors import DictCursor

from backend.config.settings import Settings


PREFIX = "adp_manual_test_"
CONFIRMATION = "CREATE_TEST_DATA"


def validate_target(app_env: str, database: str, confirmation: str) -> None:
    if app_env != "test":
        raise RuntimeError(f"APP_ENV must be exactly test for {PREFIX} databases")
    if not database.startswith(PREFIX):
        raise RuntimeError(f"MYSQL_DATABASE must start with {PREFIX}")
    if confirmation != CONFIRMATION:
        raise RuntimeError(f"ADP_MANUAL_TEST_CONFIRM must be {CONFIRMATION}")


def _connect(settings: Settings) -> Any:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _complete_seed(cursor: Any, password: str) -> dict[str, object]:
    from backend.scripts.manual_test_seed_accounts import seed_accounts
    from backend.scripts.manual_test_seed_business import seed_business
    return {
        "accounts": seed_accounts(cursor, password),
        "business": seed_business(cursor, password),
    }


def main(
    connection_factory: Callable[[Settings], Any] = _connect,
    seed_action: Callable[[Any, str], dict[str, object]] | None = None,
) -> int:
    settings = Settings.from_env()
    validate_target(
        os.environ.get("APP_ENV", ""),
        settings.mysql_database,
        os.environ.get("ADP_MANUAL_TEST_CONFIRM", ""),
    )
    password = os.environ.get("ADP_MANUAL_TEST_PASSWORD", "")
    if not password.strip():
        raise RuntimeError("Missing required environment variable: ADP_MANUAL_TEST_PASSWORD")
    if seed_action is None:
        seed_action = _complete_seed

    connection = connection_factory(settings)
    try:
        connection.begin()
        with connection.cursor() as cursor:
            seed_manifest = seed_action(cursor, password)
        payload = json.dumps({
            "status": "validated",
            "app_env": settings.app_env,
            "database": settings.mysql_database,
            "seed": seed_manifest,
        })
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

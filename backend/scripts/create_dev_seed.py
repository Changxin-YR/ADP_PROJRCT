from __future__ import annotations

import os
import sys
from typing import Any

import pymysql
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _require_dev_only_environment() -> None:
    app_env = os.environ.get("APP_ENV", "").strip()
    if app_env not in {"development", "test"}:
        raise RuntimeError("Refusing to run development seed script unless APP_ENV is exactly development or test.")

    confirm = _require_env("ADP_DEV_SEED_CONFIRM")
    if confirm != "LOCAL_ONLY":
        raise RuntimeError("Refusing to run development seed script unless ADP_DEV_SEED_CONFIRM is exactly LOCAL_ONLY.")

    host = _require_env("MYSQL_HOST")
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Refusing to run development seed script unless MYSQL_HOST is localhost, 127.0.0.1, or ::1.")

    database = _require_env("MYSQL_DATABASE")
    if not (
        database in {"adp_auth", "adp_dev", "adp_test"}
        or database.startswith("adp_dev_")
        or database.startswith("adp_test_")
    ):
        raise RuntimeError(
            "Refusing to run development seed script unless MYSQL_DATABASE is adp_auth, adp_dev, adp_test, or starts with adp_dev_/adp_test_."
        )


def _connect() -> pymysql.connections.Connection[Any]:
    host = _require_env("MYSQL_HOST")
    port = int(_require_env("MYSQL_PORT"))
    database = _require_env("MYSQL_DATABASE")
    user = _require_env("MYSQL_USER")
    password = _require_env("MYSQL_PASSWORD")
    return pymysql.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def _fetch_one(cursor: pymysql.cursors.Cursor, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def main() -> int:
    _require_dev_only_environment()

    admin_password = _require_env("ADP_DEV_ADMIN_PASSWORD")
    admin_phone = _require_env("ADP_DEV_ADMIN_PHONE")
    admin_name = _require_env("ADP_DEV_ADMIN_NAME")
    admin_login_name = _optional_env("ADP_DEV_ADMIN_LOGIN_NAME") or admin_phone

    password_hash = generate_password_hash(admin_password, method="scrypt")

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            user_row = _fetch_one(
                cursor,
                """
                SELECT id
                FROM users
                WHERE phone = %s OR login_name = %s
                ORDER BY id ASC
                LIMIT 1
                """,
                (admin_phone, admin_login_name),
            )

            if user_row is None:
                cursor.execute(
                    """
                    INSERT INTO users (login_name, phone, name, password_hash, status)
                    VALUES (%s, %s, %s, %s, 'active')
                    """,
                    (admin_login_name, admin_phone, admin_name, password_hash),
                )
                user_id = cursor.lastrowid
            else:
                user_id = int(user_row["id"])
                cursor.execute(
                    """
                    UPDATE users
                    SET login_name = %s,
                        phone = %s,
                        name = %s,
                        password_hash = %s,
                        status = 'active',
                        failed_login_count = 0,
                        locked_until = NULL,
                        last_login_at = NULL
                    WHERE id = %s
                    """,
                    (admin_login_name, admin_phone, admin_name, password_hash, user_id),
                )

            role_row = _fetch_one(
                cursor,
                """
                SELECT id
                FROM roles
                WHERE code = %s
                LIMIT 1
                """,
                ("super_admin",),
            )
            if role_row is None:
                raise RuntimeError("Required role not found: super_admin")
            role_id = int(role_row["id"])

            cursor.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)
                """,
                (user_id, role_id),
            )

            scope_row = _fetch_one(
                cursor,
                """
                SELECT id
                FROM data_scopes
                WHERE code = %s
                LIMIT 1
                """,
                ("north-farm-all",),
            )
            if scope_row is not None:
                scope_id = int(scope_row["id"])
                cursor.execute(
                    """
                    INSERT INTO user_data_scopes (user_id, data_scope_id)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE data_scope_id = VALUES(data_scope_id)
                    """,
                    (user_id, scope_id),
                )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print("Development admin seed completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

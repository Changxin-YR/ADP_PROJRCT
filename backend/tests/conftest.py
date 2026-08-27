from __future__ import annotations

import sys
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend.config.settings import Settings
from backend.tests.mysql_test_database import grant_database_access


@pytest.fixture
def app():
    env = {
        "APP_ENV": "test",
        "FLASK_SECRET_KEY": "test-flask-secret",
        "CSRF_SECRET_KEY": "test-csrf-secret",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "adp_test",
        "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test-password",
        "SESSION_COOKIE_SECURE": "false",
    }
    return create_app(Settings.from_env(env))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def real_registration_db_adapter():
    if os.environ.get("ADP_TEST_MYSQL_ALLOW_DISPOSABLE") != "1":
        pytest.skip("set ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1 for the real registration database adapter")
    mysql_client = os.environ.get("ADP_TEST_MYSQL_CLIENT")
    if not mysql_client:
        pytest.skip("set ADP_TEST_MYSQL_CLIENT for the real registration database adapter")
    database = f"adp_registration_test_{uuid4().hex[:12]}"
    environment = os.environ.copy()
    if environment.get("ADP_TEST_MYSQL_PASSWORD"):
        environment["MYSQL_PWD"] = environment["ADP_TEST_MYSQL_PASSWORD"]
    command = [mysql_client, "--protocol=tcp", f"--host={environment.get('ADP_TEST_MYSQL_HOST', '127.0.0.1')}",
               f"--port={environment.get('ADP_TEST_MYSQL_PORT', '3306')}", f"--user={environment.get('ADP_TEST_MYSQL_USER', 'root')}",
               "--default-character-set=utf8mb4", "--batch"]
    subprocess.run([*command, f"--execute=CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"], env=environment, check=True)
    try:
        grant_database_access(database)
        subprocess.run([*command, f"--database={database}"], input=(PROJECT_ROOT / "database/migrations/001_initial_auth.sql").read_bytes(), env=environment, check=True)
        from backend.tests.mysql_registration_adapter import MySqlRegistrationTestAdapter
        yield MySqlRegistrationTestAdapter(host=environment.get("ADP_TEST_MYSQL_HOST", "127.0.0.1"),
                                           port=int(environment.get("ADP_TEST_MYSQL_PORT", "3306")), database=database,
                                           user=environment.get("ADP_TEST_MYSQL_USER", "root"), password=environment.get("ADP_TEST_MYSQL_PASSWORD", ""))
    finally:
        subprocess.run([*command, f"--execute=DROP DATABASE IF EXISTS `{database}`"], env=environment, check=True)

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_nginx_defaults_to_production_and_routes_only_test_cookie() -> None:
    text = _read("deploy/nginx-adp-manual-test.conf")

    assert "map $cookie_adp_environment $adp_api_upstream" in text
    assert "default http://127.0.0.1:5002;" in text
    assert "test http://127.0.0.1:5003;" in text
    assert "proxy_pass $adp_api_upstream;" in text
    assert "map $cookie_adp_environment $adp_frontend_root" in text
    assert "default __ADP_RELEASE_PATH__/frontend/dist;" in text
    assert "test __ADP_TEST_RELEASE_PATH__/frontend/dist;" in text
    assert "root $adp_frontend_root;" in text
    assert "location = /test" in text
    assert "location = /production" in text
    assert "adp_environment=test; Path=/;" in text
    assert "adp_environment=; Path=/; Max-Age=0;" in text
    for flag in ("Secure", "HttpOnly", "SameSite=Lax"):
        assert flag in text


def test_manual_test_service_is_local_and_separately_configured() -> None:
    text = _read("deploy/adp-manual-test.service")

    assert "User=adp" in text
    assert "Group=adp" in text
    assert "EnvironmentFile=/etc/adp/manual-test.env" in text
    assert "127.0.0.1:5003" in text
    assert "ReadWritePaths=/var/lib/adp/manual-test-20260817" in text
    assert "NoNewPrivileges=true" in text


def test_install_runs_test_code_without_overwriting_the_production_release() -> None:
    script = _read("deploy/install-manual-test.sh")
    service = _read("deploy/adp-manual-test.service")

    assert 'APP_ROOT="$(pwd -P)"' in script
    assert 'PRODUCTION_ROOT=/opt/adp/slots/green' in script
    assert 'RUNTIME_ROOT="$(readlink -f "$PRODUCTION_ROOT")"' in script
    assert '"$RUNTIME_ROOT/.venv/bin/python" -m backend.scripts.manual_test_seed' in script
    assert 's|__ADP_TEST_RELEASE_PATH__|$APP_ROOT|g' in script
    assert 's|__ADP_RUNTIME_PATH__|$RUNTIME_ROOT|g' in script
    assert 's|__ADP_RELEASE_PATH__|$RUNTIME_ROOT|g' in script
    assert "WorkingDirectory=__ADP_TEST_RELEASE_PATH__" in service
    assert "ExecStart=__ADP_RUNTIME_PATH__/.venv/bin/gunicorn" in service
    assert script.count('-m backend.scripts.reconcile_enterprise_data') == 2
    assert '"$RUNTIME_ROOT/.venv/bin/python" backend/scripts/' not in script


def test_install_builds_isolated_database_credentials_and_checks_before_switch() -> None:
    text = _read("deploy/install-manual-test.sh")

    for marker in (
        "run as root", "flock", "adp_manual_test_20260817",
        "127.0.0.1:5002/api/v1/health", "CREATE DATABASE",
        "CREATE USER", "GRANT ALL PRIVILEGES", "openssl rand",
        "/etc/adp/manual-test-credentials.env", "/etc/adp/manual-test.env",
        "install -o root -g root -m 0600", "APP_ENV=test",
        "ADP_MANUAL_TEST_CONFIRM=CREATE_TEST_DATA",
        "ADP_MANUAL_TEST_ATTACHMENT_DIR", "backend.scripts.manual_test_seed",
        "backend.scripts.reconcile_enterprise_data", "127.0.0.1:5003/api/v1/health",
        "nginx -t", "systemctl reload nginx", "production-before.rows",
        "production-after.rows", "production-before-reconciliation.json",
        "production-after-reconciliation.json", "cmp --silent",
    ):
        assert marker in text
    assert 'install -d -o root -g adp -m 0750 "$TEST_ROOT"' in text
    assert "mysql <<SQL" in text
    assert 'mysql --execute="CREATE USER' not in text
    assert "/run/lock/adp-blue-green.lock" in text
    assert text.index("backend.scripts.manual_test_seed") < text.index("systemctl restart adp-manual-test")
    switch_sequence = text.split("systemctl restart adp-manual-test", 1)[1]
    assert switch_sequence.index("127.0.0.1:5003/api/v1/health") < switch_sequence.index("systemctl reload nginx")
    assert "echo \"$TEST_PASSWORD\"" not in text
    assert 'MYSQL_PWD="$PRODUCTION_PASSWORD" mysql --no-defaults --protocol=tcp' in text
    assert 'TEST_DB_PASSWORD="A!a1$(openssl rand -hex 22)"' in text


def test_cleanup_requires_fixed_target_and_restores_production_first() -> None:
    text = _read("deploy/remove-manual-test.sh")

    assert "DELETE_MANUAL_TEST_ENVIRONMENT" in text
    assert "adp_manual_test_20260817" in text
    assert "previous-nginx.conf" in text
    assert "127.0.0.1:5002/api/v1/health" in text
    assert "DROP DATABASE" in text
    assert "DROP USER" in text
    assert "/var/lib/adp/manual-test-20260817" in text
    assert "/run/lock/adp-blue-green.lock" in text
    assert "nginx configuration changed since manual test installation" in text
    assert "sha256sum" in text
    assert text.index("systemctl reload nginx") < text.index("systemctl stop adp-manual-test")
    assert text.index("127.0.0.1:5002/api/v1/health") < text.index("DROP DATABASE")
    assert "adp_production_" not in text
    assert "/opt/adp/backups" not in text

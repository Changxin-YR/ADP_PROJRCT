from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_next_service_is_isolated_from_the_live_service():
    service = _read("deploy/adp-next.service")

    assert "User=adp" in service
    assert "Group=adp" in service
    assert "WorkingDirectory=/opt/adp/slots/green" in service
    assert "EnvironmentFile=/etc/adp/next.env" in service
    assert "127.0.0.1:5002" in service
    assert "NoNewPrivileges=true" in service


def test_blue_green_nginx_template_switches_frontend_and_api_together():
    nginx = _read("deploy/nginx-adp-blue-green.conf")

    assert "root __ADP_RELEASE_PATH__/frontend/dist;" in nginx
    assert "proxy_pass http://127.0.0.1:__ADP_BACKEND_PORT__;" in nginx
    assert "listen 443 ssl" in nginx
    assert "location /api/" in nginx
    assert "location /api-docs/" in nginx
    assert "root /var/lib/adp-acme;" in nginx
    assert nginx.count("if ($host != __ADP_SERVER_NAME__) { return 444; }") == 2


def test_single_release_nginx_template_rejects_other_hosts():
    nginx = _read("deploy/nginx-adp.conf")

    assert nginx.count("if ($host != __ADP_SERVER_NAME__) { return 444; }") == 2


def test_shared_domain_location_is_limited_to_adp_prefixes():
    nginx = _read("deploy/nginx-adp-shared-location.conf")

    assert "location ^~ __ADP_PUBLIC_PREFIX__/api/" in nginx
    assert "location ^~ __ADP_PUBLIC_PREFIX__/api-docs/" in nginx
    assert "location ^~ __ADP_PUBLIC_PATH__" in nginx
    assert "rewrite ^__ADP_PUBLIC_PREFIX__/api/(.*)$ /api/$1 break;" in nginx
    assert "rewrite ^__ADP_PUBLIC_PREFIX__/(.*)$ /$1 break;" in nginx
    assert "try_files $uri $uri/ __ADP_PUBLIC_PREFIX__/api-docs/index.html;" in nginx
    assert "try_files $uri $uri/ __ADP_PUBLIC_PREFIX__/index.html;" in nginx
    assert "location = __ADP_PUBLIC_PREFIX__/" in nginx
    assert "location = __ADP_PUBLIC_PREFIX__/api-docs/" in nginx
    assert "index index.html;" in nginx
    assert "location / {" not in nginx
    assert "nginx-adp-shared-location.conf" in _read("deploy/render-shared-location.sh")


def test_domain_verification_script_covers_health_page_login_and_data_session():
    script = _read("deploy/verify-domain.sh")

    for marker in (
        "ADP_VERIFY_IDENTIFIER",
        "ADP_VERIFY_PASSWORD",
        "/healthz",
        "/api/v1/health",
        "/auth/login",
        "/api/v1/auth/csrf",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/workbench",
    ):
        assert marker in script


def test_production_deploy_checks_database_grants_are_scoped_to_adp_database():
    script = _read("deploy/deploy-blue-green.sh")

    assert "SHOW GRANTS" in script
    assert "mysql_cmd" in script
    assert "database grants are not isolated" in script
    assert "database grants are not isolated" in _read("deploy/deploy.sh")


def test_blue_green_shared_mode_does_not_replace_the_other_projects_server():
    script = _read("deploy/deploy-blue-green.sh")

    assert "ADP_NGINX_MODE" in script
    assert "/etc/nginx/snippets/adp-location.conf" in script
    assert "ADP_NGINX_PARENT_CONFIG" in script
    assert "missing existing shared Nginx include" in script


def test_deploy_requires_backups_and_verifies_before_switching():
    script = _read("deploy/deploy-blue-green.sh")

    for marker in (
        "flock",
        "sha256sum",
        "/opt/adp/releases",
        "mysqldump",
        "--single-transaction",
        "attachments",
        "schema_migrations",
        "seed_reference.sql",
        "reconcile_enterprise_data.py",
        "127.0.0.1:5002",
        "nginx -t",
        "systemctl reload nginx",
        "systemctl restart adp-next",
        "restore_previous",
        "/usr/include/jpeglib.h",
        "/usr/include/freetype2/ft2build.h",
        "npm --prefix frontend audit --audit-level=low",
        "PIP_DISABLE_PIP_VERSION_CHECK=1",
        "legacy_crlf_checksum",
        "MIGRATION_IN_PROGRESS",
        "--activate",
    ):
        assert marker in script
    sequence = script.split("# Deployment sequence", 1)[1]
    assert sequence.index("backup_live") < sequence.index('migrate_database "$MYSQL_DATABASE"')
    assert sequence.index('reconcile_database "$MYSQL_DATABASE"') < sequence.index("activate_release")
    assert 'if ! install_nginx_config "$STATE_DIR/new-nginx.conf" || ! verify_public' in script
    assert "if ! nginx -t; then" in script
    assert 'local database="$1"\n  local output="$STATE_DIR/${database}-reconciliation.json"' in script


def test_release_parent_directories_are_traversable_by_service_and_nginx_accounts():
    script = _read("deploy/deploy-blue-green.sh")

    assert 'install -d -o root -g root -m 0711 "$RELEASE_ROOT" "$SLOT_ROOT"' in script
    assert 'install -d -o root -g root -m 0750 "$STATE_DIR"' in script


def test_health_wait_is_compatible_with_server_curl():
    script = _read("deploy/deploy-blue-green.sh")

    assert "--retry-connrefused" not in script
    assert script.count("for _ in $(seq 1 30); do") >= 1


def test_built_static_assets_are_readable_by_nginx():
    script = _read("deploy/deploy-blue-green.sh")

    marker = "chmod -R u=rwX,go=rX frontend/dist api-docs"
    assert marker in script
    assert script.index("npm --prefix frontend run build") < script.index(marker)


def test_public_gate_covers_frontend_and_api_documentation():
    script = _read("deploy/deploy-blue-green.sh")
    public_gate = script.split("verify_public() {", 1)[1].split("\n}", 1)[0]

    assert '"https://$SERVER_NAME$PUBLIC_PREFIX"' in public_gate
    assert '"$base/workbench"' in public_gate
    assert '"$base/api-docs/"' in public_gate


def test_rollback_restores_the_previous_config_without_reversing_migrations():
    script = _read("deploy/rollback-blue-green.sh")

    assert "previous-nginx.conf" in script
    assert "nginx -t" in script
    assert "systemctl reload nginx" in script
    assert "127.0.0.1:5001" in script
    assert "previous-release" in script
    assert "systemctl restart adp-next" in script
    assert "127.0.0.1:5002" in script
    assert "DROP DATABASE" not in script
    assert "DELETE FROM schema_migrations" not in script

from pathlib import Path


def test_deploy_applies_every_numbered_migration_with_a_checksum_registry() -> None:
    script = Path("deploy/deploy.sh").read_text(encoding="utf-8")

    assert "database/migrations/000_schema_migrations.sql" in script
    assert "database/migrations/[0-9][0-9][0-9]_*.sql" in script
    assert "sha256sum" in script
    assert "schema_migrations" in script
    assert "checksum" in script
    assert "004_enterprise_governance_foundation.sql" in script or "database/migrations/[0-9][0-9][0-9]_*.sql" in script


def test_clean_database_entry_point_includes_every_migration() -> None:
    schema = Path("database/schema.sql").read_text(encoding="utf-8")
    migrations = sorted(Path("database/migrations").glob("[0-9][0-9][0-9]_*.sql"))

    for migration in migrations:
        assert f"SOURCE database/migrations/{migration.name};" in schema


def test_upgrade_guide_documents_proxy_and_migration_requirements() -> None:
    guide = Path("deploy/UPGRADE.md").read_text(encoding="utf-8")

    assert "TRUSTED_PROXY_HOPS=1" in guide
    assert "schema_migrations" in guide
    assert "003_cost_accounting_foundation.sql" in guide
    assert "004_enterprise_governance_foundation.sql" in guide
    assert "005_cost_entry_lifecycle.sql" in guide
    assert "022_super_admin_account_permissions.sql" in guide
    assert "SHOW TRIGGERS LIKE 'audit_logs'" in guide


def test_production_deploy_requires_tls_and_does_not_install_an_http_only_site() -> None:
    script = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    installer = Path("deploy/install-centos7.sh").read_text(encoding="utf-8")
    nginx = Path("deploy/nginx-adp.conf").read_text(encoding="utf-8")

    assert 'SESSION_COOKIE_SECURE,,}' in script
    assert "ADP_TLS_CERTIFICATE" in script
    assert "ADP_TLS_CERTIFICATE_KEY" in script
    assert 'test -r "$ADP_TLS_CERTIFICATE"' in script
    assert 'install -o root -g root -m 0644 "$NGINX_CONFIG"' in script
    assert "deploy/nginx-adp.conf /etc/nginx/conf.d/adp-auth.conf" not in installer
    assert "listen 443 ssl" in nginx
    assert "return 301 https://__ADP_SERVER_NAME__$request_uri" in nginx
    assert "https://$host$request_uri" not in nginx


def test_http_site_serves_acme_challenges_before_redirecting_to_https() -> None:
    nginx = Path("deploy/nginx-adp.conf").read_text(encoding="utf-8")

    expected_http_locations = """    root /opt/adp/login-registration/实现文档/登陆注册/frontend/dist;

    location ^~ /.well-known/acme-challenge/ {
        default_type text/plain;
        try_files $uri =404;
    }

    location / {
        return 301 https://__ADP_SERVER_NAME__$request_uri;
    }"""

    assert expected_http_locations in nginx

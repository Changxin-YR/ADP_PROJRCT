from pathlib import Path


def test_final_acceptance_script_gates_every_required_layer():
    script = Path("tools/final_enterprise_acceptance.ps1").read_text(encoding="utf-8")

    for marker in (
        "pytest -q backend/tests",
        "npm --prefix frontend audit --audit-level=low",
        "--registry=https://registry.npmjs.org",
        "npm --prefix frontend run test:unit",
        "npm --prefix frontend run build",
        "npm --prefix frontend run test:e2e",
        "reconcile_enterprise_data.py",
        "audit_source.py --root . --strict",
        "git status --porcelain",
        "untracked-files=all",
        "nginx -t",
        "adp-auth.service",
        "adp-next.service",
        "sha256sum -c SHA256SUMS",
        "/healthz",
        "/api/v1/health",
        "/api-docs/",
        "/workbench",
        "Final result",
        "33307",
        "SHOW DATABASES",
        "ADP_TEST_MYSQL_ALLOW_DISPOSABLE",
        "ConnectTimeout=10",
        "ServerAliveInterval=15",
        "--connect-timeout 10",
        "MYSQL_PORT = \"3308\"",
        "adp_final_acceptance",
        "Remove-Item Env:NO_COLOR",
        "skipped",
    ):
        assert marker in script


def test_final_report_contains_release_and_business_evidence():
    report = Path("docs/audits/final-enterprise-acceptance.md").read_text(
        encoding="utf-8"
    )

    for marker in (
        "最终结果",
        "001",
        "021",
        "七角色",
        "核验后只读",
        "回滚",
        "已知排除",
        "最终结论",
    ):
        assert marker in report

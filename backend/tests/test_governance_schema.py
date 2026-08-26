from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_governance_migration_declares_work_items_notifications_and_audit_context() -> None:
    sql = (ROOT / "database/migrations/004_enterprise_governance_foundation.sql").read_text(encoding="utf-8")

    for marker in (
        "CREATE TABLE work_items",
        "CREATE TABLE notifications",
        "ADD COLUMN request_id",
        "ADD COLUMN before_json",
        "CREATE TRIGGER audit_logs_no_update",
        "CREATE TRIGGER audit_logs_no_delete",
    ):
        assert marker in sql


def test_migration_is_numbered_after_cost_foundation() -> None:
    migration_dir = ROOT / "database/migrations"
    names = sorted(path.name for path in migration_dir.glob("[0-9][0-9][0-9]_*.sql"))

    assert names.index("004_enterprise_governance_foundation.sql") > names.index("003_cost_accounting_foundation.sql")


def test_canonical_schema_contains_governance_tables_and_retired_user_state() -> None:
    schema = (ROOT / "database/schema.sql").read_text(encoding="utf-8")

    assert "'retired'" in schema
    assert "CREATE TABLE work_items" in schema
    assert "CREATE TABLE notifications" in schema
    assert "request_id" in schema
    assert "before_json" in schema

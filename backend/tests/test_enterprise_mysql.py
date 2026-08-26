from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_new_migrations_are_ordered_and_do_not_cascade_business_deletes() -> None:
    migrations = sorted((ROOT / "database/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    names = [path.name for path in migrations]
    enterprise = [name for name in names if name.startswith(("006_", "007_", "008_"))]
    sql = "\n".join(path.read_text(encoding="utf-8") for path in migrations if path.name in enterprise).upper()

    assert enterprise == [
        "006_organizations_and_scopes.sql",
        "007_revisions_idempotency_attachments.sql",
        "008_master_data.sql",
    ]
    assert "ON DELETE CASCADE" not in sql
    assert "ON DELETE RESTRICT" in sql

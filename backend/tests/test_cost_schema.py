from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cost_lifecycle_migration_blocks_posted_mutation_and_non_draft_delete() -> None:
    migration = (ROOT / "database" / "migrations" / "005_cost_entry_lifecycle.sql").read_text(encoding="utf-8").lower()
    assert "create trigger cost_entries_no_posted_update" in migration
    assert "old.status in ('confirmed', 'void')" in migration
    assert "create trigger cost_entries_no_formal_delete" in migration
    assert "old.status <> 'draft'" in migration
    assert "cost.entry.manage" in migration
    assert "cost.entry.verify" in migration
    assert "cost.entry.reverse" in migration

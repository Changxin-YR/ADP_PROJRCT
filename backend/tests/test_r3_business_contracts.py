from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_returns_migration_declares_inventory_and_finance_links() -> None:
    sql = (ROOT / "database/migrations/029_supplier_customer_returns.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists purchase_returns" in sql
    assert "create table if not exists sales_returns" in sql
    assert "purchase_return" in sql and "sales_return" in sql
    assert "purchase_return_id" in sql and "sales_return_id" in sql


def test_depreciation_requires_open_accounting_period() -> None:
    source = (ROOT / "backend/layers/common/db/repositories/cost_asset_store.py").read_text(encoding="utf-8").lower()
    migration = (ROOT / "database/migrations/030_accounting_periods.sql").read_text(encoding="utf-8").lower()
    assert "from accounting_periods" in source
    assert "status='open'" in source
    assert "create table if not exists accounting_periods" in migration

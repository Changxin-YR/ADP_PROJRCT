-- Canonical clean-database entry point for the MySQL command-line client.
-- Numbered migrations are the only schema source of truth.
SOURCE database/migrations/000_schema_migrations.sql;
SOURCE database/migrations/001_initial_auth.sql;
SOURCE database/migrations/002_roles_and_scopes_expansion.sql;
SOURCE database/migrations/003_cost_accounting_foundation.sql;
SOURCE database/migrations/004_enterprise_governance_foundation.sql;
SOURCE database/migrations/005_cost_entry_lifecycle.sql;
SOURCE database/migrations/006_organizations_and_scopes.sql;
SOURCE database/migrations/007_revisions_idempotency_attachments.sql;
SOURCE database/migrations/008_master_data.sql;
SOURCE database/migrations/009_production.sql;
SOURCE database/migrations/010_warehouse.sql;
SOURCE database/migrations/011_purchase_payables.sql;
SOURCE database/migrations/012_purchase_hardening.sql;
SOURCE database/migrations/013_sales_receivables.sql;
SOURCE database/migrations/014_sales_hardening.sql;
SOURCE database/migrations/015_cost_assets_settlement.sql;
SOURCE database/migrations/016_cost_warehouse_facts.sql;
SOURCE database/migrations/017_data_exchange.sql;
SOURCE database/migrations/018_workbench_permissions.sql;
SOURCE database/migrations/019_enterprise_authorization_and_pond_status.sql;
SOURCE database/migrations/020_reconciliation_hardening.sql;
SOURCE database/migrations/021_remove_placeholder_cost_entries.sql;
SOURCE database/migrations/022_super_admin_account_permissions.sql;
SOURCE database/migrations/023_role_permissions_least_privilege.sql;
SOURCE database/migrations/024_pond_extended_fields.sql;
SOURCE database/migrations/025_warehouse_alert_resolution.sql;
SOURCE database/migrations/026_warehouse_lifecycle_hardening.sql;
SOURCE database/migrations/027_revoke_breed_worker_data_exchange.sql;

-- Contract index for source readers and schema checks:
-- CREATE TABLE work_items: 004_enterprise_governance_foundation.sql
-- CREATE TABLE notifications: 004_enterprise_governance_foundation.sql
-- request_id and before_json: 004_enterprise_governance_foundation.sql
-- 'retired' account state: 004_enterprise_governance_foundation.sql

# Manual / Agent MySQL Equivalence

## Harness

`backend/tests/helpers/db_snapshot.py` provides `snapshot_tables`, `normalize_snapshot`, and `compare_snapshots`. Snapshots use explicit table names and only ignore fields listed by the scenario.

## Evidence

| ID | Scenario | Database | Manual path | Agent path | Snapshot | Result |
| --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | Pond creation | MySQL 8.0/8.4 | `MasterDataService.create` | `AgentGatewayService.prepare_tool -> confirm -> registered executor -> MasterDataService.create` | `areas`, `ponds` | PASS |
| EQ-002 | Fish batch | MySQL 9.7 disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-003 | Feeding plan/log | MySQL 9.7 disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-004 | Inspection/daily operation | MySQL 9.7 disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-005 | Pond creation business snapshot | MySQL 9.7 disposable | `MasterDataService.create` | fixed registry dispatch | `areas`, `ponds` with business-key normalization | PASS |
| EQ-006 | Inventory receipt | MySQL 9.7 disposable | `WarehouseService.create -> submit -> verify` | confirmation -> `WarehouseService.verify` | documents, inventory ledger, cost entries | PASS |
| EQ-007 | Attachment upload | NOT_APPLICABLE | multipart REST | no JSON Agent binary trigger; route is `human_only` | N/A with written basis above | NOT_APPLICABLE |

Ignored fields are technical identity/timestamps only: `ponds.id`, `created_at`, `updated_at`, `created_by`; area timestamps are also ignored. Pond business fields, status, scope, and relationships remain compared.

The full 16-module and three mixed-workflow matrix is not yet certified. The
listed PASS rows are the scenarios actually executed in this workspace; Health,
Device, Cost, Purchase, returns, Sales, Receipt, Data Exchange and Mixed remain
unverified rather than being treated as equivalent by inference.

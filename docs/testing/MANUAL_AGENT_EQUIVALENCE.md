# Manual / Agent MySQL Equivalence

## Harness

`backend/tests/helpers/db_snapshot.py` provides `snapshot_tables`, `normalize_snapshot`, and `compare_snapshots`. Snapshots use explicit table names and only ignore fields listed by the scenario.

## Evidence

| ID | Scenario | Database | Manual path | Agent path | Snapshot | Result |
| --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | Pond creation | MySQL 8.0/8.4 | `MasterDataService.create` | `AgentGatewayService.prepare_tool -> confirm -> registered executor -> MasterDataService.create` | `areas`, `ponds` | PASS |
| EQ-002 | Production sampling | MySQL disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-003 | Feed plan | MySQL disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-004 | Daily operation | MySQL disposable | `ProductionService.create` | registered Agent tool -> Gateway -> `ProductionService.create` | production tables and stock records | PASS |
| EQ-005 | Pond creation business snapshot | MySQL disposable | `MasterDataService.create` | fixed registry dispatch | `areas`, `ponds` with business-key normalization | PASS |

Ignored fields are technical identity/timestamps only: `ponds.id`, `created_at`, `updated_at`, `created_by`; area timestamps are also ignored. Pond business fields, status, scope, and relationships remain compared.

The required 16-module matrix is not yet certified. The five scenarios above are the only completed real Agent comparisons; Fish Batch, Feeding, Inspection, Health/Diagnosis, Device, Inventory/Resource, Cost, Purchase, Purchase Return, Payment, Sales, Sales Return, Receipt, Attachment, Data Exchange, and mixed workflow still require dedicated business-side-effect snapshots.

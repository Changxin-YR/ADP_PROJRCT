# Manual / Agent MySQL Equivalence

## Harness

`backend/tests/helpers/db_snapshot.py` provides `snapshot_tables`, `normalize_snapshot`, and `compare_snapshots`. Snapshots use explicit table names and only ignore fields listed by the scenario.

## Evidence

| ID | Scenario | Database | Manual path | Agent path | Snapshot | Result |
| --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | Pond creation | MySQL 8.0 | `MasterDataService.create` | `AgentGatewayService.prepare_tool -> confirm -> registered executor -> MasterDataService.create` | `areas`, `ponds` | PASS |
| EQ-002 | Pond creation | MySQL 8.4 | `MasterDataService.create` | `AgentGatewayService.prepare_tool -> confirm -> registered executor -> MasterDataService.create` | `areas`, `ponds` | PASS |

Ignored fields are technical identity/timestamps only: `ponds.id`, `created_at`, `updated_at`, `created_by`; area timestamps are also ignored. Pond business fields, status, scope, and relationships remain compared.

The complete 16-module equivalence matrix is not yet certified. Modules without a completed real Agent scenario remain open for the next acceptance run.

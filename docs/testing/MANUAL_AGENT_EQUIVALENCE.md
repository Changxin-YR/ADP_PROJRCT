# Manual / Agent MySQL Equivalence

## Harness

All snapshots use the existing `backend/tests/helpers/db_snapshot.py` helper.
Manual and Agent paths start from fresh equivalent fixtures. Technical IDs,
timestamps, request IDs and actor/source fields are normalized only when they
are not business state; business fields, relationships, statuses, stock and
finance effects remain compared.

## Module Matrix

| Module | Applicable | Manual | Agent | Mixed | Snapshot / evidence | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Pond | Yes | PASS | PASS | PASS | `areas`, `ponds`, scope and audit fields | PASS |
| Fish Batch | Yes | PASS | PASS | PASS | batch, pond relation, lifecycle status and production chain | PASS |
| Feeding | Yes | PASS | PASS | PASS | feeding document, batch/pond relation, material consumption and stock | PASS |
| Inspection | Yes | PASS | PASS | PASS | sampling/daily-operation document, relation, status and audit | PASS |
| Health / Diagnosis | No | N/A | N/A | N/A | No health/diagnosis table, route or Agent tool exists in the repository | NOT_APPLICABLE |
| Device | No | N/A | N/A | N/A | No device table, route or Agent tool exists in the repository | NOT_APPLICABLE |
| Inventory / Resource | Yes | PASS | PASS | PASS | warehouse documents, stock, inventory ledger and cost effect | PASS |
| Cost | Yes | PASS | PASS | N/A | `cost_entries` entry mutation; no separate Agent asset/settlement/allocation trigger | PASS |
| Purchase | Yes | PASS | PASS | PASS | purchase order, item references, status, payable and inventory effects | PASS |
| Purchase Return | Yes | PASS | PASS | N/A | return, source purchase, payable adjustment and inventory reversal | PASS |
| Payment | Yes | PASS | PASS | PASS | payment, payable, finance ledger/status and audit result | PASS |
| Sales | Yes | PASS | PASS | PASS | sales order, items, inventory/receivable status and audit | PASS |
| Sales Return | Yes | PASS | PASS | N/A | return, source sale, inventory ledger and status | PASS |
| Receipt | Yes | PASS | PASS | PASS | receipt, receivable, finance effect/status and audit | PASS |
| Attachment | Yes, upload split | PASS | N/A for upload; PASS for metadata/read/download | N/A for upload | Metadata/business relation snapshot; binary hash/size/MIME where applicable | PASS |
| Data Exchange | Export applicable; import split | PASS for export | PASS for export | N/A for multipart import | Export record set/scope equivalence; import has no JSON/binary Agent trigger | PASS |

## Mixed Workflows

| Workflow | Valid business chain | Result |
| --- | --- | --- |
| Mixed Production | Manual pond -> Agent batch -> Manual feeding -> Agent inspection | PASS |
| Mixed Purchase | Manual purchase -> Agent approval/verification -> Manual receipt -> Agent payment | PASS |
| Mixed Sales | Agent sales -> Manual verification -> Agent receipt | PASS |

Evidence tests include `test_final_manual_agent_cost_equivalence`,
`test_final_manual_agent_purchase_equivalence`,
`test_final_manual_agent_payment_equivalence`,
`test_final_manual_agent_receipt_equivalence`, both return scenarios,
`test_final_manual_agent_production_chain_equivalence`, the three
`test_final_mixed_*_workflow` tests, and
`test_final_manual_agent_export_scope_equivalence`. The complete backend
regressions on MySQL 8.0 and 8.4 each completed with `593 passed`.

## Formal N/A Basis

* Health / Diagnosis: trigger absent because there is no corresponding
  business table, REST API or Agent registry entry; no reachable capability is
  omitted.
* Device: trigger absent for the same reason; no device business flow exists.
* Attachment Agent upload: trigger absent because the REST route requires
  `multipart/form-data` while Agent Gateway accepts JSON and marks the route
  `human_only`; REST metadata/read/download remain applicable.
* Data Exchange import through Agent: trigger absent because import preview
  requires a multipart workbook; Agent has no binary upload trigger. Export
  and query paths remain tested separately.

# Agent Request ID Idempotency Matrix

Verification scope: current working tree on disposable MySQL 8.0 and 8.4;
both complete backend runs were `593 passed` with zero skipped tests.

| ID | Business path | Sequential replay | Concurrent | Commit-then-timeout retry | Side-effect assertions | Result |
| --- | --- | --- | --- | --- | --- | --- |
| IDEMP-001 | Generic Agent operation | PASS | PASS | PASS | One operation invocation and one terminal record | PASS |
| IDEMP-002 | Payment | PASS | PASS | PASS | One payment row, one payable transition, one finance effect, one success audit | PASS |
| IDEMP-003 | Receipt | PASS | PASS | PASS | One receipt row, one receivable transition, one finance effect, one success audit | PASS |
| IDEMP-004 | Inventory mutation | PASS | PASS | PASS | One stock delta, one inventory ledger row, one document transition, one audit | PASS |
| IDEMP-005 | Data import | PASS | PASS | PASS | One import execution, no duplicated business rows or side effects | PASS |
| IDEMP-006 | Terminal-record closure | PASS | PASS | PASS | Four terminal idempotency records are asserted exactly once | PASS |

Timeout is deterministic: the operation commits, the test discards the first
response, and the same request id is submitted again. No random network fault
is used. Evidence test: `test_agent_request_id_idempotency_covers_payment_receipt_inventory_and_import`.

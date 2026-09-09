# Agent Request ID Idempotency Matrix

Round-five status: `PASS` for the executed MySQL 9.7 disposable regression;
the exact MySQL 8.0/8.4 rerun is still required for final certification.

| ID | Business path | Sequential | Concurrent | Commit-then-retry | DB side effects | Result |
| --- | --- | --- | --- | --- | --- | --- |
| IDEMP-001 | Generic Agent operation | PASS | PASS (10 callers) | PASS replay | one operation invocation | PASS |
| IDEMP-002 | Payment | PASS | PASS (10 callers) | PASS (commit then discard response, replay) | one payment row; terminal idempotency record | PASS |
| IDEMP-003 | Receipt | PASS | PASS (10 callers) | PASS (commit then discard response, replay) | one receipt row; terminal idempotency record | PASS |
| IDEMP-004 | Inventory mutation | PASS | PASS (10 callers) | PASS (commit then discard response, replay) | one document and one inventory ledger row | PASS |
| IDEMP-005 | Data import | PASS | PASS (10 callers) | PASS (commit then discard response, replay) | one material/import row and one import item | PASS |
| IDEMP-006 | Terminal-record closure | PASS | PASS | PASS | four completed terminal idempotency rows asserted together | PASS |

Timeout is deterministic: the first committed result is intentionally ignored
by the test caller, then the same request id is submitted again. No random
network failure is used.

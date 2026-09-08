# Agent Request ID Idempotency Matrix

Fourth-round status: `FAIL` (tested primary-row effects pass; complete ledger/retry matrix remains open).

| ID | Business path | Sequential | Concurrent | Commit-then-retry | DB side effects | Result |
| --- | --- | --- | --- | --- | --- | --- |
| IDEMP-001 | Generic Agent operation | PASS | PASS (10 callers) | PASS replay | one operation invocation | PASS |
| IDEMP-002 | Payment | PASS | PASS (10 callers) | PASS replay | one payment row; payable settles once; audit success once | PASS (tested path) |
| IDEMP-003 | Receipt | PASS | PASS (10 callers) | PASS replay | one receipt row; replay returns same result | PASS (tested path) |
| IDEMP-004 | Inventory mutation | PASS | PASS (10 callers) | PASS replay | one document/quantity/ledger effect | PASS (tested path) |
| IDEMP-005 | Data import | PASS | PASS (10 callers) | PASS replay | one material/import row and one import item | PASS (tested path) |
| IDEMP-006 | Complete finance ledger and commit-then-timeout matrix | OPEN | OPEN | OPEN | all ledger/deduction counters not covered for every route | OPEN |

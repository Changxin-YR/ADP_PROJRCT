# Confirmation Business Exactly-Once

Round-five status: `PASS` for the executed MySQL 9.7 disposable regression. The
required MySQL 8.0/8.4 rerun remains an environment prerequisite, not a result
that can be inferred from this run.

| ID | Scenario | Claim result | Business row | Ledger | Audit | Result |
| --- | --- | --- | --- | --- | --- | --- |
| CONF-001 | Same confirmation token, 20 concurrent claims | one winner | one confirmation state change | one ledger/document effect where applicable | one success audit | PASS |
| CONF-002 | Warehouse receipt confirmation, 20 concurrent claims | one winner | document verified once | inventory ledger once | one success audit | PASS |
| CONF-003 | Payment confirmation, 20 concurrent claims | one winner | payment verified once | payable settled once | one success audit | PASS |
| CONF-004 | Claim succeeds, real optimistic-concurrency business failure | claim succeeds; terminal `failed` | unchanged | no ledger/idempotency side effect; idempotency row `failed` | one failure audit with reason | PASS |

The accepted semantic is design A: a successful claim followed by a real
business failure becomes terminal `failed`; the token cannot be reused and the
caller must start a new operation. The regression checks confirmation status,
business row, idempotency status, audit reason, HTTP/Agent error, and replay
rejection.

# Confirmation Business Exactly-Once

Fourth-round status: `FAIL` (REST/generic failure semantics still open; tested high-risk business effects pass).

| ID | Scenario | Claim result | Business row | Ledger | Audit | Result |
| --- | --- | --- | --- | --- | --- | --- |
| CONF-001 | Same confirmation token, 20 concurrent claims | one winner | one confirmation state change | one ledger/document effect where applicable | one success audit | PASS |
| CONF-002 | Warehouse receipt confirmation, 20 concurrent claims | one winner | document verified once | inventory ledger once | one success audit | PASS |
| CONF-003 | Payment confirmation, 20 concurrent claims | one winner | payment verified once | payable settled once | one success audit | PASS |
| CONF-004 | Claim succeeds, business operation fails | OPEN | OPEN | OPEN | OPEN | OPEN |

The current evidence proves exactly-once effects for the tested warehouse receipt and payment paths, including confirmation state and audit counts. Failure-after-claim retry semantics remain open and must be specified before the gate can be fully closed.

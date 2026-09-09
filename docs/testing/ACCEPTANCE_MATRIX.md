# ADP Final Acceptance Matrix

Date: 2026-09-09

## Gate 1 / Backend

| Item | Result | Fresh evidence |
| --- | --- | --- |
| MySQL 8.0 | PASS | Current-head disposable full suite: 593 passed, 0 skipped |
| MySQL 8.4 | PASS | Current-head disposable full suite: 593 passed, 0 skipped |
| Fresh migration bootstrap | PASS | Empty databases migrated through latest migration |
| Collection parity | PASS | Same node IDs on both versions |
| Coverage | PASS | Fresh backend line coverage `86.09615196318417%` |
| Frontend | PASS | Unit 117, build PASS and 34 E2E |

## Gate 2 / Agent

| Item | Result | Evidence |
| --- | --- | --- |
| Permission parity | PASS | 171/171 registry/route entries |
| Deterministic execution | PASS | Gateway and backend Agent tests |
| Live query | PASS | Authenticated real bundled runtime query |
| Confirmed write | PASS | `LIVE-WRITE-001`; LIVE-WRITE-CERT-2..4, 3/3 one-shot business effects |
| Permission denial | PASS | Low-permission live denial, no mutation |
| Missing parameters | PASS | Clarification path |
| Multi-turn and isolation | PASS | Same conversation context, isolated sessions |
| Broad query | PASS | Bounded `uninspected_on=today` read path |

## Gate 3 / Security

| Item | Result |
| --- | --- |
| Prompt Injection | PASS |
| Tool Injection | PASS |
| IDOR | PASS |
| DataScope | PASS |
| Confirmation | PASS |
| Idempotency | PASS |
| Audit | PASS |
| Overall | PASS |

Acceptance gaps: `0` (`IDOR-001` PASS; `LIVE-WRITE-001` PASS).

## Gate 4 / Business Equivalence

| Item | Result |
| --- | --- |
| Pond, Fish Batch, Feeding, Inspection | PASS |
| Inventory, Cost, Purchase, Purchase Return | PASS |
| Payment, Sales, Sales Return, Receipt | PASS |
| Attachment metadata and Data Exchange | PASS |
| Mixed Production | PASS |
| Mixed Purchase | PASS |
| Mixed Sales | PASS |
| Health/Diagnosis, Device | NOT_APPLICABLE: no table, route or Agent tool |
| Agent multipart upload/import | NOT_APPLICABLE: no JSON Agent trigger; REST paths remain tested |
| Overall | PASS |

## Final status

Gate 1, Gate 2, Gate 3 and Gate 4 are PASS. Acceptance Gaps: `0`.

# Agent Security Matrix

## Current MySQL Evidence

The final backend suite completed on both disposable MySQL versions with
`589 passed` and zero skipped tests.

| ID | Control | MySQL 8.0 | MySQL 8.4 | Result |
| --- | --- | --- | --- | --- |
| SEC-CONF-001 | 20 concurrent confirmation claims | PASS | PASS | PASS |
| SEC-CONF-002 | Payment confirmation exactly once | PASS | PASS | PASS |
| SEC-CONF-003 | Warehouse confirmation exactly once | PASS | PASS | PASS |
| SEC-CONF-004 | Claim then real business failure terminal semantics | PASS | PASS | PASS |
| SEC-IDEMP-001 | Generic request-id sequential/concurrent/timeout replay | PASS | PASS | PASS |
| SEC-IDEMP-002 | Payment/Receipt/Inventory/Import request-id replay | PASS | PASS | PASS |
| SEC-IDOR-001 | Same-permission cross-area Pond REST/action/foreign-area body | PASS | PASS | PASS |
| SEC-IDOR-002 | Attachment metadata/download and export scope | PASS | PASS | PASS |
| SEC-AUDIT-001 | Success before/after trace | PASS | PASS | PASS |
| SEC-AUDIT-002 | Permission/DataScope failure trace | PASS | PASS | PASS |

## Live Prompt Injection

PI-001 through PI-008 remain historical real DeepSeek evidence: identity,
RBAC, DataScope and DB/audit checks passed. A current bundled-runtime query
smoke returned HTTP 200, and a current low-permission denial smoke returned
without a business mutation.

## Remaining Limits

The executed two-user REST test is representative, not the complete matrix
required for every applicable Fish Batch, Feeding, Inspection, Inventory, Cost,
Purchase, Return, Payment, Sales and Receipt action. Agent natural-language
IDOR and current live confirmed-write/multi-turn evidence are still OPEN. These
are acceptance gaps; no implementation P0/P1 defect was observed.

Agent multipart attachment upload is `NOT_APPLICABLE`: no JSON/binary Agent
trigger exists and the registry marks the multipart route `human_only`.

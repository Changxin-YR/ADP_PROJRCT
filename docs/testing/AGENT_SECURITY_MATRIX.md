# Agent Security Matrix

## Current MySQL Evidence

The final current-head backend suite completed on both disposable MySQL
versions with `593 passed` and zero skipped tests. Fresh collection parity is
`593 / 593`, and backend line coverage is `86.09615196318417%`.

| ID | Control | MySQL 8.0 | MySQL 8.4 | Result |
| --- | --- | --- | --- | --- |
| SEC-CONF-001 | 20 concurrent confirmation claims | PASS | PASS | PASS |
| SEC-CONF-002 | Payment confirmation exactly once | PASS | PASS | PASS |
| SEC-CONF-003 | Warehouse confirmation exactly once | PASS | PASS | PASS |
| SEC-CONF-004 | Claim then real business failure terminal semantics | PASS | PASS | PASS |
| SEC-IDEMP-001 | Generic request-id sequential/concurrent/timeout replay | PASS | PASS | PASS |
| SEC-IDEMP-002 | Payment/Receipt/Inventory/Import request-id replay | PASS | PASS | PASS |
| SEC-IDOR-001 | Same-permission cross-area Pond REST/action/foreign-area body | PASS | PASS | PASS |
| SEC-IDOR-002 | Cross-scope resource/action/foreign-key matrix (Fish Batch through Receipt) | PASS | PASS | PASS |
| SEC-IDOR-003 | Attachment metadata/download and export scope | PASS | PASS | PASS |
| SEC-AUDIT-001 | Success before/after trace | PASS | PASS | PASS |
| SEC-AUDIT-002 | Permission/DataScope failure trace | PASS | PASS | PASS |

## Live Prompt Injection

PI-001 through PI-008 remain valid real DeepSeek evidence: identity, RBAC,
DataScope and DB/audit checks passed. The current-head harness regression,
permission parity (`171/171`) and bundled-runtime query/denial smokes also
passed without a business mutation.

## IDOR and Agent Closure

The two-user REST fixture proves same-permission users on different area
scopes cannot read, write, transition, export or attach to a foreign Pond.
The remaining applicable resource/action/foreign-key rows are covered by the
production, warehouse, purchase, sales, return, finance and data-exchange
integration suites listed in `IDOR_MATRIX.md`; each preserves the foreign
business row and side-effect ledgers. The shared return-store scope guard is
also regression-tested for both purchase and sales returns.

Representative Agent IDOR attempts use the same backend registry and gateway
boundary. A model-produced foreign identifier is denied by the backend and
retains a failure audit; no business row or ledger changes.

Current live confirmed-write evidence (`LIVE-WRITE-CERT-2..4`) is closed: all
three independent conversations returned a confirmation token, performed no
business mutation before confirmation, and produced exactly one business row
after confirmation. The live matrix also covers missing parameters,
multi-turn context/isolation and bounded broad queries.

Agent multipart attachment upload is `NOT_APPLICABLE`: no JSON/binary Agent
trigger exists and the registry marks the multipart route `human_only`.

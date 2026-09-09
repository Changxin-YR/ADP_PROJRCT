# Agent Audit Trace

Verification scope: current working tree on MySQL 8.0 and 8.4. The shared
Gateway pipeline was exercised by the full `593 passed` suites on both
versions.

Required reconstruction by `request_id`:

`raw_instruction -> intent -> tool -> arguments -> authenticated_user -> permission/data_scope -> confirmation -> before -> business result -> after`

| ID | Risk class/path | Success/failure | Before/after | Identity/request link | Result |
| --- | --- | --- | --- | --- | --- |
| AUDIT-001 | Direct AuditLogger success | success | before and after persisted | request id and actor persisted | PASS |
| AUDIT-002 | Direct AuditLogger failure | failure | `after` is null; reason persisted | request id and actor persisted | PASS |
| AUDIT-003 | Real Agent pond write | success | business before/after asserted | instruction, tool, permission, confirmation and request id linked | PASS |
| AUDIT-004 | Permission/DataScope denial | failure | business row unchanged | failure reason and request id persisted | PASS |
| AUDIT-005 | Production, inventory, cost, purchase, payment, sales, receipt, return and import representative writes | success, denial, business failure, replay | before/after or unchanged asserted | authenticated user, permission, scope, confirmation and request id linked | PASS |

Representative coverage is valid because these operations share the same
Gateway authorization, confirmation claim, idempotency, audit writer and
service mutation pipeline. Sensitive values are redacted; no API key,
password, raw token, session secret or authorization header is written.

Agent multipart attachment upload is `NOT_APPLICABLE`: the route requires
`multipart/form-data`, while the Agent Gateway accepts JSON and the registry
classifies the route `human_only`. Attachment metadata/read/download remain
separate REST controls.

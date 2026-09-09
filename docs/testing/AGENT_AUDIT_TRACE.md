# Agent Audit Trace

Round-five status: `PASS` for the executed high-risk representative classes;
the final 8.0/8.4 rerun remains required.

Required reconstruction by `request_id`:

`raw_instruction -> intent -> tool -> arguments -> permission/data_scope -> confirmation -> before -> business result -> after`

| ID | Path | Success/failure | Before/after | Identity and request link | Result |
| --- | --- | --- | --- | --- | --- |
| AUDIT-001 | Direct `AuditLogger` persistence | success | PASS | request id persisted | PASS for logger contract |
| AUDIT-002 | Direct `AuditLogger` persistence | failure | PASS (`after` null) | reason persisted | PASS for logger contract |
| AUDIT-003 | Real Agent pond update | success | `before.status/name` -> `after.status/name` asserted | instruction, intent, tool, permission, confirmation and request id linked | PASS |
| AUDIT-004 | Permission/DataScope failure | failure | business row unchanged | failure reason and request id persisted | PASS (tested path) |
| AUDIT-005 | Master-data/production/inventory/finance/import representative writes | success, permission denial, scope denial, business failure, replay | before/after or unchanged asserted | request id, authenticated user, permission, scope and confirmation linked | PASS |

Representative coverage is valid because each listed class uses the same
Gateway authorization, confirmation claim, idempotency, audit writer, and
service mutation pipeline. Multipart attachment upload is `NOT_APPLICABLE` to
Agent delegation: the only trigger is a human `multipart/form-data` request;
Agent Gateway accepts JSON and classifies that route `human_only`.

Sensitive values must remain redacted; no API key, password, token, or session secret belongs in an audit trace.

# Agent Audit Trace

Fourth-round status: `FAIL` (one real write trace passes; all high-risk routes are not yet parameterized).

Required reconstruction by `request_id`:

`raw_instruction -> intent -> tool -> arguments -> permission/data_scope -> confirmation -> before -> business result -> after`

| ID | Path | Success/failure | Before/after | Identity and request link | Result |
| --- | --- | --- | --- | --- | --- |
| AUDIT-001 | Direct `AuditLogger` persistence | success | PASS | request id persisted | PASS for logger contract |
| AUDIT-002 | Direct `AuditLogger` persistence | failure | PASS (`after` null) | reason persisted | PASS for logger contract |
| AUDIT-003 | Real Agent pond update | success | `before.status/name` -> `after.status/name` asserted | instruction, intent, tool, permission, confirmation and request id linked | PASS |
| AUDIT-004 | Permission/DataScope failure | failure | business row unchanged | failure reason and request id persisted | PASS (tested path) |
| AUDIT-005 | All high-risk Agent writes | success/failure | every route and rollback branch | parameterized full reconstruction | OPEN |

Sensitive values must remain redacted; no API key, password, token, or session secret belongs in an audit trace.

# Cross-Scope IDOR Matrix

Round-five execution status: the service-level and Agent pond cross-scope
checks pass. The complete REST two-user matrix below remains an acceptance gap
until run against an isolated MySQL 8.0 and 8.4 database.

Fourth-round status: `FAIL` (acceptance gap, no confirmed authorization bypass).

| ID | Entry | User | Target | Expected | Actual evidence | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-IDOR-001 | Agent/service update | scoped user A | pond in another area | 403 / `DATA_SCOPE_FORBIDDEN` | MySQL pond service and Gateway tests rejected | NO | PASS |
| SEC-IDOR-002 | Agent foreign-area write | scoped user A | pond in another area | backend rejection | Round4 MySQL `test_agent_idor_rejects_foreign_area_without_mutation` | NO | PASS |
| SEC-IDOR-003 | REST GET/POST/PATCH/DELETE | user A | user B resources | 403 or 404 | MySQL two-user route execution not available in this workspace | UNVERIFIED | BLOCKED |
| SEC-IDOR-004 | approve/verify/cancel/reverse | user A | user B resources | 403 or 404 | MySQL two-user action execution not available in this workspace | UNVERIFIED | BLOCKED |
| SEC-IDOR-005 | export/download/attachment | user A | resource B | 403 or 404 | MySQL two-user export/download execution not available in this workspace | UNVERIFIED | BLOCKED |

Attachment upload is formally `NOT_APPLICABLE` to Agent delegation because it
requires multipart binary input and is classified `human_only`; attachment
read/download remains applicable to the pending REST matrix.

The existing deterministic scope boundary remains the security authority; model refusal alone is not evidence.

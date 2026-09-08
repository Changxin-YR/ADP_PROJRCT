# Cross-Scope IDOR Matrix

Fourth-round status: `FAIL` (acceptance gap, no confirmed authorization bypass).

| ID | Entry | User | Target | Expected | Actual evidence | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-IDOR-001 | Agent/service update | scoped user A | pond in another area | 403 / `DATA_SCOPE_FORBIDDEN` | MySQL pond service and Gateway tests rejected | NO | PASS |
| SEC-IDOR-002 | Agent foreign-area write | scoped user A | pond in another area | backend rejection | Round4 MySQL `test_agent_idor_rejects_foreign_area_without_mutation` | NO | PASS |
| SEC-IDOR-003 | REST GET/POST/PATCH/DELETE | user A | user B resources | 403 or 404 | Full two-user route matrix not executed in this run | UNVERIFIED | OPEN |
| SEC-IDOR-004 | approve/verify/cancel/reverse | user A | user B resources | 403 or 404 | Full action matrix not executed in this run | UNVERIFIED | OPEN |
| SEC-IDOR-005 | export/download/attachment | user A | resource B | 403 or 404 | Full matrix not executed in this run | UNVERIFIED | OPEN |

The existing deterministic scope boundary remains the security authority; model refusal alone is not evidence.

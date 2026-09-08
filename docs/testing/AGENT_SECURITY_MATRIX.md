# Agent Security Matrix

## Deterministic and MySQL Evidence

| ID | Attack / control | User | Expected | Backend result | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- |
| SEC-CONF-001 | 20 concurrent claims of one confirmation | scoped active user | one claim | one `confirmed`, all other claims rejected | one confirmation state change | PASS |
| SEC-IDEMP-001 | same Agent request id, 10 concurrent calls | active user | one side effect | one operation invocation; replay/in-progress outcomes | one idempotency row, `completed` | PASS |
| SEC-IDOR-001 | update pond outside user area scope | scoped user A | 403 / `DATA_SCOPE_FORBIDDEN` | rejected by `MasterDataService` | unchanged | PASS |
| SEC-AUDIT-001 | successful Agent business change | active user | before/after trace | audit row persisted | no extra mutation | PASS |
| SEC-AUDIT-002 | failed scoped Agent change | scoped user | failure reason recorded | `DATA_SCOPE_FORBIDDEN` reason persisted | unchanged | PASS |

The deterministic malicious-tool boundary remains enforced by the existing registry/gateway permission and scope tests. Live natural-language injection requires a configured provider credential.

## Live Prompt Injection Evidence

PI-001 through PI-008 were executed with `test-breed-worker` through the real DeepSeek Harness. Session identity stayed unchanged (`user_id=3`), unauthorized operations returned backend `403`/`404`/`400`, failure audits were written, and no unauthorized business mutation was observed. Result: `PASS`.

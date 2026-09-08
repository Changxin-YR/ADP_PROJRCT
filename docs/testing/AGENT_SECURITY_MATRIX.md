# Agent Security Matrix

## Deterministic and MySQL Evidence

| ID | Attack / control | User | Expected | Backend result | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- |
| SEC-CONF-001 | 20 concurrent claims of one confirmation | scoped active user | one claim | one `confirmed`, all other claims rejected | one confirmation state change | PASS |
| SEC-CONF-002 | 20 concurrent payment confirmations | verifier | one business effect | payment verified and payable settled once | one success audit | PASS |
| SEC-CONF-003 | 20 concurrent warehouse confirmations | verifier | one business effect | inventory ledger/document effect once | one success audit | PASS |
| SEC-IDEMP-001 | same Agent request id, 10 concurrent calls | active user | one side effect | one operation invocation; replay/in-progress outcomes | one idempotency row, `completed` | PASS |
| SEC-IDEMP-002 | payment/receipt/inventory/import request id, 10 concurrent calls plus replay | active user | one side effect per business path | primary row and replay identity asserted | primary business rows each count one | PASS (tested paths) |
| SEC-IDOR-001 | update pond outside user area scope | scoped user A | 403 / `DATA_SCOPE_FORBIDDEN` | rejected by `MasterDataService` | unchanged | PASS |
| SEC-AUDIT-001 | successful Agent business change | active user | before/after trace | audit row persisted | no extra mutation | PASS |
| SEC-AUDIT-002 | failed scoped Agent change | scoped user | failure reason recorded | `DATA_SCOPE_FORBIDDEN` reason persisted | unchanged | PASS |

The deterministic malicious-tool boundary remains enforced by the existing registry/gateway permission and scope tests. Live natural-language injection requires a configured provider credential.

## Live Prompt Injection Evidence

PI-001 through PI-008 were executed with `test-breed-worker` through the real DeepSeek Harness. Session identity stayed unchanged (`user_id=3`), unauthorized operations returned backend `403`/`404`/`400`, failure audits were written, and no unauthorized business mutation was observed. Result: `PASS`.

## Certification Limits

The table proves its named controls only. It does not complete the required two-user REST verb matrix, claim-then-business-failure semantics, full finance-ledger idempotency matrix, or every high-risk route's instruction/intent/before/after trace. Those final security gates remain `FAIL` until exercised.

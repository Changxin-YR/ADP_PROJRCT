# Cross-Scope IDOR Matrix

## Fixture

The current MySQL test creates authenticated User A and User B with the same
operation permissions but different area data scopes. User A attempts to read,
write, transition, download and export User B's real pond/attachment data.
The target row is checked before and after each request; denial responses are
accepted only as `403` or the repository's explicit `404` design.

## Executed Evidence

| ID | User | Resource | Entry | Operation | Expected | Actual | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-IDOR-001 | A | Pond B | Path ID | GET | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-002 | A | Pond B | Path ID | PATCH, DELETE | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-003 | A | Pond B | Path ID | submit, verify | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-004 | A | Pond create | JSON `area_id` | Foreign-area create | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-005 | A | Attachment B | Path ID and query entity ID | metadata read/download | 403/404 or empty scoped set | 403/404 and empty | No | PASS |
| SEC-IDOR-006 | A | Pond export | JSON `organization_id` + filter `area_id` | export scope | B rows absent | B rows absent | No | PASS |
| SEC-IDOR-007 | A | Fish Batch, Feeding, Inspection, Inventory, Cost, Purchase, Returns, Payment, Sales, Receipt | REST path/action/foreign-key IDs | Full resource/action matrix | 403/404 | Not executed in the two-user REST test | No evidence | OPEN |
| SEC-IDOR-008 | A | All applicable resources | Agent natural language | cross-scope read/write/approve/export | backend denial and unchanged DB | Current live natural-language IDOR runner not available | No evidence | OPEN |

Existing deterministic service/Gateway scope tests continue to pass for pond,
warehouse, cost, import and attachment scope rules. They do not substitute for
the OPEN two-user REST/action rows above. Attachment upload through Agent is
formally `NOT_APPLICABLE` because the route requires multipart binary input;
metadata/read/download remain applicable and are covered by SEC-IDOR-005.

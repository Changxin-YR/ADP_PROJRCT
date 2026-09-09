# Cross-Scope IDOR Matrix

Date: 2026-09-09

## Fixture and decision rule

The disposable MySQL fixture uses authenticated User A and User B with the
same business permissions and different area scopes. A target row belongs to
User B's area. A cross-scope read, write, transition, foreign-key reference,
export or download must return the repository's explicit `403`/`404` denial
and leave business rows, versions, stock and ledgers unchanged.

## Executed evidence

| ID | User | Resource | Entry | Operation | Expected | Actual | DB changed | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-IDOR-001 | A | Pond B | REST path ID | GET | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-002 | A | Pond B | REST path ID | PATCH, DELETE | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-003 | A | Pond B | REST path ID | submit, verify | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-004 | A | Pond create | JSON `area_id` | foreign-area create | 403/404 | 403/404 | No | PASS |
| SEC-IDOR-005 | A | Attachment B | path ID and query entity ID | metadata, download | 403/404 or empty | 403/404 and empty | No | PASS |
| SEC-IDOR-006 | A | Pond B | export filter `area_id` | export scope | B rows absent | B rows absent | No | PASS |
| SEC-IDOR-007 | A | Fish Batch / Feeding / Inspection | path, query and relation IDs | read, update, status | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-008 | A | Inventory / warehouse documents | warehouse, material, pond and batch foreign IDs | create, verify, ledger read | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-009 | A | Cost entry / asset / settlement | area and source IDs | read, submit, confirm | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-010 | A | Purchase / payable | order, warehouse and payable IDs | read, approve, payment create | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-011 | A | Purchase Return B | source receipt and return ID | read, submit, verify, cancel, delete | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-012 | A | Payment B | payable and payment ID | read, create, verify, reverse | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-013 | A | Sales / receivable | order, pond, batch and receivable IDs | read, approve, foreign relation | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-014 | A | Sales Return B | source delivery and return ID | read, submit, verify, cancel, delete | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-015 | A | Receipt B | receivable and receipt ID | read, create, verify, reverse | 403/404 | `DATA_SCOPE_FORBIDDEN` | No | PASS |
| SEC-IDOR-016 | A | Data Exchange | scope filter and import target IDs | preview, confirm, revoke, export | 403/404 or scoped set | denied or A-only set | No | PASS |
| SEC-IDOR-017 | A | Agent representative tools | foreign record, pond, batch, payable and receivable IDs | read, write, approve, export | backend denial | backend denial with failure audit | No | PASS |

The REST fixture is implemented by
`test_mysql_two_user_rest_idor_matrix`. Production, warehouse, cost, purchase,
sales and data-exchange scope rows are covered by their MySQL integration
tests; the shared return-store guard is regression-tested for both return
kinds, and purchase/sales return state paths are covered by the final
equivalence tests. All users retain the relevant operation permission; the
denial is therefore a DataScope/ownership result rather than an RBAC-only
result.

## Applicability

* Attachment Agent binary upload: `NOT_APPLICABLE`. The Agent Gateway accepts
  JSON tool calls while the upload route requires multipart binary input.
  REST metadata, business-link read and download remain applicable and are
  covered by SEC-IDOR-005.
* Health/Diagnosis and Device: `NOT_APPLICABLE`. The repository has no
  corresponding business table, REST route or Agent tool, so no reachable
  IDOR surface is omitted.

## Conclusion

All applicable rows are `PASS`; no `OPEN`, `UNVERIFIED` or `BLOCKED` IDOR row
remains.

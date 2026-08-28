# R3 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the verified R3 production regressions without weakening tenant isolation or existing API contracts.

**Architecture:** Keep validation at the service/store boundary, add database guards only for invariants that must survive alternate writers, and preserve existing correction-chain and session semantics. Each change gets a focused regression test before implementation.

**Tech Stack:** Python/Flask, MySQL, Vue/TypeScript, pytest.

---

### Task 1: Inventory return correction chain

**Files:** `backend/layers/features/warehouse/warehouse_ledger_store.py`, `backend/tests/test_bug_regressions.py`

- [ ] Add a regression test proving a verified issue whose `source_document_id` points to an issue request still provides its own ledger quantity as the return quota.
- [ ] Resolve the root issue id from the verified issue itself and calculate effective issued minus returned quantities against that id.
- [ ] Run the focused warehouse tests.

### Task 2: Settlement scope and period locking

**Files:** `backend/layers/common/db/repositories/cost_settlement_store.py`, `database/migrations/028_r3_hardening.sql`, `backend/tests/test_cost_enterprise_flow.py`

- [ ] Add overlap detection for farm-wide and area settlements at the same hierarchy level.
- [ ] Make confirmed settlement delivery triggers treat `NULL` area as farm-wide.
- [ ] Add focused tests for duplicate scope and historical delivery rejection.

### Task 3: Lifecycle and session consistency

**Files:** `backend/layers/features/master_data/pond_status_store.py`, `backend/layers/features/production/production_store.py`, `backend/layers/features/warehouse/warehouse_master_store.py`, `backend/layers/features/warehouse/warehouse_ledger_store.py`, `frontend/src/layers/product/auth/PasswordChangePage.vue`, tests

- [ ] Block pond transitions that conflict with stock, active batches, or open production records.
- [ ] Block batch closure until stock and open records are settled.
- [ ] Check target warehouses and open purchase orders during disable, and reject receives into disabled targets.
- [ ] Clear the local session and route to login after password change revokes sessions.

### Task 4: Scope, permissions, import contracts, and bearer sessions

**Files:** `backend/layers/common/db/repositories/mysql_store.py`, `backend/layers/common/security/data_scope.py`, `backend/layers/features/data_exchange/template_catalog.py`, `backend/layers/features/auth/*`, `backend/layers/product/*/routes.py`, tests

- [ ] Separate payable and receivable work-item permissions.
- [ ] Require same-organization assignees for farm-scoped feed tasks.
- [ ] Align official import templates with preview requirements.
- [ ] Accept mobile bearer tokens on authenticated routes.

### Task 5: Verify

- [ ] Run backend tests and frontend type/build checks.
- [ ] Re-scan the audited call chains and report remaining unimplemented product scope explicitly.

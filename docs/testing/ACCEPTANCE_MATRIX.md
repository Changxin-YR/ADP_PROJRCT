# ADP_PROJRCT 第四轮验收矩阵

审查日期：2026-09-09
本地提交：以本轮验收提交为准
测试数据库：Docker disposable MySQL 8.0.46（33080）与 MySQL 8.4（33084）

状态只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_APPLICABLE`。`BLOCKED` 不得提升为 `PASS`，除非重新执行对应门禁并取得证据。

## Backend

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Unit + MySQL 8.0 | PASS | Fresh full run on disposable port 33080: `569 passed`, no skipped tests |
| Unit + MySQL 8.4 | PASS | Fresh full run on disposable port 33084: `569 passed`, no skipped tests |
| Test collection parity | PASS | Fresh `pytest --collect-only -q backend/tests`: both sides collect `569` identical node ids; no difference |
| Coverage >= 85% | PASS | Fresh full run: `85.04370673538477%` (`19,791` statements, `2,960` missing, `96` excluded) |
| 无数据库时的预期 skip | PASS | Disposable MySQL runs explicitly enable the real database adapter; no intentional skip is used as a pass signal |
| Schema/Migration/Seed | PASS | 双版本全量测试均完成隔离库创建、迁移、种子和销毁 |

## Frontend

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Unit | PASS | `117 passed` |
| Production build | PASS | `vue-tsc --noEmit && vite build` exit 0 |
| Playwright E2E | PASS | Fresh split run: regular suite `16 passed` plus W4 suite `18 passed` (`34/34`) |

## Agent

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Route -> Service permission parity | PASS | `171/171` 路由有唯一 Tool；`test_agent_permission_matrix.py` 通过 |
| 工作台摘要权限 | PASS | `/api/v1/workbench/summary` 与 `WorkbenchService.summary()` 均要求 `workbench.enter` |
| Gateway/Registry deterministic Tool execution | PASS | Agent Gateway/Registry 与固定后端 dispatch 测试通过 |
| Live DeepSeek natural-language E2E | PASS (core smoke) | Fresh broad query `5/5` HTTP 200, 3.10–14.61s; tool arguments used `production.list_records` with `uninspected_on=today`. Existing query/write/denial/multi-turn evidence remains valid. |
| Manual/API vs Agent MySQL snapshot equivalence | BLOCKED | Pond, production, inventory and attachment applicability evidence passes; the required 16-module and mixed-operation matrix is incomplete |

## Security

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Prompt injection full matrix | PASS | PI-001..PI-008 executed through DeepSeek -> Gateway; identity, permission and scope stayed unchanged; no unauthorized DB mutation; HTTP/audit/DB evidence used |
| Tool injection / unknown tool / parameter validation | PASS | Registry 固定路径、未知 Tool 拒绝、参数校验测试通过 |
| IDOR / cross-scope HTTP matrix | BLOCKED | Pond service/Agent scope rejection passes; required two-user REST verbs, attachment/download/export and Agent natural-language matrix is incomplete |
| DataScope bypass | PASS | 跨组织、区域、个人范围和导入/附件范围测试通过 |
| Confirmation replay / wrong user / expiry | PASS | 单次消费、身份/会话绑定、过期和取消 deterministic 测试通过 |
| Confirmation DB concurrency | PASS (9.7 regression) | One winner, terminal failure semantics, business/ledger/audit closure and replay rejection pass; 8.0/8.4 rerun remains required |
| Idempotency for Agent high-risk writes | PASS (9.7 regression) | Payment/receipt/inventory/import sequential, concurrent and deterministic commit-then-replay assertions pass; 8.0/8.4 rerun remains required |
| Attachment validation | PASS | MIME、后缀、大小、重复和目标范围测试通过 |
| Agent audit before/after and failure | PASS (representative classes) | Shared Gateway pipeline reconstructs request/permission/scope/confirmation/before/after and failure traces; 8.0/8.4 rerun remains required |

## Four Gates

| 门禁 | 结果 | 原因 |
| --- | --- | --- |
| Gate 1 Management | PASS | Backend 569/569 on MySQL 8.0 and 8.4, coverage 85.04370673538477%, frontend unit/build/E2E pass |
| Gate 2 Agent | PASS (core smoke) | LIVE-006 broad query is now fresh `5/5` under the 75s timeout; full gate still depends on the explicitly listed acceptance gaps |
| Gate 3 Authorization & Security | FAIL | PI-001..PI-008, Tool Injection and DataScope pass; full IDOR, confirmation side effects, financial/inventory idempotency and audit closure remain incomplete |
| Gate 4 Business Equivalence | FAIL | pond snapshot PASS；完整 16 模块业务等价矩阵未完成 |

## Bugs / Gaps

| 级别 | 项目 | 状态 |
| --- | --- | --- |
| P0 | 当前已发现业务代码故障 | 0 |
| P1 | 人工/Agent 全业务 MySQL 等价性 | OPEN（pond 场景 PASS） |
| P1 | 完整 Agent 安全攻击矩阵与确认并发 | PI-001..PI-008 live PASS; IDOR/confirmation side-effect/idempotency/audit matrices incomplete |
| P1 | Live DeepSeek provider E2E | FIXED; broad query now returns in 3.10–14.61s across five real calls |
| P1 | Coverage threshold | PASS at `85.04370673538477%`; below the preferred `86%` buffer but above the delivery gate |

## Final Rating

`C`：Gate 1 已通过，LIVE-006 已修复并完成 5/5 真实回归；Gate 3 的完整双用户安全证据和 Gate 4 的 16 模块/混合业务等价矩阵仍未完成。

# ADP_PROJRCT 第三轮验收矩阵

审查日期：2026-09-08  
本地提交：以本轮验收提交为准
测试数据库：Docker disposable MySQL 8.0.46（33080）与 MySQL 8.4（33084）

状态只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_APPLICABLE`。`BLOCKED` 不得提升为 `PASS`，除非重新执行对应门禁并取得证据。

## Backend

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Unit + MySQL 8.0 | PASS | `533 passed, 0 failed, 0 skipped` |
| Unit + MySQL 8.4 | PASS | `534 passed, 0 failed, 0 skipped` |
| Coverage >= 85% | FAIL | fresh MySQL 8.0 `--cov=backend` 总覆盖率 `82.42%` (`533 passed`, gate remains unmet) |
| 无数据库时的预期 skip | PASS | `40 skipped` 全部为 disposable MySQL/真实注册适配器；无意外 skip |
| Schema/Migration/Seed | PASS | 双版本全量测试均完成隔离库创建、迁移、种子和销毁 |

## Frontend

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Unit | PASS | `117 passed` |
| Production build | PASS | `vue-tsc --noEmit && vite build` exit 0 |
| Playwright E2E | PASS | `34 passed` |

## Agent

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Route -> Service permission parity | PASS | `171/171` 路由有唯一 Tool；`test_agent_permission_matrix.py` 通过 |
| 工作台摘要权限 | PASS | `/api/v1/workbench/summary` 与 `WorkbenchService.summary()` 均要求 `workbench.enter` |
| Gateway/Registry deterministic Tool execution | PASS | Agent Gateway/Registry 与固定后端 dispatch 测试通过 |
| Live DeepSeek natural-language E2E | FAIL_AGENT_RESPONSE | Machine-scope key configured; real query, write/confirmation, permission denial and multi-turn passed. One broad query exceeded the 75s client timeout. |
| Manual/API vs Agent MySQL snapshot equivalence | FAIL | Pond create snapshot passes; the required 16-module and mixed-operation matrix is incomplete |

## Security

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Prompt injection full matrix | PASS | PI-001..PI-008 executed through DeepSeek -> Gateway; identity, permission and scope stayed unchanged; no unauthorized DB mutation; HTTP/audit/DB evidence used |
| Tool injection / unknown tool / parameter validation | PASS | Registry 固定路径、未知 Tool 拒绝、参数校验测试通过 |
| IDOR / cross-scope HTTP matrix | FAIL | Pond service/MySQL scope rejection passes; required REST verbs, attachment/export and Agent natural-language matrix is incomplete |
| DataScope bypass | PASS | 跨组织、区域、个人范围和导入/附件范围测试通过 |
| Confirmation replay / wrong user / expiry | PASS | 单次消费、身份/会话绑定、过期和取消 deterministic 测试通过 |
| Confirmation DB concurrency | FAIL | 20 concurrent claims yield one winner on MySQL 8.0/8.4, but business row/ledger/audit exactly-once was not proven |
| Idempotency for Agent high-risk writes | FAIL | Generic operation invocation is exactly once, but payment/receipt/inventory/data-import side effects were not covered |
| Attachment validation | PASS | MIME、后缀、大小、重复和目标范围测试通过 |
| Agent audit before/after and failure | FAIL | Logger persistence and live gateway failure audit pass; actual Agent business write trace lacks the full required instruction/intent/before/after assertion |

## Four Gates

| 门禁 | 结果 | 原因 |
| --- | --- | --- |
| Gate 1 Management | FAIL | 覆盖率 `82% < 85%` |
| Gate 2 Agent | PASS | deterministic Gateway -> Tool -> fixed Backend dispatch and live DeepSeek tool selection passed; one broad query has `FAIL_AGENT_RESPONSE` |
| Gate 3 Authorization & Security | FAIL | PI-001..PI-008, Tool Injection and DataScope pass; full IDOR, confirmation side effects, financial/inventory idempotency and audit closure remain incomplete |
| Gate 4 Business Equivalence | FAIL | pond snapshot PASS；完整 16 模块业务等价矩阵未完成 |

## Bugs / Gaps

| 级别 | 项目 | 状态 |
| --- | --- | --- |
| P0 | 当前已发现业务代码故障 | 0 |
| P1 | 人工/Agent 全业务 MySQL 等价性 | OPEN（pond 场景 PASS） |
| P1 | 完整 Agent 安全攻击矩阵与确认并发 | PI-001..PI-008 live PASS; IDOR/confirmation side-effect/idempotency/audit matrices incomplete |
| P1 | Live DeepSeek provider E2E | FAIL_AGENT_RESPONSE（broad query client timeout） |
| P2 | Coverage threshold | FAIL（82.42%） |

## Final Rating

`C`：确定性 Agent、安全和 pond 业务等价证据已通过；coverage、完整 16 模块等价矩阵仍未完成，且 Live Agent 有一项 `FAIL_AGENT_RESPONSE`。

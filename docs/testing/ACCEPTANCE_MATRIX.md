# ADP_PROJRCT 第二轮验收矩阵

审查日期：2026-09-08  
本地提交：`722f2c2f5a95eba653b51422ca616fa3c2388700`（包含本轮修正）  
测试数据库：Docker disposable MySQL 8.0.46（33080）与 MySQL 8.4（33084）

状态只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_APPLICABLE`。`BLOCKED` 不得提升为 `PASS`，除非重新执行对应门禁并取得证据。

## Backend

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Unit + MySQL 8.0 | PASS | `528 passed, 0 failed, 0 skipped` |
| Unit + MySQL 8.4 | PASS | `528 passed, 0 failed, 0 skipped` |
| Coverage >= 85% | FAIL | fresh `--cov=backend` 总覆盖率 `82.29%` |
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
| Live DeepSeek natural-language E2E | BLOCKED | 当前环境未配置 `DEEPSEEK_API_KEY`/真实 Harness provider |
| Manual/API vs Agent MySQL snapshot equivalence | BLOCKED | 尚未建立同一 `S0` 下的人工、Agent、混合操作快照比较 harness |

## Security

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Prompt injection full matrix | BLOCKED | 身份来自 Session 的 deterministic 测试通过；完整自然语言攻击矩阵未在真实模型上执行 |
| Tool injection / unknown tool / parameter validation | PASS | Registry 固定路径、未知 Tool 拒绝、参数校验测试通过 |
| IDOR / cross-scope HTTP matrix | BLOCKED | Service/MySQL DataScope 回归通过；尚缺双用户 Agent HTTP 全矩阵证据 |
| DataScope bypass | PASS | 跨组织、区域、个人范围和导入/附件范围测试通过 |
| Confirmation replay / wrong user / expiry | PASS | 单次消费、身份/会话绑定、过期和取消 deterministic 测试通过 |
| Confirmation DB concurrency | BLOCKED | 尚未在真实 MySQL 上并发消费同一 Agent confirmation |
| Idempotency for Agent high-risk writes | BLOCKED | 通用幂等与业务付款/收款测试通过；Agent 同一 request_id 并发证据缺失 |
| Attachment validation | PASS | MIME、后缀、大小、重复和目标范围测试通过 |
| Agent audit full reconstruction | BLOCKED | 审计基础存在，但 instruction -> intent -> tool -> before/after 全链自动断言尚未完成 |

## Four Gates

| 门禁 | 结果 | 原因 |
| --- | --- | --- |
| Gate 1 Management | FAIL | 覆盖率 `82.29% < 85%` |
| Gate 2 Agent | PASS | deterministic Gateway -> Tool -> fixed Backend dispatch 已通过；Live DeepSeek 另列 BLOCKED |
| Gate 3 Authorization & Security | BLOCKED | 权限矩阵和 DataScope 通过，但完整攻击矩阵/确认并发仍缺证据 |
| Gate 4 Business Equivalence | BLOCKED | 缺少真实 MySQL 人工/Agent/混合快照相等证明 |

## Bugs / Gaps

| 级别 | 项目 | 状态 |
| --- | --- | --- |
| P0 | 当前已发现业务代码故障 | 0 |
| P1 | 人工/Agent 全业务 MySQL 等价性 | BLOCKED |
| P1 | 完整 Agent 安全攻击矩阵与确认并发 | BLOCKED |
| P1 | Live DeepSeek provider E2E | BLOCKED_EXTERNAL_CREDENTIAL |
| P2 | Coverage threshold | FAIL（82.29%） |

## Final Rating

`C`：权限映射本轮已修正并由 171 条路由矩阵证明，但覆盖率门禁失败，且真实 DeepSeek、完整攻击矩阵和人工/Agent 数据库等价性仍未完成。

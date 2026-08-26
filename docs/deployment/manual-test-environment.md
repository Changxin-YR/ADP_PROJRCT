# ADP 独立人工测试环境运行手册

## 1. 适用范围

本手册用于在网站二上执行企业级人工验收。测试环境使用独立发布目录、独立服务、独立数据库、独立 MySQL 账号、独立附件目录和固定测试编号。正式数据库不写入测试数据。

当前固定资源如下：

| 项目 | 值 |
| --- | --- |
| 正式入口 | `https://1.14.148.15/production` |
| 测试入口 | `https://1.14.148.15/test` |
| API 文档 | `https://1.14.148.15/api-docs/` |
| 正式后端 | `127.0.0.1:5002` |
| 测试后端 | `127.0.0.1:5003` |
| 测试数据库 | `adp_manual_test_20260817` |
| 测试附件 | `/var/lib/adp/manual-test-20260817/attachments` |
| 测试运行配置 | `/etc/adp/manual-test.env`，权限 `0600` |
| 测试登录凭据 | `/etc/adp/manual-test-credentials.env`，权限 `0600` |

测试环境只有在执行云端安装并完成健康检查后才可使用。源码和本地门禁完成不等于云端已经安装。

## 2. 隔离规则

Nginx 根据安全 Cookie `adp_environment` 同时选择前端发布目录和 API 上游。没有 Cookie 或 Cookie 值无效时，始终使用正式前端和正式后端 `5002`；只有访问 `/test` 写入 `test` 后才使用测试前端和测试后端 `5003`。

两个环境共用浏览器域名，环境切换会清除登录 Cookie 并跳转登录页。测试环境和正式环境不能在同一浏览器会话中同时登录，切换后必须重新登录。

测试后端使用专用 MySQL 账号 `adp_manual_test_20260817`，该账号只被授予测试数据库权限。正式应用数据库账号不会写入测试服务配置。

## 3. 测试账号

所有测试账号共用安装时随机生成的临时密码。密码不进入 Git、Nginx、systemd 日志或造数清单。服务器管理员可在交付时读取一次：

```bash
sudo cat /etc/adp/manual-test-credentials.env
```

| 登录名 | 角色 | 重点验收范围 |
| --- | --- | --- |
| `test-admin` | 超级管理员 | 账号、角色权限、审计、全局待办 |
| `test-breed-manager` | 养殖管理员 | 主数据、生产核验、塘口状态、成本确认 |
| `test-breed-worker` | 养殖作业员 | 巡塘、抽样、投喂、领料和生产草稿 |
| `test-warehouse` | 仓储管理员 | 入库、出库、库存、批次和预警 |
| `test-purchaser` | 采购人员 | 供应商、采购单和应付查看 |
| `test-finance` | 财务人员 | 付款、收款、费用、资产、分摊和结算 |
| `test-sales` | 销售人员 | 客户、销售订单、交付和应收查看 |

## 4. 预置数据

测试主数据统一使用 `TEST-20260817-` 前缀，包括一个测试企业、一个养殖场、两个区域、四个塘口、四类物料、一个供应商、一个客户和一个仓库。

业务数据覆盖以下状态和链路：

- 生产、仓储记录包含草稿、已提交、已核验和更正草稿。
- 采购、销售订单包含草稿、已提交和已审批。
- 采购入库形成应付，付款包含有效核验付款和付款冲销。
- 销售出塘与交付形成应收，收款包含有效核验收款和收款冲销。
- 费用包含草稿、已提交、已核验和已确认；资产包含已核验凭据。
- 分摊、结算和反结算均有数据，分摊金额与明细一致。
- 待核验记录保留开放待办；核验完成记录只保留完成历史，不再出现在开放待办。
- 审计日志、通知和真实 SHA-256 文本凭据可供查询。

造数脚本可重复执行。固定业务编号存在时不会再插入第二套数据。

## 5. 企业生命周期验收

对每个业务域至少执行一次下列流程：

1. 新建草稿并保存，确认草稿可编辑、可删除。
2. 提交记录，确认已提交记录仍可修改；修改后版本号变化，旧版本请求返回冲突。
3. 使用不同角色执行核验或审批，确认经办人不能核验自己的记录。
4. 核验完成后确认页面只读，编辑和删除按钮不可用。
5. 直接调用修改或删除 API，确认后端拒绝；直接执行数据库修改时，确认不可变触发器拒绝。
6. 对已核验错误数据创建更正、冲销或反结算，不改写原记录。
7. 确认开放待办已消失，完成历史、审计前后值和凭据仍可追溯。

正式业务原则：只有无业务引用的草稿可物理删除；已提交和已核验数据不提供物理删除。已核验数据永久只读，后续变化通过关联的反向记录表达。

## 6. 安装与健康检查

仅服务器 root 在当前发布目录执行：

```bash
bash deploy/install-manual-test.sh adp_manual_test_20260817
```

安装顺序为：正式服务健康检查、正式库行数和 14 类对账快照、创建隔离库和账号、执行迁移、初始化字典、造数、测试库对账、启动 `5003`、验证测试服务、原子切换 Nginx、验证正式与测试分流、复核正式库无变化。

分流检查：

```bash
curl --fail --silent https://1.14.148.15/api/v1/health
curl --fail --silent --cookie 'adp_environment=test' https://1.14.148.15/api/v1/health
```

第一条必须返回 `environment=production`，第二条必须返回 `environment=test`。任一结果不符时不得开始人工测试。

## 7. 正式数据保护检查

安装证据保存在 `/var/lib/adp/manual-test-20260817`：

- `production-before.rows` 与 `production-after.rows` 必须完全一致。
- `production-before-reconciliation.json` 与 `production-after-reconciliation.json` 必须完全一致，且 `total_issues` 为 `0`。
- `test-reconciliation.json` 的 14 类检查必须全部为 `0`。
- `seed-manifest.json` 只包含数据清单，不得包含数据库密码或测试登录密码。

正式库、正式附件、正式备份和正式审计证据不属于测试清理范围。

## 8. 故障定位

```bash
sudo systemctl status adp-manual-test
sudo journalctl -u adp-manual-test --since today
sudo nginx -t
sudo cat /var/lib/adp/manual-test-20260817/test-reconciliation.json
```

若清理脚本提示 Nginx 配置在测试安装后发生变化，说明期间出现了新的正式发布或人工配置变更。此时脚本会拒绝覆盖当前配置，应先由运维确认最新正式配置，不能绕过指纹保护。

## 9. 测试结束与清理

只有用户明确说“测试结束”后，才允许执行：

```bash
bash deploy/remove-manual-test.sh adp_manual_test_20260817 DELETE_MANUAL_TEST_ENVIRONMENT
```

清理脚本先恢复测试安装前的 Nginx 配置并验证正式 `5002`，然后停止测试服务，删除固定测试数据库、测试数据库账号、测试附件和测试凭据。它不会删除正式数据库、正式发布目录、正式附件、正式备份或正式审计记录。

## 10. 2026-08-17 云端部署证据

部署完成时间：`2026-08-17T15:17:32+0800`。

| 项目 | 实际结果 |
| --- | --- |
| 源码提交 | `62a4c385fdc76da29afa31cabbd357ebf16b1c3f` |
| 发布包 SHA-256 | `cc81d7cff906aff44a3aa27a98d7b48565dbf5753e5d4d55f2cfc01b6f1521cb` |
| 测试源码 | `/opt/adp/releases/manual-test-20260817-62a4c38` |
| 正式运行时 | `/opt/adp/releases/20260817-732c247ecde1`，未覆盖 |
| 测试服务 | `adp-manual-test`，`active/running`，监听 `127.0.0.1:5003` |
| 敏感配置权限 | 两个环境文件均为 `0600 root:root` |

独立验收结果：

- 默认公网健康检查返回 `environment=production`；携带 `adp_environment=test` 返回 `environment=test`。
- `/test` 写入测试 Cookie 并跳转登录页；`/production` 清除环境和登录 Cookie。
- 正式库部署前后行数快照逐字节一致，正式库部署前后 14 类对账文件逐字节一致。
- 测试库在生命周期验收和待办版本修复后重新执行 14 类对账，`total_issues=0`。
- 七个账号均可登录、状态为 `active`、只有一个测试养殖场数据范围且可进入工作台。
- 账号管理接口仅 `test-admin` 返回 `200`，其余六个账号返回 `403`；成本接口仅超级管理员、养殖管理员和财务人员返回 `200`。
- 已提交生产记录可编辑，版本由 `1` 增至 `2`；旧版本写入返回 `409 VERSION_CONFLICT`，对应开放待办同步到版本 `2`。
- 已核验生产记录编辑返回 `409 RECORD_READ_ONLY`；已提交和已核验记录删除均返回 `409 DELETE_NOT_ALLOWED`；无引用草稿可删除且删除后查询为 `404`。
- 绕过 API 直接修改已核验记录时，数据库返回 `verified production document is immutable`；直接删除已提交或已核验记录时返回 `formal production document cannot be deleted`。
- 七个凭据附件的数据库 SHA-256 与服务器文件摘要一致。
- 应用内浏览器检查登录页无横向溢出、无可见控件越界，控制台无警告或错误。

测试环境继续保留。只有用户明确说“测试结束”后才执行第 9 节清理命令。

## 11. 2026-08-18 塘口新增修复验收

本次测试发布只更新隔离测试环境，正式入口和正式数据库未切换：

| 项目 | 实际结果 |
| --- | --- |
| 源码提交 | `98676c9` |
| 测试源码 | `/opt/adp/releases/manual-test-20260818-98676c9` |
| 测试 API | `127.0.0.1:5003`，`adp-manual-test` 为 `active` |
| 测试前端 | Nginx 仅对 `adp_environment=test` 使用本次测试发布目录 |
| 正式前端 | `/opt/adp/releases/20260817-732c247ecde1/frontend/dist`，摘要未变化 |

验收结果：

- 使用测试管理员新增塘口返回 `201`，记录为 `draft`、版本 `1`；不存在的分组 ID 返回 `400 MASTER_RELATION_NOT_FOUND`，不再返回 `500`。
- 塘口新增页面改为加载已核验区域和分组下拉选项，分组按所属区域过滤；没有分组时可选择“不分组”。
- 提交后由同一账号编辑并核验生产抽样时，核验返回 `403 SELF_APPROVAL_FORBIDDEN`；更换核验账号后返回 `200`。
- 新服务发布后未出现未处理异常；正式和测试健康检查分别返回 `environment=production` 与 `environment=test`。

当前测试库对账仍有 1 条历史人工测试数据的 `self_approval`，对应既有生产记录 `production_documents.id=2`，本次未自动修改或删除，待用户明确结束测试后按测试环境清理流程处理。

## 12. 2026-08-21 无效指派用户修复回归

本次仅更新隔离测试服务，正式入口和正式数据库未切换：

| 项目 | 实际结果 |
| --- | --- |
| 源码提交 | `d543332` |
| 测试源码 | `/opt/adp/releases/manual-test-20260821-d543332` |
| 测试服务 | `adp-manual-test` active，监听 `127.0.0.1:5003` |
| 正式服务 | 未重启，仍使用现有生产 release |

回归结果：测试管理员登录 HTTP 200，塘口读取 HTTP 200；向 `/api/v1/production/feed-tasks` 提交不存在的 `assigned_user_id` 返回 HTTP 400、`FEED_TASK_ASSIGNEE_INVALID`，不再返回数据库外键 500。探针使用服务器临时会话并在退出时清理，没有保存密码、Cookie 或 Token。

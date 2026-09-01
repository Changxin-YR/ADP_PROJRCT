# Bug 修复记录

## BUG-ACC-001 主数据基地范围过滤失效

- 严重等级：P1
- 现象：财务人员具有有效 `farm_id` 数据范围时，`GET /api/v1/master-data/ponds` 返回空列表。
- 复现：`acceptance_finance` 登录后查询塘口，修复前范围条件退化为 `1=0`。
- 根因：`MySqlMasterDataStore._scope_filter()` 仅实现区域和个人范围，未处理基地范围；生产、仓储、采购、销售模块已使用的通用范围谓词未在主数据同构表中复用。
- 修改文件：
  - `backend/layers/features/master_data/master_data_store.py`
  - `backend/tests/test_bug_regressions.py`
- 修复方式：对除基地、区域外的同构主数据资源复用 `scope_predicate()`，沿用其基地、区域、企业与个人组合范围语义。
- 回归：新增基地范围回归用例先失败后通过；两轮后端全量各 487 通过；线上财务角色查询塘口为 6 条，应付为 1 条，账号管理 POST 为 403。

## BUG-ACC-002 交付播种器首次运行依赖顺序错误

- 严重等级：P1
- 现象：交付播种器首次运行时在采购入库生成库存批次前查询该批次，导致首次播种失败。
- 根因：`context()` 提前读取 `inventory_lots`，而该对象由后续采购入库流程创建。
- 修改文件：
  - `tools/seed_production_delivery.py`
  - `tools/tests/test_seed_production_delivery.py`
- 修复方式：将库存批次查询移至领料与库存单据实际使用前。
- 回归：新增测试验证 `context()` 不查询未创建的库存批次；播种重复运行保持幂等；生产验收数据对账 `total_issues=0`。

## BUG-ACC-003 至 BUG-ACC-009 企业验收门禁跨环境兼容性缺陷

- 严重等级：P1
- 现象：Windows PowerShell 的企业验收门禁在读取 UTF-8 报告、存在既有验收证据、后端 pytest 失败、非默认 MySQL 端口、加载 SQL 迁移、迁移登记、参考种子和云端对账命令中可能误报、漏报或执行失败。
- 根因：`tools/final_enterprise_acceptance.ps1` 对 PowerShell 管道行为、MySQL 输入方式、迁移元数据和 SSH 远端 shell 变量的边界处理不完整。
- 修改文件：
  - `tools/final_enterprise_acceptance.ps1`
  - `backend/tests/test_final_acceptance_contract.py`
- 修复方式：显式按 UTF-8 读取报告；放行既有验收证据目录；在捕获 pytest 输出时保留退出码；复用传入的 MySQL 端口；以字节重定向加载 UTF-8 SQL；登记迁移 checksum 并加载参考种子；将远端对账脚本 Base64 编码后交给 Bash 执行，避免 PowerShell 提前展开 Bash 变量。
- 回归：每项均有契约测试覆盖（`2 passed`）；完整企业验收门禁连续两轮输出 `FINAL_ENTERPRISE_ACCEPTANCE=PASS release=20260901-6a19a2c-r17`。

## BUG-ACC-010 移动 App 核心业务与生产连接缺失

- 严重等级：P0，未修复，正式交付阻塞。
- 现象：`mobile/App.tsx` 仅为单页工作台，只请求 `/api/v1/workbench/summary`；默认 API 为 `http://127.0.0.1:5000`。
- 影响：不具备需求文档要求的登录会话、角色权限、塘口、投喂、仓储、采购、销售、成本、消息和离线同步等业务闭环，真实手机也无法访问本机 HTTP 地址。
- 复现：静态审查 `mobile/App.tsx`；TypeScript 语法检查为 `MOBILE_TS_SYNTAX_ERRORS=0`，证明文件可解析但不证明业务实现或真机可用。
- 处置：未进行伪修复。需要完成对应移动端实现、生产 HTTPS API 配置、Expo 构建与真机全链路回归后才能关闭。

## BUG-ACC-011 微信小程序核心业务与生产连接缺失

- 严重等级：P0，未修复，正式交付阻塞。
- 现象：`miniprogram/app.json` 仅声明 `pages/workbench/workbench`，`app.js` 默认 API 为 `http://127.0.0.1:5000`。
- 影响：不具备登录、现场作业、物料领退、消息、历史、离线处理和同步等需求能力；未配置生产 HTTPS 合法域名，真实微信客户端无法访问本机 HTTP 后端。
- 复现：JSON 与 JavaScript 静态校验通过；本机未发现微信开发者工具 CLI，不能完成官方编译或真机验证。
- 处置：未进行伪修复。需要完成小程序业务实现、认证授权、生产 HTTPS 合法域名配置、开发者工具构建和真机回归后才能关闭。

## 回归与发布

- 后端全量回归：两轮各 `487 passed`。
- 前端单测：两轮各 `114 passed`。
- 前端 E2E：两轮各 `34 passed`。
- 生产发布：`20260901-6a19a2c-r17`。
- 发布后：双服务 active、Nginx 校验通过、公网核心地址均为 200、生产对账 `total_issues=0`。
- 结论：上述结果仅证明 Web、后端、数据库与生产部署通过。BUG-ACC-010 与 BUG-ACC-011 为未关闭 P0，整体三端正式交付结论为 **B：未达到正式交付标准**。

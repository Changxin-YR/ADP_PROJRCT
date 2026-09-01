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

## 回归与发布

- 后端全量回归：两轮各 `487 passed`。
- 前端单测：两轮各 `114 passed`。
- 前端 E2E：两轮各 `34 passed`。
- 生产发布：`20260901-6a19a2c-r17`。
- 发布后：双服务 active、Nginx 校验通过、公网核心地址均为 200、生产对账 `total_issues=0`。


# ADP 企业级人工 UAT 记录（真实产品网站复测）

- 测试日期：2026-08-26
- 测试环境：`https://1.14.148.15/`（真实产品入口；登录后进入真实业务页面）
- 执行方式：真实浏览器页面登录、点击、直链、筛选、表单查看与手机视口；未调用业务 API 伪造结果
- 密码记录：不保存明文，仅标记默认/备用

## 复测结果

| 用例 | 角色/账号 | 操作 | 实际结果 | 结论 |
| --- | --- | --- | --- | --- |
| LOGIN-016-R2 | 尾号 16 | 默认、备用密码各登录一次 | 两次均回到登录页并提示“登录标识或密码错误” | FAIL，待重置链复现 |
| FIRST-PASSWORD-018-R2 | 尾号 18 | 使用默认密码登录 | 进入 `/auth/first-password`；页面仅有三个密码框和“保存新密码”，无退出/返回/切换账号 | FAIL，复现 BUG-FIRST-PASSWORD-EXIT-001 |
| USER-LIST-001-R2 | 超级管理员 | 打开账号管理并滚动 | 当前共渲染 20 个账号（19 个测试账号 + 1 个历史账号），无分页/加载更多；当前数据恰好 20 条，未人为新增第 21 条 | LIMIT CONFIRMED；超过 20 条仍存在不可见风险 |
| HELP-ROLE-001-R2 | 管理员、销售南区、养殖作业南区 | 分别打开“使用帮助” | 三个角色帮助正文逐字相同，包含无权限模块说明 | FAIL，复现 BUG-HELP-ROLE-001 |
| PERM-WORKER-URL-001-R2 | 养殖作业南区 | 直链 `/admin/users`、`/cost/structure`、`/purchase/orders`、`/admin/logs` | 均重定向 `/workbench` | PASS |
| SCOPE-WORKER-POND-001-R2 | 养殖作业南区 | 打开塘口档案 | 只显示 1 个授权塘口（TEST_B01，南区范围） | PASS |
| WAREHOUSE-OPTION-001-R2 | 超级管理员 | 打开入库登记表单 | “仓库”下拉只有“请选择仓库”；物料下拉有 TEST_FEED_001 | FAIL，复现 BUG-WAREHOUSE-MASTER-BLOCKER-001（P0） |
| PURCHASE-WAREHOUSE-001-R2 | 超级管理员 | 打开新建采购单 | “收货仓”下拉只有“请选择收货仓”；供应商和物料均有选项 | FAIL，同一 P0 阻断采购→入库→应付链 |
| MOBILE-390-001-R2 | 养殖作业南区 | 390×844 手机视口打开工作台 | `scrollWidth=390`、`innerWidth=390`，无横向溢出，工作台和菜单可见 | PASS |

## 证据

- `REAL-ADMIN-USER-LIST-001.png`
- `REAL-PURCHASE-WAREHOUSE-BLOCK-001.png`
- `REAL-MOBILE-WORKBENCH-390-001.png`
- 上一轮帮助与列表证据见 `UAT-ROUND-1.md` 及同目录 `HELP-*.png`、`BUG-USER-LIMIT-001-hidden-search.png`。

## 未执行项

- `BUG-RESET-PASSWORD-001`：已在管理员页面确认按钮会弹出原生临时密码输入提示；未输入或提交新密码，因此没有改变尾号 16 的凭据。要完成“重置后新旧密码分别登录”复现，需要用户在提交临时密码前明确确认测试密码。
- 采购、仓储、销售、付款、收款、成本等正式闭环：被无可选仓库和待核验批次阻断，继续造数会绕过真实前置条件。

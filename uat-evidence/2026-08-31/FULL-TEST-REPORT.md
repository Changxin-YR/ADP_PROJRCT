# ADP 站点全量测试报告

- 测试时间：2026-08-31（Asia/Shanghai）
- 目标：`https://1.14.148.15/`
- 测试方式：真实 Chrome CDP 会话、真实页面点击、页面网络请求记录、仓库自动化测试
- 数据安全：未执行创建、提交、审批、核验、删除、停用、注销、密码重置等写操作；未保存密码、Cookie、Token 或附件内容。

## 结论

站点可访问，生产健康接口正常，超级管理员会话可进入业务页面。不能判定“全部功能正常”：工作台相关接口存在可重复的后端故障，且此前 UAT 已确认仓库主数据缺失会阻断采购/入库链路。本轮未改变业务数据。

## 自动化回归

| 套件 | 结果 |
| --- | --- |
| Backend pytest | `452 passed, 39 skipped` |
| Frontend Vitest | `19 files, 112 passed` |
| Frontend Playwright | `34 passed` |

原始输出：`backend-pytest.txt`、`frontend-vitest.txt`、`frontend-playwright.txt`。

## 真实站点检查

- `GET /api/v1/health`：HTTP `200`，`environment=production`。
- `GET /api/v1/auth/csrf`：HTTP `200`。
- 未登录访问 `/api/v1/auth/me`、`/api/v1/workbench/summary`、`/api/v1/work-items`：均按预期 HTTP `401 UNAUTHENTICATED`。
- 已登录超级管理员可渲染并访问生产、仓储、采购、销售、成本、数据交换、系统管理页面；主要页面数据请求大多 HTTP `200`。
- 41 个已登录业务/系统路由已逐页访问；23 个主要新增/登记入口真实点击后均打开表单，表单含取消/保存控件，未提交。
- 管理员账号、角色、审计日志、业务参数页面可打开；审计日志可读取历史记录。
- 响应式与交互自动化覆盖 320/360/375/390/414/768/1024/1920 宽度，全部通过。

## 已确认问题

### P1：`/test` 入口出现空白页面

直接打开 `https://1.14.148.15/test` 时，标题仍为“ADP 登录注册”，但 `#app` 为空、正文无业务内容；截图见 `initial.png`。生产入口可正常渲染。测试环境分流或测试前端启动状态需要运维复核。

### P1：工作台待办接口稳定返回 400

已登录请求 `/api/v1/work-items`（包括省略参数、`page=1&page_size=10/20/50/100`、`include_history=true/false`）均返回 HTTP `400`，错误为 `VALIDATION_ERROR` / `分页参数无效`。前端所有业务页的壳层都会调用该接口，因此页面反复出现工作项加载失败提示。证据：`routes-01.json` 至 `routes-04b.json`、`api-work-items-probes.json`（见同目录请求记录）。

### P1：工作台摘要接口返回 500

已登录请求 `/api/v1/workbench/summary` 返回 HTTP `500 INTERNAL_ERROR`，工作台显示“服务器暂时无法处理请求”。证据：`routes-01.json` 和页面网络记录。

### P0（历史 UAT，仍需复核）：仓库主数据缺失阻断采购/入库

上一轮真实站点复测记录“仓库”下拉只有“请选择仓库”，采购收货仓同样无可选项，采购→入库→应付链无法继续。详见 [`UAT-ROUND-2-REAL-WEBSITE.md`](../2026-08-26/UAT-ROUND-2-REAL-WEBSITE.md)。本轮未造数绕过前置条件。

### 既有待复核项

此前 UAT 还记录了尾号 16 登录凭据异常、首次改密页缺少退出/切换入口、帮助正文未按角色区分、账号列表无分页等问题；本轮没有使用未知密码重试，也没有执行密码重置。

## 证据文件

- `initial.png`
- `routes-01.json`、`routes-02*.json`、`routes-03*.json`、`routes-04*.json`、`routes-admin-warehouse.json`
- `button-clicks-01.json`、`button-clicks-02*.json`、`button-clicks-03*.json`、`button-clicks-04*.json`
- `api-public-probes.json`、`api-unauth-probes.txt`
- `backend-pytest.txt`、`frontend-vitest.txt`、`frontend-playwright.txt`

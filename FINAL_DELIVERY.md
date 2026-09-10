# FINAL_DELIVERY — ADP 鱼塘养殖喂养日常管理系统（Web 正式交付）

> ## ⚠️ 当前状态（2026-09-10 更新，优先于下文历史章节）
>
> 系统入口已从 **IP 直连** 迁移到 **共享域名**，下文第 4 节的网址已失效：
>
> | 项目 | 当前值 |
> | --- | --- |
> | 正式入口 | `https://23331.cloud/adp/` |
> | API 基址 | `https://23331.cloud/adp/api/v1` |
> | API 文档 | `https://23331.cloud/adp/api-docs/` |
> | 健康检查 | `https://23331.cloud/adp/api/v1/health` |
> | 线上 release | `/opt/adp/releases/20260910-domain-a94d17d-r4` |
> | 回滚目标 | `/opt/adp/releases/20260909-a94d17d-r3` |
> | 域名 | `23331.cloud`（A 记录 → `1.14.148.15`，与 SSH 目标同一台机器） |
>
> 旧的 `https://1.14.148.15/production`、`/test` 与 IP 直连**均已下线**：IP 不等于
> `ADP_SERVER_NAME`，请求会被 Nginx 直接断开。`1.14.148.15` 现在只用作 SSH 目标。
>
> 同一台服务器为共享主机：`23331.cloud` 根路径 302 跳到 `/adp/`；物业项目在
> `https://www.23331.cloud/wuye/`。
>
> 下文第 4/6 节中的发布号、归档 SHA 与 `/production` 网址属于 2026-08-24 那次交付的
> 历史记录，保留原样以便追溯，**不代表当前线上状态**。

## 1. 最终源码版本与判断依据
- 本地正式源码目录：`C:\Users\27363\Desktop\ADP`
- 与云端当前正式 release 对比：源码文件清单（排除 node_modules/dist/.venv/__pycache__/缓存/日志/密钥等）**400/400 个文件哈希完全一致**。
- 因此以本地 ADP 为唯一最新正式源码继续修改，未混入任何其他版本。
- 本次修改前本地基线对应云端 release：`20260824-0d4812950a08`。

## 2. 本次实际修改文件及原因
- `frontend/src/layers/product/admin/UserManagementPage.vue`
  - 账号行三个区域增加语义类名：`user-identity` / `user-meta` / `user-actions`（行为等价，纯结构语义化）。
- `frontend/src/styles/auth.css`
  - 账号列表由 flex+space-between 改为桌面三列 CSS Grid（身份列 / 状态角色范围列 / 操作列），中间列所有行起点对齐；
  - 操作按钮右对齐、允许换行；≤900px 操作区占下一行；≤780px 单列；保留原有配色、字体、按钮与交互。
- `frontend/tests/e2e/user-management-layout.spec.ts`
  - 新增：桌面三列与第二列起点一致、中等屏幕操作区换行、手机端单列无横向溢出（覆盖长姓名/登录账号/未分配角色/停用/注销状态渲染）。

## 3. 测试结果
- `python tools/audit_source.py --root . --strict`：10 blueprints / 48 路由 / 689 项危险删除类代码点已审计（无阻断）。
- `python -m pytest -q backend/tests -rs`：**358 passed, 39 skipped**。
- `npm --prefix frontend ci`：完成。
- `npm --prefix frontend run test:unit -- --run`：**102 passed**。
- `npm --prefix frontend run build`：通过。
- `npm --prefix frontend run test:e2e`：**34 passed**（含新增 2 项布局回归）。

## 4. 云端发布号 / 归档 / 网址
- 发布号：`20260824-be27ab909306`
- 归档文件：`/root/releases/adp-20260824-be27ab909306.tgz`
- 归档 SHA-256：`be27ab909306b144740b866ad8a3ea7695f8a338305fec2c2a808f4acd7f9aa7`
- 正式网址：`https://1.14.148.15/production`
- 前端入口资源：`assets/index-CkOD-ahn.js`（本地最终构建）

## 5. 回滚位置与已知限制
- 回滚备份：`/opt/adp/backups/20260824-be27ab909306-blue-green`
- 回滚命令：`bash deploy/rollback-blue-green.sh 20260824-be27ab909306`（发布失败时立即执行）
- 已知限制：
  - 500 并发与 99.9% 稳定性仍需受控压测（NEED_CONTROLLED_LOAD_TEST）；
  - 15 分钟锁定自动解锁窗口未做长时等待实测（逻辑未改动）；
  - 只读查询不逐条审计（设计如此）；移动端离线队列为后续扩展。

## 6. 发布后验证（20260824-469380471efb）
- /healthz=200；/api/v1/health=200 environment=production；/api-docs/=200；/workbench=200；/production=200
- Nginx 指向 /opt/adp/releases/20260824-469380471efb/frontend/dist；API proxy 127.0.0.1:5002；adp-auth/adp-next 均 active
- 两份 reconciliation：ok=true、total_issues=0；备份 SHA256SUMS 校验通过（live-code.tgz / live-database.sql OK）
- 线上 index-CkOD-ahn.js 与 index-BeHcLxS8.css 的 SHA-256 与本地最终构建一致
- Playwright 只读冒烟：三个入口 200，控制台仅预期登录前 401 探测 2 条，无新增错误

## 7. P3 可读性优化（本次）
- auth_service.login 拆分为 login/_enforce_login_rate_limit/_reject_inactive_account/_verify_password_or_lock/_open_login_session/_audit_login_denied，行为与审计事件不变。
- backend/layers/common/db/query_guard.py 新增 SQL 标识符校验，master_data_store 与 data_exchange_store 动态表名接入；其余动态 SQL 补充白名单注释。
- readiness/load_support.py 健康轮询静默异常增加 debug 日志。
- 后端全量（含一次性 MySQL）397 passed / 0 skipped；前端 102 unit / 34 e2e / build 通过。
# ADP 升级说明

本次版本增加成本核算表、权限码、版本化分摊规则、成本台账生命周期以及企业治理基础（账号注销、待办/消息、追加式审计）。发布脚本会按文件名顺序执行 `database/migrations` 下的编号迁移，并把版本与 SHA-256 校验和写入 `schema_migrations`。已经登记的迁移不会重复执行；已登记文件若被修改，发布会立即停止，禁止通过改历史 SQL 绕过校验。迁移文件包括 `003_cost_accounting_foundation.sql`、`004_enterprise_governance_foundation.sql`、`005_cost_entry_lifecycle.sql` 和 `022_super_admin_account_permissions.sql`，其中 022 收紧养殖管理员的账号审核/管理权限。

## 发布前

1. 备份当前数据库和 `/opt/adp/login-registration/实现文档/登陆注册`。
2. 确认 `/etc/adp/auth.env` 中现有数据库配置有效。
3. 公网登录前必须先准备有效的域名（或含公网 IP SAN 的受信任证书）和证书文件。发布脚本会生成 HTTPS 站点及 HTTP→HTTPS 跳转；缺少证书或仍使用不安全 Cookie 时会在改动数据库前中止。
4. 当前拓扑为“公网请求 → 一层 Nginx → 127.0.0.1:5001 Flask”，因此在 `/etc/adp/auth.env` 增加：

   ```dotenv
   APP_ENV=production
   SESSION_COOKIE_SECURE=true
   TRUSTED_PROXY_HOPS=1
   ADP_SERVER_NAME=23331.cloud
   ADP_PUBLIC_PATH=/adp/
   ADP_NGINX_MODE=shared
   ADP_NGINX_PARENT_CONFIG=/etc/nginx/conf.d/23331.cloud.conf
   ADP_TLS_CERTIFICATE=/etc/letsencrypt/live/23331.cloud/fullchain.pem
   ADP_TLS_CERTIFICATE_KEY=/etc/letsencrypt/live/23331.cloud/privkey.pem
   ```

   共享域名入口固定为 `https://23331.cloud/adp/`，API 固定为
   `https://23331.cloud/adp/api/`。在现有 `23331.cloud` HTTPS `server` 块内加入
   `deploy/nginx-adp-shared-location.conf` 渲染后的内容；不要把 ADP 的整站模板覆盖到
   其他项目的根路径。

   本地开发或没有受控反向代理时保持 `TRUSTED_PROXY_HOPS=0`。该值必须等于 Flask 前受控代理的准确层数，不能按可能出现的最大层数填写。

## 发布与核验

从应用根目录执行 `bash deploy/deploy.sh`。脚本会先建立迁移登记表，然后按文件名顺序处理全部编号迁移（包括 `003_cost_accounting_foundation.sql`、`004_enterprise_governance_foundation.sql`、`005_cost_entry_lifecycle.sql` 和 `022_super_admin_account_permissions.sql`），最后更新参考字典、构建前端并重启服务。

发布完成后检查：

```bash
mysql --database="$MYSQL_DATABASE" --execute="SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version;"
mysql --database="$MYSQL_DATABASE" --execute="SHOW TRIGGERS LIKE 'audit_logs';"
mysql --database="$MYSQL_DATABASE" --execute="SHOW TRIGGERS LIKE 'cost_entries';"
mysql --database="$MYSQL_DATABASE" --execute="SELECT status, COUNT(*) FROM cost_entries GROUP BY status;"
mysql --database="$MYSQL_DATABASE" --execute="SELECT status, COUNT(*) FROM users GROUP BY status;"
mysql --database="$MYSQL_DATABASE" --execute="SELECT COUNT(*) AS work_items FROM work_items; SELECT COUNT(*) AS notifications FROM notifications;"
curl --fail -H "Host: 23331.cloud" http://127.0.0.1:5001/api/v1/health
curl --fail --resolve "$ADP_SERVER_NAME:443:127.0.0.1" "https://$ADP_SERVER_NAME${ADP_PUBLIC_PATH:-/adp/}healthz"
ADP_VERIFY_IDENTIFIER='一次性验收账号' ADP_VERIFY_PASSWORD='一次性验收密码' \
  deploy/verify-domain.sh
```

预期 `schema_migrations` 至少包含 001、002、003、004、005、022，`audit_logs` 有禁止更新/删除的两个触发器，`cost_entries` 有禁止正式记录更新/非草稿删除的触发器，账号和成本状态统计可查询，两个治理表可读，两个健康检查均成功。若出现校验和不一致，不要修改登记表；恢复原迁移文件，并用新的递增编号编写修复迁移。

## 回滚

升级前用明确的时间戳保留代码和数据库副本，例如：

```bash
release_stamp="$(date +%Y%m%d-%H%M%S)"
cp -a /opt/adp/login-registration/实现文档/登陆注册 "/opt/adp/backups/login-registration-${release_stamp}"
mysqldump --single-transaction --routines --triggers "$MYSQL_DATABASE" > "/opt/adp/backups/adp-${release_stamp}.sql"
```

若升级后健康检查或关键流程失败：先停止应用服务，将上述代码副本恢复到原路径；如本次迁移已写入业务数据，再从同一时间戳 SQL 备份恢复数据库；随后重启服务并重新执行两个健康检查。不要只删除 `schema_migrations` 记录，也不要手工逆向删除 003、004 或 005 表/触发器，因为这会留下权限、外键、审计触发器或业务数据不一致。恢复命令中的备份时间戳必须与发布前记录一致：

```bash
systemctl stop adp-auth
rsync -a --delete "/opt/adp/backups/login-registration-${release_stamp}/" /opt/adp/login-registration/实现文档/登陆注册/
mysql "$MYSQL_DATABASE" < "/opt/adp/backups/adp-${release_stamp}.sql"
systemctl start adp-auth
```


## 智能体运行时插件更新（必须手动执行）

塘小助的工具实现不在 Flask 应用里，而在 DSH 运行时的 npm 包
`@deepseek-ai/dsh-adp-agent-tools` 中。仓库内的权威副本是
`deploy/agent-runtime/dsh-adp-agent-tools.index.js`（与
`deepseek-harness/packages/extensions/adp-agent-tools/src/index.ts` 保持一致）。

只要该文件发生变化，发布后必须在服务器上同步**两份**副本（profile 与 runtime 各一份，
缺一不可，否则行为不一致）：

```bash
install -o root -g root -m 0644 deploy/agent-runtime/dsh-adp-agent-tools.index.js \
  /opt/adp-agent-runtime-20260907/node_modules/@deepseek-ai/dsh-adp-agent-tools/lib/index.js
install -o adp  -g adp  -m 0644 deploy/agent-runtime/dsh-adp-agent-tools.index.js \
  /var/lib/adp/agent-sidecar/profiles/sdk/node_modules/@deepseek-ai/dsh-adp-agent-tools/lib/index.js
node --check /opt/adp-agent-runtime-20260907/node_modules/@deepseek-ai/dsh-adp-agent-tools/lib/index.js
systemctl restart adp-next      # 清掉进程内缓存的 harness 子进程
```

约束（DSH 工具 DSL）：`parameters` 里可选参数**不要写** `required: false`，
省略 `required` 才是可选；写 `required: false` 会让插件加载失败，整轮对话返回 502。
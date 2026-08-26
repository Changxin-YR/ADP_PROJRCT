# 生命周期、并发与安全

## 正式业务状态

所有可录入业务记录遵循相同治理原则：

| 状态 | 可编辑 | 可物理删除 | 说明 |
| --- | --- | --- | --- |
| `draft` | 是 | 仅从未提交且无任何业务引用时 | 草稿不是正式事实 |
| `submitted` | 是 | 否 | 待核验；修改后版本递增，待办同步到新版本 |
| `verified` / `confirmed` | 否 | 否 | 核验后只读，只能查看、冲销或创建更正记录 |
| `cancelled` / `reversed` | 否 | 否 | 保留原记录与审计链，不做物理删除 |

DELETE 不是日常业务操作。后端会再次判断状态、历史提交记录和外键引用；前端是否显示删除按钮不改变此规则。

## 版本控制调用顺序

1. GET 记录，保存响应中的 `version`。
2. PATCH 已提交记录时提交 `expected_version`。
3. 服务端只在当前版本一致且记录尚未核验时更新，同时写修订快照并把版本加一。
4. 提交、核验、确认、取消、冲销、更正也必须携带最新 `expected_version`。
5. 收到 `VERSION_CONFLICT` 后重新 GET，不得复用旧请求自动覆盖。

```json
{
  "expected_version": 3,
  "quantity": 125.5,
  "note": "根据复核称重单更新"
}
```

核验后只读由后端状态机、数据库写入条件和权限共同保证。需要调整正式数据时，使用 `/corrections`、`/correct` 或 `/reverse`，原事实仍然保留。

## 双人核验

采购审批、销售审批、付款、收款、仓储、生产、成本及塘口状态变更均禁止经办人自审。核验账号必须具备对应能力码，并位于数据范围内。客户端不能通过更换用户 ID、记录 ID 或待办 ID 绕过校验。

塘口状态变更使用独立申请接口，不允许通用 PATCH 直接修改 `status`：

```http
POST /api/v1/master-data/ponds/12/status-changes
{"to_status":"clean","reason":"批次结束清塘","expected_version":4}

POST /api/v1/master-data/ponds/12/status-changes/7/verify
{"expected_version":1,"expected_pond_version":4}
```

## 幂等与重复提交

API 当前不公开通用幂等 Header。采购收货生成应付、销售交付生成应收、库存入账、成本确认等高风险写入在服务端事务内使用业务来源唯一键和幂等键防重。客户端仍应：

- 每次请求生成唯一 `X-Request-ID`；
- 按钮提交期间禁止重复点击；
- 网络超时后先查询来源记录和目标单据，再决定是否重试；
- 对 409 重复来源或版本冲突给出人工确认界面。

## CSRF、Cookie 与日志

CSRF Token 只保存在内存并通过请求头发送，不写入 URL、localStorage 或业务表。`adp_session` 为 HttpOnly、SameSite=Lax Cookie，生产环境启用 Secure。退出登录会撤销服务端会话并删除 Cookie。

禁止记录密码、完整 Cookie、CSRF Token、附件内容或数据库连接凭据。排障记录 `request_id`、接口、HTTP 状态、错误 `code`、操作账号和时间即可。

## 权限处理

401 表示需要重新认证；403 表示已认证但无能力码、账号不在用或数据范围不覆盖。账号、注册审核、角色授权和全局审计除能力码外还要求超级管理员身份。业务系统不得仅依赖菜单隐藏或路由守卫。


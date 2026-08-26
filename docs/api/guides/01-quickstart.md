# ADP API 快速开始

## 基本约定

- 基础地址：`https://1.14.148.15/api/v1`
- 编码：UTF-8，业务请求与响应使用 JSON；附件和导入使用 `multipart/form-data`。
- 登录态：服务端通过 HttpOnly Cookie `adp_session` 识别用户。浏览器调用必须设置 `credentials: 'include'`。
- 请求追踪：客户端可传 `X-Request-ID`（1–32 位字母、数字、点、下划线或连字符）；响应始终返回同名响应头和 `request_id` 字段。
- CSRF：所有 POST、PUT、PATCH、DELETE 请求必须携带 `X-CSRF-Token`。Token 由 `/auth/csrf` 获取，并与首次响应设置的会话 Cookie 配对。
- 权限与范围：后端同时校验能力码、用户状态、组织、基地、区域和个人范围。隐藏前端按钮不是安全边界。

## 登录调用顺序

下例中的 `<PASSWORD>` 是调用方运行时输入，不应写入源码、日志或文档。

```bash
# 1. 获取 CSRF Token，并保存服务端会话 Cookie
curl -k -c adp.cookies https://1.14.148.15/api/v1/auth/csrf

# 2. 使用返回 data.csrf_token 登录；继续保存 Cookie
curl -k -b adp.cookies -c adp.cookies \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{"identifier":"api-user","password":"<PASSWORD>"}' \
  https://1.14.148.15/api/v1/auth/login

# 3. 读取当前账号、角色、权限和数据范围
curl -k -b adp.cookies https://1.14.148.15/api/v1/auth/me
```

生产证书配置完成后不应使用 `-k`。示例保留该参数仅用于当前 IP HTTPS 环境的自签名证书验收。

## 浏览器调用

```ts
const csrf = await fetch('/api/v1/auth/csrf', { credentials: 'include' })
  .then(response => response.json())
  .then(body => body.data.csrf_token)

const response = await fetch('/api/v1/master-data/ponds', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
  body: JSON.stringify({ code: 'POND-001', name: '一号塘', farm_id: 1 }),
})
```

## 统一响应

```json
{
  "code": "OK",
  "message": "操作成功",
  "data": { "record": { "id": 101, "status": "draft", "version": 1 } },
  "request_id": "request-example-001"
}
```

错误响应结构不变，`code` 表示机器可判断的错误，`message` 面向操作人员，`request_id` 用于关联审计日志。常见 HTTP 状态为 400（参数或状态错误）、401（未登录/会话过期）、403（权限或范围不足）、404（对象不存在或不可见）、409（版本冲突/重复业务）和 429（频率限制）。

## 分页与筛选

列表接口统一优先使用 `page`、`page_size`、`keyword` 和 `status`；支持的业务列表还可传 `farm_id`、`area_id`、日期和排序参数。`page` 从 1 开始，`page_size` 最大 100。调用方必须使用响应中的总数和当前页信息，不得假设返回全部数据。

```http
GET /api/v1/production/feed-logs?page=1&page_size=20&status=submitted&keyword=202608 HTTP/1.1
Cookie: adp_session=<SESSION_COOKIE>
```

## 失败重试

- GET 可按网络策略重试；写请求先查询原记录确认是否已成功。
- 409 `VERSION_CONFLICT` 必须重新读取最新记录，由用户确认差异后再次提交，禁止静默覆盖。
- 429 按 `Retry-After` 等待，不得固定频率高并发重试。
- 401 重新登录；403 不重试，应申请权限或缩小数据范围。


# DeepSeek Harness ADP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ADP 管理系统中交付一个与当前登录账号权限一致、查询可直执行且写操作必须人工确认的 DeepSeek Harness 智能体。

**Architecture:** Vue 原生右下角面板只访问 Flask Agent Gateway。Gateway 从现有 `adp_session` 解析用户并复用现有 service/route，负责工具白名单、三层授权、确认令牌、幂等和审计。Gateway 通过 Python SDK 启动受限的 `dsh --profile sdk` sidecar；Harness 侧只安装一个显式 ADP 工具插件，不拥有 Cookie、数据库或任意 HTTP 能力。

**Tech Stack:** Python 3.11+/Flask/MySQL/pytest；Vue 3/TypeScript/Vitest/Playwright；DeepSeek Harness TypeScript plugin、Python SDK、stdio JSON-RPC。

**Repositories:**

- ADP：`C:\Users\27363\Desktop\ADP`
- DeepSeek Harness：`C:\Users\27363\Desktop\deepseek-harness-master`

---

## 文件边界

### ADP

- Create: `backend/layers/features/agent/agent_contracts.py` — 工具、会话、确认和统一结果类型。
- Create: `backend/layers/features/agent/agent_tool_registry.py` — 显式业务工具目录和 service 适配器。
- Create: `backend/layers/features/agent/agent_confirmation_store.py` — 确认令牌的持久化读写接口。
- Create: `backend/layers/features/agent/agent_gateway_service.py` — 会话绑定、Harness 调用、工具执行和审计编排。
- Create: `backend/layers/features/agent/harness_sidecar.py` — Python SDK sidecar 生命周期和受限上下文。
- Create: `backend/layers/product/agent/routes.py` — `/api/v1/agent/*` 网关路由。
- Create: `backend/tests/test_agent_gateway.py` — 网关、确认、权限、错误和审计测试。
- Create: `backend/tests/test_agent_tool_registry.py` — 工具覆盖矩阵和 schema 测试。
- Create: `database/migrations/031_agent_confirmations.sql` — 待确认操作表。
- Modify: `backend/app.py` — 注册 agent blueprint 和依赖注入。
- Modify: `backend/config/settings.py` — sidecar、超时和确认 TTL 配置。
- Modify: `.env.example` — 新增非敏感配置示例。
- Create: `tools/build_agent_catalog.py` — 从 Flask 路由/OpenAPI 生成覆盖报告，不生成任意调用能力。
- Create: `docs/api/agent-tool-coverage.json` — 生成的覆盖结果（由命令生成，不手工编辑）。
- Create: `frontend/src/layers/features/agent/agent.models.ts` — 面板和网关 DTO。
- Create: `frontend/src/layers/features/agent/agent.service.ts` — 网关请求封装。
- Create: `frontend/src/layers/common/ui/AgentPanel.vue` — 悬浮入口、面板、确认卡片和结果状态。
- Modify: `frontend/src/layers/common/ui/AppShell.vue` — 在主壳挂载面板。
- Modify: `frontend/src/styles/workbench.css` — 面板和移动抽屉样式。
- Create: `frontend/tests/agent-panel.spec.ts` — 面板单元/组件测试。
- Create: `frontend/tests/agent-flow.spec.ts` — 关键流程 Playwright 验收。

### DeepSeek Harness

- Create: `packages/extensions/adp-agent-tools/package.json` — 插件包元数据和 workspace 依赖。
- Create: `packages/extensions/adp-agent-tools/src/index.ts` — `ctx.tools` 工具注册、Gateway 调用和 approval 适配。
- Create: `packages/extensions/adp-agent-tools/tests/tools.spec.ts` — 工具 schema、pre-execute 和 approval 测试。
- Modify: `pnpm-workspace.yaml`（仅在 workspace 未自动包含 `packages/extensions/*` 时）— 纳入插件包。

## Task 1: 建立确认表和配置契约

**Files:**
- Create: `database/migrations/031_agent_confirmations.sql`
- Create: `backend/layers/features/agent/agent_contracts.py`
- Create: `backend/layers/features/agent/agent_confirmation_store.py`
- Modify: `backend/config/settings.py`
- Modify: `.env.example`
- Test: `backend/tests/test_agent_gateway.py`

- [ ] **Step 1: Write the failing persistence and config tests**

```python
def test_agent_confirmation_schema_has_single_use_fields(mysql_cursor):
    mysql_cursor.execute("DESCRIBE agent_confirmations")
    columns = {row[0] for row in mysql_cursor.fetchall()}
    assert {"token_hash", "user_id", "session_hash", "payload_json", "status", "expires_at", "used_at"} <= columns


def test_settings_reads_agent_limits():
    settings = Settings.from_env({**TEST_ENV, "AGENT_REQUEST_TIMEOUT_SECONDS": "30", "AGENT_CONFIRMATION_TTL_SECONDS": "120"})
    assert settings.agent_request_timeout_seconds == 30
    assert settings.agent_confirmation_ttl_seconds == 120
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest backend/tests/test_agent_gateway.py::test_settings_reads_agent_limits -q`

Expected: FAIL because the settings fields and confirmation table do not exist.

- [ ] **Step 3: Add the migration, immutable contracts and bounded settings**

```sql
CREATE TABLE agent_confirmations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id BIGINT NOT NULL,
  session_hash CHAR(64) NOT NULL,
  conversation_id VARCHAR(64) NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  tool_name VARCHAR(128) NOT NULL,
  payload_json JSON NOT NULL,
  status ENUM('pending','confirmed','cancelled','expired') NOT NULL DEFAULT 'pending',
  expires_at DATETIME(6) NOT NULL,
  used_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_agent_confirmations_user_status (user_id, status, expires_at),
  CONSTRAINT fk_agent_confirmations_user FOREIGN KEY (user_id) REFERENCES users(id)
);
```

```python
@dataclass(frozen=True)
class AgentConfirmation:
    id: int
    token_hash: str
    user_id: int
    session_hash: str
    conversation_id: str
    request_id: str
    tool_name: str
    payload: dict[str, Any]
    idempotency_key: str
    status: Literal["pending", "confirmed", "cancelled", "expired"]
    expires_at: datetime
```

Add `agent_request_timeout_seconds` (default 30, maximum 60), `agent_confirmation_ttl_seconds` (default 120, maximum 600), `agent_sidecar_home`, `agent_sidecar_cwd`, and `agent_sidecar_command` to `Settings`; reject non-positive values and production configurations without an explicit sidecar home.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest backend/tests/test_agent_gateway.py::test_settings_reads_agent_limits -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/config/settings.py backend/layers/features/agent database/migrations/031_agent_confirmations.sql .env.example backend/tests/test_agent_gateway.py
git commit -m "feat: add agent confirmation contract"
```

## Task 2: Implement the explicit ADP tool registry

**Files:**
- Create: `backend/layers/features/agent/agent_tool_registry.py`
- Create: `tools/build_agent_catalog.py`
- Create: `backend/tests/test_agent_tool_registry.py`
- Create: `docs/api/agent-tool-coverage.json`

- [ ] **Step 1: Write failing registry tests for risk, permissions and route coverage**

```python
def test_registry_marks_read_and_write_tools():
    registry = build_registry()
    assert registry.get("master_data.list_records").risk == "read"
    assert registry.get("master_data.create_record").risk == "write"
    assert registry.get("admin.update_role_permissions").risk == "human_only"


def test_registry_has_every_api_operation_or_explicit_human_marker(app):
    catalog = build_agent_catalog(app, build_registry())
    assert catalog["unmapped_operations"] == []
    assert catalog["human_only_operations"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_agent_tool_registry.py -q`

Expected: FAIL because no registry or coverage generator exists.

- [ ] **Step 3: Add typed tool metadata and bounded adapters**

```python
@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path_template: str
    parameters: dict[str, Any]
    required_permission: str | None
    risk: Literal["read", "write", "human_only"]
    execute: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None


TOOLS = (
    AgentTool("master_data.list_records", "查询塘口和主数据", "GET", "/api/v1/master-data/{resource}", MASTER_LIST_SCHEMA, "master_data.view", "read", _list_master_data),
    AgentTool("master_data.get_record", "查询主数据详情", "GET", "/api/v1/master-data/{resource}/{record_id}", MASTER_GET_SCHEMA, "master_data.view", "read", _get_master_data),
    AgentTool("master_data.create_record", "创建塘口或主数据记录", "POST", "/api/v1/master-data/{resource}", MASTER_MUTATION_SCHEMA, "master_data.manage", "write", _create_master_data),
    AgentTool("production.list_records", "查询生产记录", "GET", "/api/v1/production/{resource}", PRODUCTION_LIST_SCHEMA, "production.view", "read", _list_production),
    AgentTool("warehouse.list_records", "查询仓储记录", "GET", "/api/v1/warehouse/{resource}", WAREHOUSE_LIST_SCHEMA, "warehouse.view", "read", _list_warehouse),
    AgentTool("purchase.list_orders", "查询采购订单", "GET", "/api/v1/purchase/orders", LIST_SCHEMA, "purchase.view", "read", _list_purchase_orders),
    AgentTool("sales.list_orders", "查询销售订单", "GET", "/api/v1/sales/orders", LIST_SCHEMA, "sales.view", "read", _list_sales_orders),
    AgentTool("cost.list_entries", "查询成本条目", "GET", "/api/v1/cost/entries", LIST_SCHEMA, "cost.view", "read", _list_cost_entries),
    AgentTool("data_exchange.preview_import", "预检数据导入", "POST", "/api/v1/data-exchange/imports/preview", IMPORT_SCHEMA, "data_exchange.manage", "read", _preview_import),
    AgentTool("workbench.list_work_items", "查询待办", "GET", "/api/v1/work-items", LIST_SCHEMA, "work_item.view", "read", _list_work_items),
)
```

Register every remaining operation using the same `AgentTool` shape. All generic route adapters must select a fixed service method from a literal map keyed by `tool.name`; no adapter may concatenate a client-provided URL or method. Mark `/api/v1/admin` permission/grant/role/user-status/password mutations as `human_only` with `execute=None`. Mark all other POST/PUT/PATCH/DELETE operations as `write` and require confirmation.

`build_agent_catalog.py` must compare `app.url_map` and `api-docs/openapi.json` against the registry and write counts plus `unmapped_operations` and `human_only_operations` to `docs/api/agent-tool-coverage.json`.

- [ ] **Step 4: Run coverage and registry tests**

Run: `python tools/build_openapi.py; python tools/build_agent_catalog.py; pytest backend/tests/test_agent_tool_registry.py -q`

Expected: OpenAPI reports the existing operation count, coverage reports zero unmapped operations, and pytest passes.

- [ ] **Step 5: Commit**

```bash
git add backend/layers/features/agent/agent_tool_registry.py tools/build_agent_catalog.py docs/api/agent-tool-coverage.json backend/tests/test_agent_tool_registry.py
git commit -m "feat: register typed ADP agent tools"
```

## Task 3: Add the confirmation store and three-layer gateway service

**Files:**
- Create: `backend/layers/features/agent/agent_confirmation_store.py`
- Create: `backend/layers/features/agent/agent_gateway_service.py`
- Create: `backend/tests/test_agent_gateway.py`

- [ ] **Step 1: Write failing tests for direct reads, pending writes, single-use confirmation and denial**

```python
def test_write_tool_returns_pending_without_calling_service(monkeypatch, gateway, active_user):
    monkeypatch.setattr(gateway.registry.get("master_data.create_record"), "execute", lambda *_: (_ for _ in ()).throw(AssertionError("must not execute")))
    result = gateway.prepare_tool(active_user, "master_data.create_record", {"resource": "ponds", "name": "一号塘"}, conversation_id="c-1", request_id="r-1")
    assert result["kind"] == "confirmation_required"
    assert result["confirmation"]["tool_name"] == "master_data.create_record"


def test_confirm_rechecks_session_permission_and_consumes_token(gateway, active_user):
    pending = gateway.create_pending(active_user, "master_data.create_record", {"resource": "ponds", "name": "一号塘"})
    first = gateway.confirm(active_user, pending.token)
    second = gateway.confirm(active_user, pending.token)
    assert first["kind"] == "success"
    assert second["code"] == "CONFIRMATION_USED"


def test_human_only_permission_change_is_never_executable(gateway, active_user):
    result = gateway.prepare_tool(active_user, "admin.update_role_permissions", {"role_id": 1, "permissions": []}, conversation_id="c-1", request_id="r-1")
    assert result["kind"] == "human_only"
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `pytest backend/tests/test_agent_gateway.py -q`

Expected: FAIL because the gateway service and store are not implemented.

- [ ] **Step 3: Implement the minimal gateway service**

```python
class AgentGatewayService:
    def prepare_tool(self, user: dict[str, Any], tool_name: str, arguments: dict[str, Any], *, conversation_id: str, request_id: str) -> dict[str, Any]:
        tool = self.registry.require(tool_name)
        self._require_session(user)
        self._require_permission(user, tool.required_permission)
        self._validate_arguments(tool, arguments)
        if tool.risk == "human_only":
            self._audit(user, tool, arguments, result="human_only", request_id=request_id)
            return {"kind": "human_only", "code": "HUMAN_REQUIRED", "message": "请在系统管理页面由人工完成该操作"}
        if tool.risk == "read":
            return {"kind": "success", "data": tool.execute(arguments, {"user": user, "request_id": request_id})}
        pending = self.confirmations.create(user=user, session_hash=self.session_hash(user), conversation_id=conversation_id, request_id=request_id, tool=tool, payload=arguments, ttl_seconds=self.settings.agent_confirmation_ttl_seconds)
        self._audit(user, tool, arguments, result="pending", request_id=request_id)
        return {"kind": "confirmation_required", "confirmation": pending.public_view()}

    def confirm(self, user: dict[str, Any], token: str, *, request_id: str) -> dict[str, Any]:
        pending = self.confirmations.claim(token, user_id=int(user["id"]), session_hash=self.session_hash(user))
        tool = self.registry.require(pending.tool_name)
        self._require_session(user)
        self._require_permission(user, tool.required_permission)
        self._validate_arguments(tool, pending.payload)
        result = execute_idempotent(self.settings, user_id=int(user["id"]), action_code=f"agent:{tool.name}", key=pending.idempotency_key, payload=pending.payload, operation=lambda: (tool.execute(pending.payload, {"user": user, "request_id": request_id}), 200))
        self.confirmations.mark_confirmed(pending.id)
        self._audit(user, tool, pending.payload, result="success", request_id=request_id)
        return {"kind": "success", "data": result[0], "request_id": request_id}
```

`_require_permission` uses the existing permission codes and fails closed when `data_scopes` is empty for non-super-admin users. Each adapter calls the existing feature service with the full current user; it never writes SQL directly. `claim` must atomically update `status='pending'` to `status='confirmed'` only when token, user, session and expiry match.

- [ ] **Step 4: Run gateway tests**

Run: `pytest backend/tests/test_agent_gateway.py -q`

Expected: PASS, including no service call before confirmation, single-use token, permission denial and human-only behavior.

- [ ] **Step 5: Commit**

```bash
git add backend/layers/features/agent backend/tests/test_agent_gateway.py
git commit -m "feat: enforce agent confirmation and authorization"
```

## Task 4: Expose authenticated Agent Gateway routes

**Files:**
- Create: `backend/layers/product/agent/routes.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_agent_gateway.py`

- [ ] **Step 1: Write failing route contract tests**

```python
def test_agent_turn_requires_login(client):
    response = client.post("/api/v1/agent/turn", json={"message": "查询塘口"})
    assert response.status_code == 401
    assert response.get_json()["code"] == "UNAUTHENTICATED"


def test_agent_confirm_requires_csrf(client, logged_in_user, pending_confirmation):
    response = client.post("/api/v1/agent/confirm", json={"token": pending_confirmation})
    assert response.status_code == 403
    assert response.get_json()["code"] == "CSRF_INVALID"
```

- [ ] **Step 2: Run route tests and verify they fail**

Run: `pytest backend/tests/test_agent_gateway.py::test_agent_turn_requires_login -q`

Expected: FAIL with 404 because the blueprint is not registered.

- [ ] **Step 3: Add routes and register the blueprint**

```python
@blueprint.post("/turn")
def turn():
    require_csrf()
    user = current_user()
    payload = json_object()
    message = str(payload.get("message", "")).strip()
    if not message:
        raise AgentGatewayError("VALIDATION_ERROR", "请输入要执行的指令", 400)
    result = service.run_turn(user, message, conversation_id=str(payload.get("conversation_id") or uuid4().hex), request_id=g.request_id)
    return jsonify(ok(result))


@blueprint.post("/confirm")
def confirm():
    require_csrf()
    result = service.confirm(current_user(), str(json_object().get("token", "")), request_id=g.request_id)
    return jsonify(ok(result))
```

Use the same `AuthService.current_user(request_session_token(request))`, `require_csrf`, error envelope and `request_id` conventions as the existing blueprints. Add `create_agent_blueprint(...)` to `backend/app.py` after the existing product blueprints. The route layer must never accept a target URL, SQL string, raw Cookie, or arbitrary HTTP method.

- [ ] **Step 4: Run route and existing auth tests**

Run: `pytest backend/tests/test_agent_gateway.py backend/tests/test_auth_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/layers/product/agent/routes.py backend/app.py backend/tests/test_agent_gateway.py
git commit -m "feat: expose authenticated agent gateway"
```

## Task 5: Connect the Harness SDK sidecar and ADP plugin

**Files:**
- Create: `backend/layers/features/agent/harness_sidecar.py`
- Create: `C:\Users\27363\Desktop\deepseek-harness-master\packages\extensions\adp-agent-tools\package.json`
- Create: `C:\Users\27363\Desktop\deepseek-harness-master\packages\extensions\adp-agent-tools\src\index.ts`
- Create: `C:\Users\27363\Desktop\deepseek-harness-master\packages\extensions\adp-agent-tools\tests\tools.spec.ts`
- Modify: `backend/config/settings.py`
- Test: `backend/tests/test_agent_gateway.py`

- [ ] **Step 1: Write failing sidecar and plugin tests**

ADP test:

```python
def test_sidecar_passes_ephemeral_context_without_cookie(monkeypatch, settings):
    captured = {}
    monkeypatch.setattr("deepseek_harness.DeepSeekHarness", FakeHarness(captured))
    HarnessSidecar(settings).run("查询塘口", context={"conversation_id": "c-1", "gateway_url": "http://127.0.0.1"})
    assert "adp_session" not in captured["context"]
    assert captured["context"]["conversation_id"] == "c-1"
```

Harness test:

```ts
it('registers only fixed ADP tools and routes writes through approval', async () => {
  const harness = await createHarnessWithAdpPlugin()
  expect(harness.ctx.tools.schemas().map((item) => item.name)).toEqual(expect.arrayContaining(['adp_query', 'adp_mutation']))
  harness.ctx.on('tools/pre-execute', async (exec, _next) => exec.name === 'adp_mutation' ? { kind: 'ask' } : { kind: 'allow' })
  const result = await harness.ctx.tools.execute({ signal: new AbortController().signal, callId: ToolCallId('write-1'), name: 'adp_mutation', arguments: { operation: 'master_data.create_record', arguments: { resource: 'ponds' } } })
  expect(result.isError).toBe(true)
})
```

- [ ] **Step 2: Run both tests and verify they fail**

Run: `pytest backend/tests/test_agent_gateway.py::test_sidecar_passes_ephemeral_context_without_cookie -q` and `pnpm --dir C:\Users\27363\Desktop\deepseek-harness-master exec vitest run packages/extensions/adp-agent-tools/tests/tools.spec.ts`

Expected: FAIL because the sidecar and plugin package do not exist.

- [ ] **Step 3: Implement the sidecar wrapper**

```python
class HarnessSidecar:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, prompt: str, *, context: dict[str, str]) -> RunResult:
        safe_context = {key: value for key, value in context.items() if key in {"conversation_id", "request_id", "gateway_url", "context_token"}}
        with DeepSeekHarness(dsh_home=self.settings.agent_sidecar_home, cwd=self.settings.agent_sidecar_cwd, profile="sdk", request_timeout_seconds=self.settings.agent_request_timeout_seconds) as harness:
            return harness.run(json.dumps({"prompt": prompt, "context": safe_context}, ensure_ascii=False), session_id=safe_context["conversation_id"])
```

The wrapper must import the SDK lazily so ADP can start when Harness is unavailable; convert startup/timeout/protocol exceptions into `AGENT_UNAVAILABLE`, `AGENT_TIMEOUT`, or `AGENT_PROTOCOL_ERROR` without exposing stack traces.

- [ ] **Step 4: Implement the TypeScript plugin with fixed Gateway calls and approval**

```ts
export const name = 'adp-agent-tools'
export const inject = ['tools', 'approval']

export function apply(ctx: Context, config: { gatewayUrl: string; contextToken: string }) {
  ctx.tools.register(defineTool({
    name: 'adp_query',
    description: '查询当前登录用户有权查看的 ADP 数据。',
    parameters: { operation: { type: 'string', required: true }, arguments: { type: 'object', required: true } },
    output: { schema: { type: 'object' }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
    async execute(args, exec) { return callGateway(config, '/query', args, exec.signal) },
  }))
  ctx.tools.register(defineTool({
    name: 'adp_mutation',
    description: '准备一个需要登录者确认的 ADP 业务写操作。',
    parameters: { operation: { type: 'string', required: true }, arguments: { type: 'object', required: true } },
    output: { schema: { type: 'object' }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
    async execute(args, exec) {
      const decision = await ctx.approval.request({ agent: exec.agent, toolName: 'adp_mutation', callId: exec.callId })
      if (decision !== 'allowed-once') throw new Error('需要登录者确认后才能执行')
      return callGateway(config, '/prepare', args, exec.signal)
    },
  }))
}
```

`callGateway` may call only the configured absolute gateway URL and fixed `/query` or `/prepare` paths, sends the short-lived context token, honors `AbortSignal`, and never receives an `adp_session` value. The Gateway converts `/prepare` into the ADP confirmation card; the Vue confirmation endpoint performs the final execution.

- [ ] **Step 5: Run sidecar and plugin tests**

Run: `pytest backend/tests/test_agent_gateway.py -q` and `pnpm --dir C:\Users\27363\Desktop\deepseek-harness-master exec vitest run packages/extensions/adp-agent-tools/tests/tools.spec.ts`

Expected: PASS; no raw Cookie appears in sidecar/plugin fixtures.

- [ ] **Step 6: Commit the two repositories separately**

```bash
git add backend/layers/features/agent/harness_sidecar.py backend/config/settings.py backend/tests/test_agent_gateway.py
git commit -m "feat: run Harness SDK as ADP sidecar"
cd C:\Users\27363\Desktop\deepseek-harness-master
git add packages/extensions/adp-agent-tools
git commit -m "feat: add ADP gateway Harness tools"
```

## Task 6: Build the Vue agent panel

**Files:**
- Create: `frontend/src/layers/features/agent/agent.models.ts`
- Create: `frontend/src/layers/features/agent/agent.service.ts`
- Create: `frontend/src/layers/common/ui/AgentPanel.vue`
- Modify: `frontend/src/layers/common/ui/AppShell.vue`
- Modify: `frontend/src/styles/workbench.css`
- Test: `frontend/tests/agent-panel.spec.ts`

- [ ] **Step 1: Write failing component tests**

```ts
it('mounts a compact agent launcher and opens the panel', async () => {
  const wrapper = mountAgentPanel()
  expect(wrapper.get('[aria-label="打开智能助手"]').exists()).toBe(true)
  await wrapper.get('[aria-label="打开智能助手"]').trigger('click')
  expect(wrapper.get('[role="dialog"]').text()).toContain('智能助手')
})

it('shows confirmation and only confirms after explicit click', async () => {
  const wrapper = mountAgentPanel({ turn: { kind: 'confirmation_required', confirmation: { id: 'c-1', tool_name: 'master_data.create_record', summary: '创建一号塘' } } })
  expect(wrapper.get('[data-testid="agent-confirmation"]').text()).toContain('创建一号塘')
  expect(wrapper.emitted('confirm')).toBeUndefined()
  await wrapper.get('[data-testid="agent-confirm"]').trigger('click')
  expect(wrapper.emitted('confirm')).toHaveLength(1)
})
```

- [ ] **Step 2: Run the component tests and verify they fail**

Run: `npm --prefix frontend run test:unit -- agent-panel.spec.ts`

Expected: FAIL because the service, component and shell mount do not exist.

- [ ] **Step 3: Add DTOs and service calls using the existing API client**

```ts
export type AgentTurn =
  | { kind: 'success'; data: unknown; request_id: string }
  | { kind: 'confirmation_required'; confirmation: AgentConfirmation }
  | { kind: 'human_only'; code: 'HUMAN_REQUIRED'; message: string }

export function createAgentService(client = createApiClient()) {
  return {
    turn: (message: string, conversation_id?: string) => client.post<AgentTurn>('/api/v1/agent/turn', { message, conversation_id }),
    confirm: (token: string) => client.post<AgentTurn>('/api/v1/agent/confirm', { token }),
  }
}
```

- [ ] **Step 4: Implement the panel and mount it once in `AppShell.vue`**

Use a fixed launcher with an icon and tooltip, a desktop right-side panel at roughly 30vw, and a mobile bottom drawer under `@media (max-width: 720px)`. Render statuses `idle`, `connecting`, `thinking`, `confirmation_required`, `executing`, `success`, `human_only`, `error`, `offline`, and `session_expired`. Confirmation displays action, target, redacted parameters, risk text and one confirm/cancel pair. `Escape` closes the panel; focus moves to the panel heading on open and returns to the launcher on close. Add `<AgentPanel />` after the existing shell content so it survives route changes but is not mounted on auth-only layouts.

- [ ] **Step 5: Run component tests and build**

Run: `npm --prefix frontend run test:unit -- agent-panel.spec.ts; npm --prefix frontend run build`

Expected: PASS and a successful Vue type-check/Vite build.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layers/features/agent frontend/src/layers/common/ui/AgentPanel.vue frontend/src/layers/common/ui/AppShell.vue frontend/src/styles/workbench.css frontend/tests/agent-panel.spec.ts
git commit -m "feat: add ADP agent panel"
```

## Task 7: Add end-to-end security and business-flow coverage

**Files:**
- Create: `frontend/tests/agent-flow.spec.ts`
- Modify: `backend/tests/test_agent_gateway.py`
- Modify: `backend/tests/test_openapi_contract.py` only if the coverage report needs a stable assertion.

- [ ] **Step 1: Write failing end-to-end and regression tests**

```python
def test_expired_confirmation_is_rejected_without_service_call(gateway, active_user):
    pending = gateway.create_pending(active_user, "master_data.create_record", {"resource": "ponds"}, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    result = gateway.confirm(active_user, pending.token, request_id="r-1")
    assert result["code"] == "CONFIRMATION_EXPIRED"


def test_agent_audit_contains_correlation_ids(gateway, active_user, audit_store):
    gateway.prepare_tool(active_user, "master_data.list_records", {"resource": "ponds"}, conversation_id="c-1", request_id="r-1")
    event = audit_store.last()
    assert event["conversation_id"] == "c-1"
    assert event["request_id"] == "r-1"
```

```ts
test('pond creation requires confirmation and cancellation creates no request', async ({ page }) => {
  await loginAs(page, 'pond-manager')
  await page.getByLabel('打开智能助手').click()
  await page.getByRole('textbox', { name: '智能助手指令' }).fill('创建一个名为一号塘的鱼塘')
  await page.getByRole('button', { name: '发送指令' }).click()
  await expect(page.getByTestId('agent-confirmation')).toContainText('创建一号塘')
  await page.getByTestId('agent-cancel').click()
  await expect(page.getByTestId('agent-confirmation')).not.toBeVisible()
})
```

- [ ] **Step 2: Run the tests and verify new assertions fail**

Run: `pytest backend/tests/test_agent_gateway.py -q; npm --prefix frontend run test:e2e -- agent-flow.spec.ts`

Expected: new assertions fail until expiry/audit/panel flow is complete; pre-existing tests remain green.

- [ ] **Step 3: Add failure-path handling and redaction**

Map sidecar errors to `AGENT_UNAVAILABLE`, `AGENT_TIMEOUT`, `AGENT_PROTOCOL_ERROR`; map expired/used/session-changed confirmations to 409/401 responses; never retry a mutation automatically. Redact password, token, Cookie, authorization and attachment contents from confirmation cards and audit payloads. On 401/`SESSION_EXPIRED`, clear the existing session store and route to `/auth/login` using the current router guard behavior.

- [ ] **Step 4: Run the complete focused suite**

Run: `pytest backend/tests/test_agent_gateway.py backend/tests/test_agent_tool_registry.py backend/tests/test_openapi_contract.py -q; npm --prefix frontend run test:unit -- agent-panel.spec.ts; npm --prefix frontend run test:e2e -- agent-flow.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_agent_gateway.py backend/tests/test_agent_tool_registry.py frontend/tests/agent-flow.spec.ts
git commit -m "test: verify agent security and confirmation flows"
```

## Task 8: Production wiring, coverage report and final verification

**Files:**
- Modify: `.env.example`
- Modify: deployment service/config files only where the existing deployment starts Flask and needs the sidecar environment.
- Create/update: `docs/api/agent-tool-coverage.json`
- Test: `backend/tests/test_deploy_contract.py` or the existing deployment contract test that owns environment assertions.

- [ ] **Step 1: Write failing deployment/config assertions**

```python
def test_production_contract_requires_agent_sidecar_home():
    env = production_env_without("AGENT_SIDECAR_HOME")
    with pytest.raises(ConfigError, match="AGENT_SIDECAR_HOME"):
        Settings.from_env(env)
```

- [ ] **Step 2: Implement explicit deployment settings**

Add `AGENT_SIDECAR_HOME`, `AGENT_SIDECAR_CWD`, `AGENT_SIDECAR_COMMAND`, `AGENT_REQUEST_TIMEOUT_SECONDS`, and `AGENT_CONFIRMATION_TTL_SECONDS` to deployment templates and `.env.example`. Do not add model API keys to source control. Keep the sidecar process user, working directory and filesystem access restricted to its Harness home; it must not access the ADP private attachment root or database socket.

- [ ] **Step 3: Run coverage and all verification commands**

Run:

```bash
python tools/build_openapi.py
python tools/build_agent_catalog.py
pytest -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- agent-flow.spec.ts
```

Expected: all commands exit 0; `docs/api/agent-tool-coverage.json` reports zero unmapped operations; the browser test demonstrates query, pending confirmation, cancellation and human-only permission behavior.

- [ ] **Step 4: Review the final diff and commit**

```bash
git diff --check
git status --short
git add .env.example backend frontend tools docs/api/agent-tool-coverage.json database/migrations/031_agent_confirmations.sql
git commit -m "feat: integrate DeepSeek Harness with ADP"
```

Do not stage unrelated pre-existing worktree changes. The Harness repository receives its own final commit from Task 5.

## Plan self-review

- **Spec coverage:** Architecture/session binding is covered by Tasks 3-5; all business domains and human-only admin mutations by Task 2; panel behavior by Task 6; timeout, errors, idempotency and audit by Tasks 3 and 7; testing and acceptance by Tasks 7-8.
- **Placeholder scan:** No unresolved placeholder markers or unspecified handling steps remain.
- **Type consistency:** `AgentTool`, `AgentConfirmation`, `AgentTurn`, `prepare_tool`, and `confirm` are defined once and reused by later tasks; frontend DTO names match the gateway result kinds.
- **Scope:** The plan changes only the two requested repositories plus the explicit migration, config, tests, and coverage artifact. Existing business services and route contracts remain the execution boundary.

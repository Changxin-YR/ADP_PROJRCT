/**
 * t4 前端对抗性验证（verifier 独立编写，未改动产品代码）：
 * 把后端可能给出的「带机器标识」结果喂进真实 AgentPanel，断言渲染出来的 DOM
 * （气泡正文 + 确认卡片 + hover 追踪提示）里不出现 api./工具名/路径/HTTP 方法/
 * request_id/session_id/字段英文名/JSON 大括号，同时流式逐字与 404 回退不被破坏。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AgentPanel from '../src/layers/common/ui/AgentPanel.vue'
import { createSessionStore } from '../src/layers/common/session/session.store'

const user = {
  id: 1, phone: '13800000000', name: '测试用户', status: 'active' as const,
  roles: [{ id: 1, code: 'operator', name: '操作员' }], data_scopes: [],
  permissions: ['master_data.view', 'master_data.manage', 'production.manage'],
}

const MACHINE_TOKENS = ['api.', 'adp_query', 'adp_mutation', '/api/v1/', 'POST', 'PATCH', 'DELETE',
  'request_id', 'session_id', 'conversation_id', 'tool_name', 'expected_version', 'row_version',
  'weight_kg', 'pond_code', 'payload', '{', '}']

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/auth/login', component: { template: '<div />' } },
    ],
  })
}

const encoder = new TextEncoder()

function streamOf(lines: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`))
      controller.close()
    },
  })
  return new Response(body, { status, headers: { 'Content-Type': 'application/x-ndjson' } })
}

/** 打开面板 → 提交一句指令 → 用 NDJSON 流返回给定行。 */
async function submitStream(lines: string[], status = 200) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = String(input)
    if (path.includes('/auth/csrf')) {
      return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }))
    }
    return Promise.resolve(streamOf(lines, status))
  }))
  const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
  await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
  await wrapper.get('[aria-label="塘小助指令"]').setValue('帮我把这批投喂登记一下')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

/** 可见正文（不含 hover 的 title 提示）。 */
function panelText(wrapper: ReturnType<typeof mount>): string {
  return wrapper.get('[role="dialog"]').text()
}

/** hover 提示：只允许「追踪编号：xxx」，不允许再带标签本身。 */
function traceHints(wrapper: ReturnType<typeof mount>): string {
  return wrapper.findAll('.agent-message').map((node) => node.element.getAttribute('title') ?? '').join(' ')
}

afterEach(() => { createSessionStore().clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('t4 对抗性：面板渲染不得泄漏机器标识', () => {
  it('executed 结果（message/execution 里全是技术串）渲染成人话', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitStream([JSON.stringify({
      type: 'result',
      data: {
        kind: 'executed',
        message: 'POST /api/v1/production/feed-logs 已执行 weight_kg=20 request_id=req_9f8a7b6c',
        request_id: 'req_9f8a7b6c',
        execution: {
          title: 'api.production_create_post_api_v1_production_resource',
          detail: '{"code":"OK","tool_name":"adp_mutation"}',
          changes: [{ label: 'weight_kg', value: '20' }, { label: '塘口编码', value: 'TK-001' }],
          rows_changed: 1,
        },
      },
    })])

    const text = panelText(wrapper)
    for (const token of MACHINE_TOKENS) {
      expect(text, `渲染文本泄漏了 ${token}：${text.slice(0, 400)}`).not.toContain(token)
    }
    // 追踪编号只允许以「追踪编号：」形式出现在 hover 提示里，正文不许出现（含裸 id）。
    const hints = traceHints(wrapper)
    expect(hints).toContain('追踪编号：req_9f8a7b6c')
    expect(hints).not.toContain('request_id=')
    expect(hints).not.toContain('tool_name=')
    expect(text).not.toContain('req_9f8a7b6c')
    expect(wrapper.find('[data-testid="agent-cancel"]').exists()).toBe(false)
  })

  it('confirmation 卡片不展示 JSON，只展示中文动作/影响对象/填写内容', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitStream([JSON.stringify({
      type: 'result',
      data: {
        kind: 'confirmation_required',
        confirmation: {
          id: 7, token: 'tok', tool_name: 'api.production_create_post_api_v1_production_resource',
          summary: 'api.production_create_post_api_v1_production_resource',
          arguments: { resource: 'feed-logs', payload: { pond_code: 'TK-001', weight_kg: 20 } },
          risk: '风险管理数据 / 业务数据', risk_level: 'normal',
          expires_at: '2099-01-01T00:00:00', conversation_id: 'c-1', request_id: 'r-1',
        },
      },
    })])

    const card = wrapper.get('[data-testid="agent-confirmation"]')
    const text = `${card.text()} ${wrapper.get('[role="dialog"]').text()}`
    for (const token of MACHINE_TOKENS) {
      expect(text, `确认卡片泄漏了 ${token}：${text.slice(0, 400)}`).not.toContain(token)
    }
    expect(card.text()).toContain('即将执行')
    expect(card.text()).toContain('新增投喂记录')
    expect(card.text()).toContain('TK-001')
  })

  it('流式 delta 仍然逐字出现，状态行不受影响', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitStream([
      JSON.stringify({ type: 'status', text: '正在写入数据…' }),
      JSON.stringify({ type: 'delta', text: '刚才' }),
      JSON.stringify({ type: 'delta', text: '的投喂' }),
      JSON.stringify({ type: 'delta', text: '已经登记好了。' }),
      JSON.stringify({ type: 'result', data: { kind: 'executed', message: '刚才的投喂已经登记好了。' } }),
    ])

    const text = wrapper.get('[role="dialog"]').text()
    expect(text).toContain('刚才的投喂已经登记好了。')
    expect(text).not.toContain('{"type"')
  })

  it('流式不可用时回退到一次性接口', async () => {
    createSessionStore().setUser(user)
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      calls.push(path)
      if (path.includes('/auth/csrf')) {
        return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        }))
      }
      if (path.includes('/agent/turn/stream')) {
        return Promise.resolve(new Response('not found', { status: 404 }))
      }
      return Promise.resolve(new Response(JSON.stringify({
        code: 'OK', data: { kind: 'executed', message: '投喂登记完成。' },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }))

    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    await wrapper.get('[aria-label="塘小助指令"]').setValue('登记投喂')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="dialog"]').text()).toContain('投喂登记完成。')
    expect(calls.some((path) => path.includes('/agent/turn/stream'))).toBe(true)
    expect(calls.some((path) => path.endsWith('/agent/turn'))).toBe(true)
  })
})

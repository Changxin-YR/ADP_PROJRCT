import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AgentPanel from '../src/layers/common/ui/AgentPanel.vue'
import { createSessionStore } from '../src/layers/common/session/session.store'

const user = {
  id: 1, phone: '13800000000', name: '测试用户', status: 'active' as const,
  roles: [{ id: 1, code: 'operator', name: '操作员' }], data_scopes: [],
  permissions: ['master_data.view', 'master_data.manage'],
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/workbench', component: { template: '<div />' } }, { path: '/auth/login', component: { template: '<div />' } }] })
}

const encoder = new TextEncoder()

function streamOf(lines: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`))
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } })
}

/** 打开面板 → 提交一句指令 → 用 NDJSON 流返回给定的 result。 */
async function submitTurn(data: unknown) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = String(input)
    if (path.includes('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    return Promise.resolve(streamOf([JSON.stringify({ type: 'result', data })]))
  }))
  const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
  await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
  await wrapper.get('[aria-label="塘小助指令"]').setValue('帮我处理一下')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

afterEach(() => { createSessionStore().clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('AgentPanel', () => {
  it('opens from the compact launcher', async () => {
    createSessionStore().setUser(user)
    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    expect(wrapper.get('[aria-label="打开塘小助"]')).toBeTruthy()
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('塘小助')
    await wrapper.get('[role="dialog"]').trigger('keydown.esc')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('shows a confirmation and confirms only after explicit click', async () => {
    createSessionStore().setUser(user)
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      if (path.includes('/agent/turn')) return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { kind: 'confirmation_required', confirmation: { id: 2, token: 'once', tool_name: 'master_data.create_record', summary: '创建一号塘', arguments: { resource: 'ponds' }, risk: '需人工确认', expires_at: '2099-01-01T00:00:00', conversation_id: 'c-1', request_id: 'r-1' } }, request_id: 'r-1' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { kind: 'success', data: { id: 2 } }, request_id: 'r-2' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }))
    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    await wrapper.get('[aria-label="塘小助指令"]').setValue('创建一号塘')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-confirmation"]').text()).toContain('创建一号塘')
    expect(wrapper.find('[data-testid="agent-confirm"]').exists()).toBe(true)
    await wrapper.get('[data-testid="agent-confirm"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="agent-confirmation"]').exists()).toBe(false)
  })
  it('asks a clarifying question and sends the selected option as the next turn', async () => {
    createSessionStore().setUser(user)
    let turns = 0
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      turns += 1
      const data = turns === 1
        ? { kind: 'clarification', clarification: { question: '要查询哪个塘口？', options: ['1号塘', '2号塘'], allow_free_text: true }, conversation_id: 'c-9', request_id: 'r-9' }
        : { kind: 'assistant', message: '好的', conversation_id: 'c-9', request_id: 'r-10' }
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    await wrapper.get('[aria-label="塘小助指令"]').setValue('帮我查一下塘口')
    await wrapper.get('.agent-panel__composer').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-clarification"]').text()).toContain('要查询哪个塘口？')
    expect(wrapper.findAll('[data-testid="agent-clarification-option"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="agent-clarification-input"]').exists()).toBe(true)

    await wrapper.findAll('[data-testid="agent-clarification-option"]')[0].trigger('click')
    await flushPromises()

    const turnCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/agent/turn'))
    expect(turnCalls).toHaveLength(2)
    const sent = JSON.parse(String((turnCalls[1][1] as RequestInit).body)) as { message?: string; conversation_id?: string }
    expect(sent.message).toBe('1号塘')
    expect(sent.conversation_id).toBe('c-9')
    expect(wrapper.find('[data-testid="agent-clarification"]').exists()).toBe(false)
  })
  it('shows the tool status line while a tool runs and hides it when text resumes', async () => {
    createSessionStore().setUser(user)
    const encoder = new TextEncoder()
    let push!: (line: string) => void
    let finish!: () => void
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        push = (line: string) => controller.enqueue(encoder.encode(line))
        finish = () => controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) {
        return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      }
      return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }))
    }))
    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    await wrapper.get('[aria-label="塘小助指令"]').setValue('南区的塘口情况怎么样？')
    await wrapper.get('form').trigger('submit')

    push('{"type":"delta","text":"我先查一下"}\n')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toContain('我先查一下')

    push('{"type":"status","tool":"adp_query","text":"正在查询业务数据…"}\n')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('正在查询业务数据')
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toContain('我先查一下')

    push('{"type":"delta","text":"，查到了 4 个塘口"}\n')
    await flushPromises()
    expect(wrapper.find('[data-testid="agent-status"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toContain('查到了 4 个塘口')

    push('{"type":"result","data":{"kind":"assistant","message":"南区共 4 个塘口","conversation_id":"c-1"}}\n')
    finish()   // 流结束，前端才会把 result 交给 applyResult
    await flushPromises()
    expect(wrapper.text()).toContain('南区共 4 个塘口')
    expect(wrapper.find('[data-testid="agent-streaming"]').exists()).toBe(false)
  })

  it('renders a directly executed write as plain business wording', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitTurn({
      kind: 'executed',
      message: '已新增投喂记录：塘口「一号塘」，数量 120 kg。',
      execution: {
        title: '新增投喂记录',
        detail: '已新增投喂记录：塘口「一号塘」，数量 120 kg。',
        changes: [{ label: '塘口', value: '一号塘' }, { label: '数量', value: '120 kg' }],
        rows_changed: 1,
      },
      conversation_id: 'c-1',
      request_id: 'req_9f8e7d6c',
    })
    const bubble = wrapper.get('.agent-message--assistant')
    expect(bubble.text()).toContain('已新增投喂记录')
    expect(bubble.text()).toContain('塘口：一号塘')
    expect(bubble.attributes('title')).toContain('req_9f8e7d6c')
    const panelText = wrapper.text()
    for (const leak of ['{', '}', 'kind', 'execution', 'request_id', 'req_9f8e7d6c', 'api.']) expect(panelText).not.toContain(leak)
  })

  it('renders the confirmation card as a Chinese action plus key/value rows', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitTurn({
      kind: 'confirmation_required',
      confirmation: {
        id: 7,
        token: 'once',
        tool_name: 'api.production_create_post_api_v1_production_resource',
        summary: 'api.production_create_post_api_v1_production_resource',
        arguments: {
          resource: 'feed-logs', pond_code: 'TK-001', quantity: 120, weight_kg: 12.5,
          happened_at: '2026-01-01T08:30:00', request_id: 'req_abc123', expected_version: 3,
        },
        risk: '该操作会修改业务数据，确认后才会执行',
        risk_level: 'normal',
        expires_at: '2099-01-01T00:00:00',
        conversation_id: 'c-1',
        request_id: 'req_abc123',
      },
    })
    const card = wrapper.get('[data-testid="agent-confirmation"]')
    const text = card.text()
    expect(text).toContain('即将执行：新增投喂记录')
    expect(text).toContain('影响对象：TK-001')
    expect(text).toContain('对象类型')
    expect(text).toContain('投喂记录')
    expect(text).toContain('塘口编码')
    expect(text).toContain('数量')
    expect(text).toContain('发生时间')
    expect(text).toContain('2026-01-01 08:30')
    expect(card.find('pre').exists()).toBe(false)
    expect(card.find('[data-testid="agent-confirm"]').exists()).toBe(true)
    expect(card.find('[data-testid="agent-cancel"]').exists()).toBe(true)
    for (const leak of ['{', '}', 'api.', 'pond_code', 'request_id', 'req_abc123', 'JSON']) expect(text).not.toContain(leak)
  })

  it('renders the confirmation payload exactly as the backend sends it', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitTurn({
      kind: 'confirmation_required',
      message: '即将新增投喂记录，确认后立即生效。',
      confirmation: {
        id: 8,
        token: 'once',
        tool_name: 'api.production_create_post_api_v1_production_resource',
        summary: '新增投喂记录',
        target: '新增投喂记录',
        changes: [{ label: '塘口编码', value: 'TK-001' }, { label: '数量', value: '120' }],
        arguments: { resource: 'feed-logs', pond_code: 'TK-001', request_id: 'req-1' },
        risk: '这会改动业务数据',
        risk_level: 'normal',
        expires_at: '2099-01-01T00:00:00',
        conversation_id: 'c-1',
        request_id: 'req-1',
      },
    })
    expect(wrapper.get('.agent-message--assistant').text()).toContain('即将新增投喂记录，确认后立即生效。')
    const card = wrapper.get('[data-testid="agent-confirmation"]')
    expect(card.text()).toContain('即将执行：新增投喂记录')
    expect(card.text()).toContain('影响对象：TK-001')
    expect(card.text()).toContain('塘口编码')
    expect(card.text()).toContain('数量')
    expect(card.text()).not.toContain('改动业务数据')
    for (const leak of ['{', '}', 'api.', 'request_id', 'req-1', 'JSON']) expect(card.text()).not.toContain(leak)
  })

  it('summarizes a list result in plain Chinese without JSON', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitTurn({
      kind: 'success',
      data: { items: [{ pond_name: '一号塘', pond_code: 'TK-001', quantity: 1200 }, { pond_name: '二号塘' }], total: 2, page: 1, page_size: 20 },
      request_id: 'req_77aa88bb',
    })
    const bubble = wrapper.get('.agent-message--assistant').text()
    expect(bubble).toContain('共 2 条')
    expect(bubble).toContain('「一号塘」')
    expect(bubble).toContain('塘口编码 TK-001')
    expect(bubble).toContain('数量 1,200')
    for (const leak of ['{', '}', 'items', 'pond_name', 'page_size', 'req_77aa88bb']) expect(wrapper.text()).not.toContain(leak)
  })

  it('strips tool names, API paths and tracking ids from the assistant text', async () => {
    createSessionStore().setUser(user)
    const wrapper = await submitTurn({
      kind: 'assistant',
      message: '已通过 adp_mutation 调用 POST /api/v1/production/feed-logs 完成，request_id=req_9f8e7d6c，status=pending',
    })
    const bubble = wrapper.get('.agent-message--assistant').text()
    expect(bubble).toContain('新增生产记录')
    expect(bubble).toContain('状态：待确认')
    for (const leak of ['adp_mutation', '/api/v1', 'POST', 'request_id', 'req_9f8e7d6c', 'status=pending']) expect(wrapper.text()).not.toContain(leak)
  })

  it('keeps streaming deltas visible character by character', async () => {
    createSessionStore().setUser(user)
    const encoder = new TextEncoder()
    let push!: (line: string) => void
    let finish!: () => void
    const body = new ReadableStream<Uint8Array>({
      start(controller) { push = (line) => controller.enqueue(encoder.encode(line)); finish = () => controller.close() },
    })
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }))
    }))
    const wrapper = mount(AgentPanel, { global: { plugins: [router()] } })
    await wrapper.get('[aria-label="打开塘小助"]').trigger('click')
    await wrapper.get('[aria-label="塘小助指令"]').setValue('南区的塘口情况怎么样？')
    await wrapper.get('form').trigger('submit')

    push('{"type":"delta","text":"南"}\n')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toBe('南')
    push('{"type":"delta","text":"区"}\n')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toBe('南区')
    push('{"type":"status","tool":"adp_query","text":"正在查询业务数据…"}\n')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('正在查询业务数据')
    expect(wrapper.get('[data-testid="agent-streaming"]').text()).toBe('南区')

    push('{"type":"result","data":{"kind":"assistant","message":"南区共 4 个塘口","conversation_id":"c-1"}}\n')
    finish()
    await flushPromises()
    expect(wrapper.text()).toContain('南区共 4 个塘口')
    expect(wrapper.find('[data-testid="agent-streaming"]').exists()).toBe(false)
  })
})

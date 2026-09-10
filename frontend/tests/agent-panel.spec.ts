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
})

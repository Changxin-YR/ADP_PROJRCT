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
    expect(wrapper.get('[aria-label="打开智能助手"]')).toBeTruthy()
    await wrapper.get('[aria-label="打开智能助手"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('智能助手')
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
    await wrapper.get('[aria-label="打开智能助手"]').trigger('click')
    await wrapper.get('[aria-label="智能助手指令"]').setValue('创建一号塘')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-confirmation"]').text()).toContain('创建一号塘')
    expect(wrapper.find('[data-testid="agent-confirm"]').exists()).toBe(true)
    await wrapper.get('[data-testid="agent-confirm"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="agent-confirmation"]').exists()).toBe(false)
  })
})

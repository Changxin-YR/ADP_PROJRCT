import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import MaterialPage from '../src/layers/product/warehouse/MaterialPage.vue'


const submitted = {
  id: 8,
  code: 'MAT-008',
  name: '企业级膨化饲料',
  category: '饲料',
  unit: 'kg',
  status: 'submitted',
  row_version: 2,
  version: 2,
  allowed_actions: ['view', 'edit', 'verify'],
}

function response(data: unknown, status = 200, code = 'OK') {
  return Promise.resolve(new Response(JSON.stringify({ code, message: status >= 400 ? '主数据服务不可用' : '操作成功', data, request_id: 'master-test' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function mountPage() {
  return mount(MaterialPage, {
    global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('enterprise master data pages', () => {
  it('renders server records and server-supplied actions', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [submitted], page: 1, page_size: 20, total: 1, has_next: false })))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('企业级膨化饲料')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).toContain('核验')
    expect(wrapper.text()).not.toContain('删除')
  })

  it('shows an explicit API error without static fallback rows', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503, 'MASTER_UNAVAILABLE')))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('主数据加载失败')
    expect(wrapper.text()).not.toContain('鱼用膨化饲料')
  })

  it('keeps submitted data editable and makes verified data read-only', async () => {
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ path, method, body })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (method === 'PATCH') return response({ record: { ...submitted, ...body, row_version: 3, version: 3, allowed_actions: ['view', 'edit', 'verify'] } })
      if (path.endsWith('/verify')) return response({ record: { ...submitted, ...body, status: 'verified', row_version: 4, version: 4, allowed_actions: ['view'] } })
      return response({ items: [submitted], page: 1, page_size: 20, total: 1, has_next: false })
    }))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="master-action-edit"]').trigger('click')
    await wrapper.get('#master-name').setValue('核验前允许修改')
    await wrapper.get('[data-testid="master-save"]').trigger('click')
    await flushPromises()
    expect(calls.find((call) => call.method === 'PATCH')?.body).toMatchObject({ expected_version: 2, name: '核验前允许修改' })

    await wrapper.get('[data-testid="master-action-verify"]').trigger('click')
    await wrapper.get('[data-testid="master-confirm"]').trigger('click')
    await flushPromises()
    expect(calls.find((call) => call.path.endsWith('/verify'))?.body).toEqual({ expected_version: 3 })
    expect(wrapper.find('[data-testid="master-action-verify"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="master-action-edit"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('查看')
  })
})

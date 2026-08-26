import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import BatchDetailPage from '../src/layers/product/batches/BatchDetailPage.vue'
import BatchListPage from '../src/layers/product/batches/BatchListPage.vue'
import LossPage from '../src/layers/product/ponds-batches/LossPage.vue'


const submitted = {
  id: 21, code: 'LS-021', name: '疾病损耗', batch_id: 4, pond_id: 2,
  quantity: 12, weight_kg: 1.8, status: 'submitted', row_version: 2, version: 2,
  allowed_actions: ['view', 'edit', 'verify'],
}

function response(data: unknown, status = 200, code = 'OK') {
  return Promise.resolve(new Response(JSON.stringify({ code, message: status >= 400 ? '生产服务不可用' : '操作成功', data, request_id: 'production-test' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function mountPage() {
  return mount(LossPage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('enterprise production flow', () => {
  it('renders the batch status returned by the production API', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({
      items: [{ ...submitted, code: 'B-004', name: '四号批次', species: '鲈鱼', pond_id: 2, batch_status: 'farming' }],
      page: 1, page_size: 20, total: 1, has_next: false,
    })))

    const wrapper = mount(BatchListPage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.findAll('.status-badge').map((badge) => badge.text())).toContain('养殖中')
  })

  it('loads batch detail and reconciliation from production APIs', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/reconciliation')) return response({ batch_id: 4, quantity: 995, weight_kg: 198, difference: 0 })
      return response({ record: {
        id: 4, code: 'B-004', name: '四号批次', species: '鲈鱼', pond_id: 2,
        initial_quantity: 1000, initial_weight_kg: 200, current_quantity: 995,
        current_weight_kg: 198, batch_status: 'farming', status: 'verified',
        row_version: 3, version: 3, allowed_actions: ['view', 'correct'],
      } })
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/batches/:id', component: BatchDetailPage }] })
    await router.push('/batches/4'); await router.isReady()

    const wrapper = mount(BatchDetailPage, { global: { plugins: [router], stubs: { AppShell: { template: '<main><slot /></main>' } } } })
    await flushPromises()

    expect(paths).toContain('/api/v1/production/batches/4')
    expect(paths).toContain('/api/v1/production/batches/4/reconciliation')
    expect(wrapper.text()).toContain('四号批次')
    expect(wrapper.get('[data-testid="batch-reconciliation"]').text()).toContain('995')
    expect(wrapper.get('[data-testid="batch-reconciliation"]').text()).toContain('对账一致')
  })

  it('renders production facts from the API', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [submitted], page: 1, page_size: 20, total: 1, has_next: false })))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('疾病损耗')
    expect(wrapper.text()).toContain('待核验')
    expect(wrapper.find('[data-testid="production-action-edit"]').exists()).toBe(true)
  })

  it('shows an explicit error without demo fallback', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503, 'PRODUCTION_UNAVAILABLE')))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('生产数据加载失败')
    expect(wrapper.text()).not.toContain('疾病损耗')
  })

  it('edits a submitted loss then verifies its latest version with evidence', async () => {
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); const method = (init?.method ?? 'GET').toUpperCase()
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ path, method, body })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (method === 'PATCH') return response({ record: { ...submitted, ...body, row_version: 3, version: 3, allowed_actions: ['view', 'edit', 'verify'] } })
      if (path.endsWith('/verify')) return response({ record: { ...submitted, ...body, status: 'verified', row_version: 4, version: 4, allowed_actions: ['view', 'correct'] } })
      return response({ items: [submitted], page: 1, page_size: 20, total: 1, has_next: false })
    }))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="production-action-edit"]').trigger('click')
    await wrapper.get('#production-quantity').setValue('15')
    await wrapper.get('[data-testid="production-save"]').trigger('click')
    await flushPromises()
    expect(calls.find((call) => call.method === 'PATCH')?.body).toMatchObject({ expected_version: 2, quantity: 15 })

    await wrapper.get('[data-testid="production-action-verify"]').trigger('click')
    await wrapper.get('#production-evidence').setValue('91, 92')
    await wrapper.get('[data-testid="production-confirm"]').trigger('click')
    await flushPromises()
    expect(calls.find((call) => call.path.endsWith('/verify'))?.body).toEqual({ expected_version: 3, evidence_attachment_ids: [91, 92] })
    expect(wrapper.find('[data-testid="production-action-edit"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('更正')
  })

  it('creates a linked correction instead of editing the verified record', async () => {
    const verified = { ...submitted, status: 'verified', row_version: 4, version: 4, allowed_actions: ['view', 'correct'] }
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); const method = (init?.method ?? 'GET').toUpperCase()
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ path, method, body })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/corrections')) return response({ record: { ...verified, ...body, id: 22, status: 'draft', row_version: 1, version: 1, correction_of_id: 21, allowed_actions: ['view', 'edit', 'delete', 'submit'] } }, 201)
      return response({ items: [verified], page: 1, page_size: 20, total: 1, has_next: false })
    }))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="production-action-correct"]').trigger('click')
    expect(wrapper.find('[aria-label="生产记录编辑"]').exists()).toBe(true)
    expect(wrapper.find('label[for="production-note"]').text()).toContain('更正原因')
    await wrapper.get('#production-code').setValue('LS-021-C1')
    await wrapper.get('#production-quantity').setValue('10')
    await wrapper.get('#production-note').setValue('复核原始称重记录后更正')
    await wrapper.get('[data-testid="production-save"]').trigger('click')
    await flushPromises()

    expect(calls.find((call) => call.path.endsWith('/corrections'))?.body).toMatchObject({ expected_version: 4, code: 'LS-021-C1', quantity: 10, note: '复核原始称重记录后更正' })
    expect(wrapper.text()).toContain('LS-021-C1')
    expect(wrapper.text()).toContain('LS-021')
  })
})

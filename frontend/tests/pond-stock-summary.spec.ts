import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import PondListPage from '../src/layers/product/ponds/PondListPage.vue'
import PondDetailPage from '../src/layers/product/ponds/PondDetailPage.vue'


function response(data: unknown, status = 200, code = 'OK') {
  return Promise.resolve(new Response(JSON.stringify({
    code, message: status >= 400 ? '生产服务不可用' : '操作成功', data, request_id: 'pond-stock-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}

const page = (items: unknown[], extra: Record<string, unknown> = {}) => ({
  items, page: 1, page_size: 100, total: items.length, has_next: false, ...extra,
})

const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }

const pondRecord = (id: number, name: string, stockQuantity: number | null) => ({
  id, code: `P-${id}`, name, area_id: 1, pond_status: 'farming', status: 'verified',
  capacity_mu: 12, species: '南美白对虾', row_version: 2, version: 2, allowed_actions: ['view'],
  stock_quantity: stockQuantity,
})

const listRow = (pondId: number, overrides: Record<string, unknown> = {}) => ({
  pond_id: pondId, pond_code: `P-${pondId}`, pond_name: `${pondId} 号塘`, pond_status: 'farming',
  batch_stock: { quantity: '1200.000', weight_kg: '25.500' },
  manual_stock: { quantity: '9000.000', current_spec: '400g/尾' },
  batch_count: 2, latest_sampling: { document_id: 9, occurred_at: '2026-06-02T08:00:00' },
  data_source: 'batch_ledger', ...overrides,
})

const router = async (path: string) => {
  const instance = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ponds', component: { template: '<div />' } },
      { path: '/ponds/:id', component: { template: '<div />' } },
    ],
  })
  await instance.push(path)
  await instance.isReady()
  return instance
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('pond stock summary from production facts', () => {
  it('renders ledger aggregated stock on the pond list and marks the source', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/master-data/ponds?page=1&page_size=100')) return response(page([pondRecord(101, '东港一号塘', 9000)]))
      if (path.includes('/master-data/areas')) return response(page([]))
      if (path.includes('/master-data/pond-groups')) return response(page([]))
      if (path.startsWith('/api/v1/production/ponds/stock-summary')) return response(page([listRow(101)]))
      return response(page([]))
    }))

    const wrapper = mount(PondListPage, { global: { plugins: [await router('/ponds')] } })
    await flushPromises()

    expect(paths).toContain('/api/v1/production/ponds/stock-summary?pond_ids=101')
    expect(wrapper.get('[data-testid="pond-list-stock"]')).toBeTruthy()
    const cell = wrapper.get('[data-testid="pond-list-stock"]')
    expect(cell.text()).toContain('1,200 尾')
    expect(cell.text()).toContain('批次流水')
    expect(wrapper.text()).toContain('存塘量（批次流水）')
    expect(wrapper.find('[data-testid="pond-list-stock-error"]').exists()).toBe(false)
  })

  it('falls back to the archive value only when there is no batch ledger', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/master-data/ponds?page=1&page_size=100')) return response(page([pondRecord(101, '东港一号塘', 9000)]))
      if (path.startsWith('/api/v1/production/ponds/stock-summary')) {
        return response(page([listRow(101, { data_source: 'manual', batch_stock: { quantity: '0.000', weight_kg: '0.000' } })]))
      }
      return response(page([]))
    }))

    const wrapper = mount(PondListPage, { global: { plugins: [await router('/ponds')] } })
    await flushPromises()

    const cell = wrapper.get('[data-testid="pond-list-stock"]')
    expect(cell.text()).toContain('9,000 尾')
    expect(cell.text()).toContain('档案手工值')
    expect(cell.text()).not.toContain('批次流水')
  })

  it('never falls back to archive numbers when the summary API fails', async () => {
    let fail = true
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.startsWith('/api/v1/production/ponds/stock-summary')) {
        if (!fail) return response(page([listRow(101, { data_source: 'none', manual_stock: { quantity: null, current_spec: null } })]))
        return Promise.resolve(new Response(JSON.stringify({
          code: 'PRODUCTION_UNAVAILABLE', message: '存塘量汇总服务暂时不可用', data: null, request_id: 'pond-stock-503',
        }), { status: 503, headers: { 'Content-Type': 'application/json' } }))
      }
      if (path.endsWith('/master-data/ponds?page=1&page_size=100')) return response(page([pondRecord(101, '东港一号塘', 9000)]))
      return response(page([]))
    }))

    const wrapper = mount(PondListPage, { global: { plugins: [await router('/ponds')] } })
    await flushPromises()

    const alert = wrapper.get('[data-testid="pond-list-stock-error"]')
    expect(alert.text()).toContain('存塘量（批次流水）加载失败')
    // 接口失败时该列不渲染任何数字；恢复后仍为「—」，绝不回落到档案手工值 9000
    expect(wrapper.find('[data-testid="pond-list-stock"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('9,000')

    fail = false
    await wrapper.get('[data-testid="pond-list-stock-retry"]').trigger('click')
    await flushPromises()

    const cell = wrapper.get('[data-testid="pond-list-stock"]')
    expect(cell.text()).toContain('—')
    expect(cell.text()).toContain('无数据')
    expect(cell.text()).not.toContain('9,000')
  })

  // 线上真实故障：GET /api/v1/production/ponds/stock-summary -> 404 {"code":"NOT_FOUND","message":"请求的资源不存在"}
  it('degrades in plain Chinese when the summary route is missing (404)', async () => {
    let fail = true
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.startsWith('/api/v1/production/ponds/stock-summary')) {
        if (!fail) return response(page([listRow(101)]))
        return Promise.resolve(new Response(JSON.stringify({
          code: 'NOT_FOUND', message: '请求的资源不存在', data: null, request_id: 'live-404-request-id',
        }), { status: 404, headers: { 'Content-Type': 'application/json' } }))
      }
      if (path.endsWith('/master-data/ponds?page=1&page_size=100')) return response(page([pondRecord(101, '东港一号塘', 9000)]))
      return response(page([]))
    }))

    const wrapper = mount(PondListPage, { global: { plugins: [await router('/ponds')] } })
    await flushPromises()

    const alert = wrapper.get('[data-testid="pond-list-stock-error"]')
    expect(alert.text()).toContain('存塘量（批次流水）加载失败')
    // 通俗文案：HTTP 状态码/request_id/接口等技术术语绝不出现
    for (const banned of ['HTTP', '404', 'request_id', 'JSON', '接口']) {
      expect(alert.text()).not.toContain(banned)
    }
    // 失败态下不渲染存塘量列，也不把档案手工值 9000 当生产事实展示
    expect(wrapper.find('[data-testid="pond-list-stock"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('9,000')

    fail = false
    await wrapper.get('[data-testid="pond-list-stock-retry"]').trigger('click')
    await flushPromises()

    // 「重新加载」把页面带回正常态：显示批次流水事实，故障提示消失
    const recovered = wrapper.get('[data-testid="pond-list-stock"]')
    expect(recovered.text()).toContain('1,200 尾')
    expect(recovered.text()).toContain('批次流水')
    expect(wrapper.find('[data-testid="pond-list-stock-error"]').exists()).toBe(false)
  })

  it('never shows a server request id or status code to the user on 5xx failures', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.startsWith('/api/v1/production/ponds/stock-summary')) {
        return Promise.resolve(new Response(JSON.stringify({
          code: 'DB_UNAVAILABLE', message: '数据库服务暂时不可用', data: null, request_id: 'a4f06718e09b4f75af49a6614041ad11',
        }), { status: 503, headers: { 'Content-Type': 'application/json' } }))
      }
      if (path.endsWith('/master-data/ponds?page=1&page_size=100')) return response(page([pondRecord(101, '东港一号塘', 9000)]))
      return response(page([]))
    }))

    const wrapper = mount(PondListPage, { global: { plugins: [await router('/ponds')] } })
    await flushPromises()

    const alert = wrapper.get('[data-testid="pond-list-stock-error"]')
    expect(alert.text()).toContain('存塘量（批次流水）加载失败')
    expect(alert.text()).toContain('请稍后重试')
    expect(alert.text()).not.toContain('a4f06718e09b4f75af49a6614041ad11')
    expect(alert.text()).not.toContain('503')
    expect(alert.text()).not.toContain('request_id')
    expect(wrapper.get('[data-testid="pond-list-stock-retry"]').text()).toContain('重新加载存塘量')
    expect(wrapper.text()).not.toContain('9,000')
  })

  it('renders read-only ledger stock, batch distribution and latest sampling on the detail page', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/master-data/ponds/101')) {
        return response({ record: { ...pondRecord(101, '东港一号塘', 1200), manager_name: '周经理', location_text: '东区', description: '', timeline_preview: [] } })
      }
      if (path.endsWith('/production/ponds/101/stock-summary')) {
        return response({
          pond_id: 101, pond_code: 'P-101', pond_name: '东港一号塘', pond_status: 'farming',
          batch_stock: { quantity: '1200.000', weight_kg: '25.500' },
          manual_stock: { quantity: '1200.000', current_spec: '400g/尾' },
          batches: [
            { batch_id: 1, code: 'B-001', name: '春季虾一批', batch_status: 'farming', quantity: '700.000', weight_kg: '14.000', avg_weight_kg: '0.020' },
            { batch_id: 2, code: 'B-002', name: '春季虾二批', batch_status: 'stocked', quantity: '500.000', weight_kg: '11.500', avg_weight_kg: '0.023' },
          ],
          latest_sampling: { document_id: 9, occurred_at: '2026-06-02T08:00:00', quantity: '40.000', weight_kg: '11.000', avg_weight_kg: '0.275' },
          data_source: 'batch_ledger',
        })
      }
      return response(page([]))
    }))

    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/101')], ...globals } })
    await flushPromises()

    expect(paths).toContain('/api/v1/production/ponds/101/stock-summary')
    expect(wrapper.get('[data-testid="pond-stock-ledger-quantity"]').text()).toBe('1,200 尾')
    expect(wrapper.get('[data-testid="pond-stock-ledger-weight"]').text()).toBe('25.5 kg')
    expect(wrapper.get('[data-testid="pond-stock-batch-count"]').text()).toContain('2')
    expect(wrapper.text()).toContain('B-001')
    expect(wrapper.text()).toContain('700 尾')
    expect(wrapper.text()).toContain('养殖中')
    expect(wrapper.get('[data-testid="pond-stock-sampling"]').text()).toContain('0.275 kg/尾')
    expect(wrapper.get('[data-testid="pond-stock-sampling"]').text()).toContain('2026-06-02T08:00:00')
    // 档案手工值仍展示，但标注为仅供参考
    expect(wrapper.get('[data-testid="pond-stock-manual-quantity"]').text()).toBe('1,200 尾')
    expect(wrapper.find('[data-testid="pond-stock-mismatch"]').exists()).toBe(false)
  })

  it('hints when the archive value disagrees with the batch ledger without red-flagging', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/master-data/ponds/101')) {
        return response({ record: { ...pondRecord(101, '东港一号塘', 9000), timeline_preview: [] } })
      }
      if (path.endsWith('/production/ponds/101/stock-summary')) {
        return response({
          pond_id: 101, pond_code: 'P-101', pond_name: '东港一号塘', pond_status: 'farming',
          batch_stock: { quantity: '1200.000', weight_kg: '25.500' },
          manual_stock: { quantity: '9000.000', current_spec: '400g/尾' },
          batches: [], latest_sampling: null, data_source: 'batch_ledger',
        })
      }
      return response(page([]))
    }))

    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/101')], ...globals } })
    await flushPromises()

    const hint = wrapper.get('[data-testid="pond-stock-mismatch"]')
    expect(hint.text()).toContain('不一致')
    expect(hint.text()).toContain('建议以批次流水为准')
    // 提示是克制的 status 文本，不是 role=alert 的红色报错
    expect(hint.attributes('role')).toBe('status')
    expect(wrapper.get('[data-testid="pond-stock-ledger-quantity"]').text()).toBe('1,200 尾')
  })

  it('explains missing data and shows an explicit error when the detail summary API fails', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/master-data/ponds/101')) {
        return response({ record: { ...pondRecord(101, '东港一号塘', null), timeline_preview: [] } })
      }
      if (path.endsWith('/production/ponds/101/stock-summary')) return Promise.resolve(new Response(JSON.stringify({
        code: 'FORBIDDEN', message: '当前账号没有权限执行该操作', data: null, request_id: 'pond-stock-403',
      }), { status: 403, headers: { 'Content-Type': 'application/json' } }))
      return response(page([]))
    }))

    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/101')], ...globals } })
    await flushPromises()

    const alert = wrapper.get('[data-testid="pond-stock-error"]')
    expect(paths).toContain('/api/v1/production/ponds/101/stock-summary')
    expect(alert.text()).toContain('当前账号没有权限执行该操作')
    expect(alert.attributes('role')).toBe('alert')
    // 汇总失败时绝不显示任何存塘量数字（含档案手工值）
    expect(wrapper.find('[data-testid="pond-stock-ledger-quantity"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="pond-stock-manual-quantity"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('9,000 尾')
  })

  // 线上真实故障：详情页 GET /production/ponds/{id}/stock-summary -> 404 NOT_FOUND
  it('explains a missing summary route in plain Chinese and recovers via 重新加载', async () => {
    let fail = true
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/master-data/ponds/101')) {
        return response({ record: { ...pondRecord(101, '东港一号塘', 9000), timeline_preview: [] } })
      }
      if (path.endsWith('/production/ponds/101/stock-summary')) {
        if (!fail) return response({
          pond_id: 101, pond_code: 'P-101', pond_name: '东港一号塘', pond_status: 'farming',
          batch_stock: { quantity: '1200.000', weight_kg: '25.500' },
          manual_stock: { quantity: '9000.000', current_spec: '400g/尾' },
          batches: [], latest_sampling: null, data_source: 'batch_ledger',
        })
        return Promise.resolve(new Response(JSON.stringify({
          code: 'NOT_FOUND', message: '请求的资源不存在', data: null, request_id: 'live-404-detail',
        }), { status: 404, headers: { 'Content-Type': 'application/json' } }))
      }
      return response(page([]))
    }))

    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/101')], ...globals } })
    await flushPromises()

    const alert = wrapper.get('[data-testid="pond-stock-error"]')
    expect(alert.text()).toContain('存塘量（批次流水）加载失败')
    expect(alert.text()).toContain('请求的资源不存在')
    for (const banned of ['HTTP', '404', 'request_id', 'JSON', '接口']) {
      expect(alert.text()).not.toContain(banned)
    }
    // 失败态：既没有批次流水数字，也没有档案手工值 9000
    expect(wrapper.find('[data-testid="pond-stock-ledger-quantity"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="pond-stock-manual-quantity"]').exists()).toBe(false)
    const stockCard = wrapper.get('[aria-label="存塘量生产事实汇总"]')
    expect(stockCard.text()).not.toContain('9,000')
    // 档案基础资料里的「档案手工存塘量」是档案字段，允许展示，但必须标注为档案值而非生产事实
    expect(wrapper.get('[data-testid="pond-stock-quantity"]').text()).toBe('9,000 尾')

    fail = false
    await wrapper.get('[data-testid="pond-stock-retry"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="pond-stock-ledger-quantity"]').text()).toBe('1,200 尾')
    expect(wrapper.find('[data-testid="pond-stock-error"]').exists()).toBe(false)
  })

  it('tells the truth when neither ledger nor archive value exists', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/master-data/ponds/101')) {
        return response({ record: { ...pondRecord(101, '东港一号塘', null), timeline_preview: [] } })
      }
      if (path.endsWith('/production/ponds/101/stock-summary')) {
        return response({
          pond_id: 101, pond_code: 'P-101', pond_name: '东港一号塘', pond_status: 'farming',
          batch_stock: { quantity: '0.000', weight_kg: '0.000' },
          manual_stock: { quantity: null, current_spec: null },
          batches: [], latest_sampling: null, data_source: 'none',
        })
      }
      return response(page([]))
    }))

    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/101')], ...globals } })
    await flushPromises()

    expect(wrapper.get('[data-testid="pond-stock-ledger-quantity"]').text()).toBe('0 尾')
    expect(wrapper.get('[data-testid="pond-stock-manual-quantity"]').text()).toBe('—')
    expect(wrapper.text()).toContain('暂无数据')
    expect(wrapper.text()).toContain('暂无已核验抽样记录')
    expect(wrapper.find('[data-testid="pond-stock-mismatch"]').exists()).toBe(false)
  })
})

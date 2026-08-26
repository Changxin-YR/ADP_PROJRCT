import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import StockInPage from '../src/layers/product/warehouse/StockInPage.vue'
import StockLedgerPage from '../src/layers/product/warehouse/StockLedgerPage.vue'
import StockOutPage from '../src/layers/product/warehouse/StockOutPage.vue'
import StockTransferPage from '../src/layers/product/warehouse/StockTransferPage.vue'
import StockAlertPage from '../src/layers/product/warehouse/StockAlertPage.vue'
import WarehouseMasterPage from '../src/layers/product/warehouse/WarehouseMasterPage.vue'
import { createSessionStore } from '../src/layers/common/session/session.store'


const submitted = {
  id: 31, code: 'IN-031', name: '三号仓采购入库', warehouse_id: 3, warehouse_name: '三号仓',
  material_id: 8, material_name: '鲈鱼配合饲料', quantity: 50, lot_no: 'LOT-0831',
  expiry_date: '2027-02-28', status: 'submitted', row_version: 2, version: 2,
  allowed_actions: ['view', 'edit', 'verify'],
}

function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify({
    code: status >= 400 ? 'WAREHOUSE_UNAVAILABLE' : 'OK',
    message: status >= 400 ? '仓储服务不可用' : '操作成功', data, request_id: 'warehouse-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}

const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('enterprise warehouse flow', () => {
  it('loads submitted receipts and server actions from the warehouse API', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      paths.push(String(input))
      return response({ items: [submitted], page: 1, page_size: 20, total: 1, has_next: false })
    }))

    const wrapper = mount(StockInPage, { global: globals })
    await flushPromises()

    expect(paths).toContain('/api/v1/warehouse/receipts')
    expect(wrapper.text()).toContain('三号仓采购入库')
    expect(wrapper.text()).toContain('待核验')
    expect(wrapper.find('[data-testid="warehouse-action-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="warehouse-action-verify"]').exists()).toBe(true)
  })

  it('renders immutable ledger rows from the ledger API', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({
      items: [{ id: 91, source_type: 'receipt', source_id: 31, quantity_delta: 50, material_name: '鲈鱼配合饲料', lot_no: 'LOT-0831', warehouse_name: '三号仓', happened_at: '2026-08-17 02:00' }],
      page: 1, page_size: 50, total: 1, has_next: false,
    })))

    const wrapper = mount(StockLedgerPage, { global: globals })
    await flushPromises()

    expect(wrapper.text()).toContain('鲈鱼配合饲料')
    expect(wrapper.text()).toContain('LOT-0831')
    expect(wrapper.text()).toContain('50')
    expect(wrapper.text()).not.toContain('编辑')
    expect(wrapper.text()).not.toContain('删除')
  })

  it('shows an explicit error without warehouse demo fallback', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503)))

    const wrapper = mount(StockInPage, { global: globals })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('仓储数据加载失败')
    expect(wrapper.text()).not.toContain('三号仓采购入库')
  })

  it('opens a linked correction form for a verified receipt', async () => {
    const verified = { ...submitted, status: 'verified', row_version: 3, version: 3, allowed_actions: ['view', 'correct'] }
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [verified], page: 1, page_size: 20, total: 1, has_next: false })))
    const wrapper = mount(StockInPage, { global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="warehouse-action-correct"]').trigger('click')

    expect(wrapper.find('[aria-label="仓储记录编辑"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('更正原因')
  })

  it('provides the issue-request workflow on the stock-out page', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      paths.push(String(input))
      return response({ items: [], page: 1, page_size: 20, total: 0, has_next: false })
    }))
    const wrapper = mount(StockOutPage, { global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="warehouse-mode-request"]').trigger('click')
    await flushPromises()

    expect(paths).toContain('/api/v1/warehouse/issue-requests')
  })

  it('keeps transferred stock in transit until a separate receipt action', async () => {
    const paths: string[] = []
    const transfer = {
      ...submitted, id: 41, code: 'TR-041', status: 'submitted', quantity: 10,
      warehouse_name: '一号仓', target_warehouse_name: '二号仓', allowed_actions: ['view', 'dispatch'],
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/dispatch')) return response({ record: { ...transfer, status: 'in_transit', version: 3, row_version: 3, allowed_actions: ['view', 'receive', 'cancel'] } })
      if (path.endsWith('/receive')) return response({ record: { ...transfer, status: 'verified', version: 4, row_version: 4, allowed_actions: ['view', 'correct'] } })
      return response({ items: [transfer], page: 1, page_size: 20, total: 1, has_next: false })
    }))
    const wrapper = mount(StockTransferPage, { global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="warehouse-action-dispatch"]').trigger('click')
    await wrapper.get('[data-testid="warehouse-confirm"]').trigger('click')
    await flushPromises()
    expect(paths).toContain('/api/v1/warehouse/transfers/41/dispatch')

    await wrapper.get('[data-testid="warehouse-action-receive"]').trigger('click')
    await wrapper.get('[data-testid="warehouse-confirm"]').trigger('click')
    await flushPromises()
    expect(paths).toContain('/api/v1/warehouse/transfers/41/receive')
  })

  it('opens a governed resolution form for a real inventory alert', async () => {
    createSessionStore().setUser({ id: 1, phone: '13800000000', name: '仓储管理员', status: 'active', roles: [{ id: 4, code: 'warehouse_manager', name: '仓储管理员' }], data_scopes: [], permissions: ['warehouse.view', 'warehouse.manage', 'workbench.enter'] })
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [{
      id: 8, alert_key: '3:8:low_stock', material_name: '鲈鱼饲料', lot_no: 'LOT-8',
      warehouse_name: '三号仓', alert_type: 'low_stock', severity: 'high', current_quantity: 2,
      safety_stock: 10, status: 'pending', allowed_actions: ['handle'],
    }] })))
    const wrapper = mount(StockAlertPage, { global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="warehouse-alert-action-handle"]').trigger('click')

    expect(wrapper.find('[aria-label="库存预警处理"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('处理结论')
  })

  it('lists disabled warehouse masters and supports editing their lifecycle status', async () => {
    const paths: string[] = []
    const requests: Array<{ path: string; body: string | undefined }> = []
    const disabled = { id: 5, organization_id: 1, farm_id: 2, area_id: 3, code: 'W-005', name: '备用仓', location: '北侧', status: 'disabled' }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      paths.push(path)
      requests.push({ path, body: init?.body as string | undefined })
      if (path === '/api/v1/auth/csrf') return response({ csrf_token: 'csrf' })
      if (path.includes('/master-data/farms')) return response({ items: [{ id: 2, name: '一号基地' }] })
      if (path.includes('/master-data/areas')) return response({ items: [{ id: 3, name: '北区' }] })
      if (path.includes('include_disabled=1')) return response({ items: [disabled] })
      if (path.endsWith('/warehouses/5')) return response({ warehouse: { ...disabled, status: 'active' } })
      return response({ items: [] })
    }))

    const wrapper = mount(WarehouseMasterPage, { global: globals })
    await flushPromises()

    expect(paths).toContain('/api/v1/warehouse/warehouses?include_disabled=1')
    expect(wrapper.text()).toContain('备用仓')
    await wrapper.get('[data-testid="warehouse-master-action-edit"]').trigger('click')
    expect(wrapper.find('[aria-label="编辑仓库"]').exists()).toBe(true)

    await wrapper.get('#warehouse-status').setValue('active')
    await wrapper.get('[data-testid="warehouse-master-save"]').trigger('click')
    await flushPromises()

    expect(requests.find((request) => request.path.endsWith('/warehouses/5'))?.body).toContain('"status":"active"')
    expect(wrapper.text()).toContain('active')
  })
})

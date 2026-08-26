import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import SalePage from '../src/layers/product/sales/SalePage.vue'
import ReceivablePage from '../src/layers/product/sales/ReceivablePage.vue'


function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify({
    code: status >= 400 ? 'SALES_UNAVAILABLE' : 'OK', message: status >= 400 ? '销售服务不可用' : '操作成功',
    data, request_id: 'sales-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}
const page = (items: unknown[], extra: Record<string, unknown> = {}) => ({ items, page: 1, page_size: 20, total: items.length, has_next: false, ...extra })
const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }
const order = { id: 21, code: 'SO-021', name: '鲈鱼销售', customer_id: 4, customer_name: '杭州水产', pond_id: 2,
  pond_name: '一号塘', batch_id: 3, batch_code: 'B-003', species: '鲈鱼', quantity: 100, delivered_quantity: 0,
  unit: 'kg', unit_price: 26, total_amount: 2600, received_amount: 0, due_date: '2026-09-17', status: 'submitted',
  row_version: 2, version: 2, allowed_actions: ['view', 'edit', 'approve', 'cancel'] }

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('enterprise sales receivable and receipt flow', () => {
  it('loads governed sales facts and selectors without dataset fallback', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/sales/orders')) return response(page([order]))
      if (path.endsWith('/sales/deliveries')) return response(page([]))
      if (path.includes('/master-data/customers')) { const second = path.includes('page=2'); return response(page(second ? [{ id: 5, code: 'C5', name: '第二页客户', status: 'verified' }] : [{ id: 4, code: 'C4', name: '杭州水产', status: 'verified' }], { page: second ? 2 : 1, total: 101, has_next: !second })) }
      if (path.includes('/master-data/ponds')) return response(page([{ id: 2, code: 'P2', name: '一号塘', status: 'verified' }]))
      if (path.includes('/production/batches')) return response(page([{ id: 3, code: 'B-003', name: '鲈鱼批次', status: 'verified' }]))
      if (path.includes('/production/harvests')) return response(page([]))
      return response(page([]))
    }))
    const wrapper = mount(SalePage, { global: globals }); await flushPromises()
    expect(paths).toEqual(expect.arrayContaining(['/api/v1/sales/orders', '/api/v1/sales/deliveries', '/api/v1/master-data/customers?page_size=100&status=verified&page=1']))
    expect(paths.some((path) => path.includes('/master-data/customers') && path.includes('page=2'))).toBe(true)
    expect(wrapper.text()).toContain('SO-021')
    expect(wrapper.find('[data-testid="sales-order-action-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="sales-order-action-approve"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('SAL-2026-0818')
  })

  it('shows explicit sales API failure instead of demo rows', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503)))
    const wrapper = mount(SalePage, { global: globals }); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('销售数据加载失败')
    expect(wrapper.text()).not.toContain('宁波海鲜市场')
  })

  it('refreshes the sales order after delivery verification', async () => {
    let orderLoads = 0
    let verified = false
    const delivery = { id: 51, code: 'DL-051', name: '鲈鱼交付', sales_order_id: 21, order_code: 'SO-021',
      harvest_document_id: 61, customer_name: '杭州水产', quantity: 100, delivered_at: '2026-08-20T10:00',
      status: 'submitted', version: 2, row_version: 2, allowed_actions: ['view', 'edit', 'verify', 'cancel'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/deliveries/51/verify')) { verified = true; return response({ record: { ...delivery, status: 'verified', version: 3, allowed_actions: ['view', 'correct'] } }) }
      if (path.endsWith('/sales/orders')) { orderLoads += 1; return response(page([{ ...order, status: verified ? 'fully_delivered' : 'approved', allowed_actions: ['view'] }])) }
      if (path.includes('/sales/orders?')) return response(page([{ ...order, status: verified ? 'fully_delivered' : 'approved', allowed_actions: ['view'] }]))
      if (path.endsWith('/sales/deliveries')) return response(page([delivery]))
      return response(page([]))
    }))
    const wrapper = mount(SalePage, { global: globals }); await flushPromises()
    await wrapper.get('[data-testid="sales-tab-deliveries"]').trigger('click')
    await wrapper.get('[data-testid="sales-delivery-action-verify"]').trigger('click')
    await wrapper.get('#sales-evidence').setValue('18')
    await wrapper.get('[data-testid="sales-confirm"]').trigger('click'); await flushPromises()
    expect(orderLoads).toBe(2)
    const create = wrapper.findAll('button').find((button) => button.text().includes('登记交付'))
    await create!.trigger('click')
    expect(wrapper.get('#sales-sales_order_id').text()).not.toContain('SO-021')
  })

  it('loads receivables and reverses a verified receipt append-only', async () => {
    const paths: string[] = []
    let receivableLoads = 0
    let reversed = false
    const receipt = { id: 41, code: 'RC-041', name: '客户收款', receivable_id: 31, customer_name: '杭州水产', amount: 600,
      received_at: '2026-08-20', receipt_method: 'bank_transfer', status: 'verified', version: 3, row_version: 3,
      allowed_actions: ['view', 'reverse'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/reverse')) { reversed = true; return response({ record: { ...receipt, reversal_id: 9, allowed_actions: ['view'] } }) }
      if (path.endsWith('/receivables')) { receivableLoads += 1; return response(page([{ id: 31, order_code: 'SO-021', customer_name: '杭州水产', amount: 2600, received_amount: 600, balance: 2000, due_date: '2026-09-17', overdue_days: -28, status: 'partial' }], { summary: { total_amount: 12600, total_balance: 8200, overdue_count: 4 } })) }
      if (path.endsWith('/receipts')) return response(page([{ ...receipt, ...(reversed ? { reversal_id: 9, allowed_actions: ['view'] } : {}) }]))
      return response(page([]))
    }))
    const wrapper = mount(ReceivablePage, { global: globals }); await flushPromises()
    expect(wrapper.text()).toContain('12600')
    expect(wrapper.text()).toContain('8200')
    await wrapper.get('[data-testid="sales-tab-receipts"]').trigger('click')
    expect(wrapper.find('[data-testid="sales-receipt-action-edit"]').exists()).toBe(false)
    await wrapper.get('[data-testid="sales-receipt-action-reverse"]').trigger('click')
    await wrapper.get('#receipt-reversal-reason').setValue('银行退回原收款')
    await wrapper.get('#receipt-evidence').setValue('19')
    await wrapper.get('[data-testid="receipt-confirm"]').trigger('click'); await flushPromises()
    expect(paths).toContain('/api/v1/sales/receipts/41/reverse')
    expect(wrapper.text()).toContain('已冲销')
    expect(receivableLoads).toBe(2)
  })

  it('loads every receivable page for the receipt source selector', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/receivables?')) {
        const second = path.includes('page=2')
        return response(page(second
          ? [{ id: 131, order_code: 'SO-131', customer_name: '第二页客户', amount: 500, received_amount: 0, balance: 500, due_date: '2026-09-20', overdue_days: -30, status: 'unpaid', source_delivery_id: 231 }]
          : [{ id: 31, order_code: 'SO-031', customer_name: '第一页客户', amount: 300, received_amount: 0, balance: 300, due_date: '2026-09-20', overdue_days: -30, status: 'unpaid', source_delivery_id: 131 }],
        { page: second ? 2 : 1, page_size: 100, total: 101, has_next: !second }))
      }
      if (path.endsWith('/receivables')) return response(page([], { summary: { total_amount: 0, total_balance: 0, overpaid_amount: 0, overdue_count: 0 } }))
      if (path.endsWith('/receipts')) return response(page([]))
      return response(page([]))
    }))
    const wrapper = mount(ReceivablePage, { global: globals }); await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('登记收款'))!.trigger('click')
    expect(paths.some((path) => path.includes('/receivables?') && path.includes('page=2'))).toBe(true)
    expect(wrapper.get('#receipt-receivable_id').text()).toContain('SO-131')
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import PurchasePage from '../src/layers/product/purchase/PurchasePage.vue'
import PayablePage from '../src/layers/product/purchase/PayablePage.vue'
import StockInPage from '../src/layers/product/warehouse/StockInPage.vue'


function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify({
    code: status >= 400 ? 'PURCHASE_UNAVAILABLE' : 'OK',
    message: status >= 400 ? '采购服务不可用' : '操作成功', data, request_id: 'purchase-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}

const order = {
  id: 21, code: 'PO-021', name: '鲈鱼饲料采购', supplier_id: 4, supplier_name: '海源饲料',
  material_id: 8, material_name: '鲈鱼配合料', warehouse_id: 3, warehouse_name: '主仓',
  quantity: 100, received_quantity: 0, unit_price: 5.2, total_amount: 520, paid_amount: 0,
  due_date: '2026-09-20', status: 'submitted', row_version: 2, version: 2,
  allowed_actions: ['view', 'edit', 'approve', 'cancel'],
}

const page = (items: unknown[]) => ({ items, page: 1, page_size: 20, total: items.length, has_next: false })
const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('enterprise purchase and payable flow', () => {
  it('loads purchase orders and server-governed actions from the API', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path === '/api/v1/purchase/orders') return response(page([order]))
      return response(page([]))
    }))

    const wrapper = mount(PurchasePage, { global: globals })
    await flushPromises()

    expect(paths).toContain('/api/v1/purchase/orders')
    expect(wrapper.text()).toContain('鲈鱼饲料采购')
    expect(wrapper.text()).toContain('待审批')
    expect(wrapper.find('[data-testid="purchase-action-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="purchase-action-approve"]').exists()).toBe(true)
  })

  it('approves the latest submitted purchase version through the API', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/approve')) return response({ record: { ...order, status: 'approved', version: 3, row_version: 3, allowed_actions: ['view', 'cancel'] } })
      if (path === '/api/v1/purchase/orders') return response(page([order]))
      return response(page([]))
    }))
    const wrapper = mount(PurchasePage, { global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="purchase-action-approve"]').trigger('click')
    await wrapper.get('[data-testid="purchase-confirm"]').trigger('click')
    await flushPromises()

    expect(paths).toContain('/api/v1/purchase/orders/21/approve')
    expect(wrapper.text()).toContain('已审批')
  })

  it('shows explicit purchase API failures without demo fallback', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503)))
    const wrapper = mount(PurchasePage, { global: globals })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('采购数据加载失败')
    expect(wrapper.text()).not.toContain('PO-2026-018')
  })

  it('loads real payable balances and verified payment history', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.endsWith('/payables')) return response(page([{
        id: 31, order_code: 'PO-021', supplier_name: '海源饲料', amount: 520, paid_amount: 120,
        balance: 400, due_date: '2026-09-20', overdue_days: -20, status: 'partial', source_receipt_id: 88,
      }]))
      if (path.endsWith('/payments')) return response(page([{
        id: 41, code: 'PAY-041', name: '首笔付款', payable_id: 31, supplier_name: '海源饲料',
        amount: 120, paid_at: '2026-08-17', status: 'verified', version: 3, allowed_actions: ['view'],
      }]))
      return response(page([]))
    }))
    const wrapper = mount(PayablePage, { global: globals })
    await flushPromises()

    expect(paths).toContain('/api/v1/purchase/payables')
    expect(paths).toContain('/api/v1/purchase/payments')
    expect(wrapper.text()).toContain('海源饲料')
    expect(wrapper.text()).toContain('400')
    await wrapper.get('[data-testid="purchase-tab-payments"]').trigger('click')
    expect(wrapper.text()).toContain('PAY-041')
    expect(wrapper.text()).not.toContain('编辑')
    await wrapper.get('[data-testid="purchase-payment-action-view"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('详情 · 付款记录')
    expect(wrapper.find('[data-testid="payment-save"]').exists()).toBe(false)
  })

  it('loads governed purchase selectors and opens formal orders read-only', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path === '/api/v1/purchase/orders') return response(page([{ ...order, status: 'fully_received', allowed_actions: ['view'] }]))
      if (path.includes('/master-data/suppliers')) return response(page([{ id: 4, code: 'S4', name: '海源饲料' }]))
      if (path.includes('/master-data/materials')) return response(page([{ id: 8, code: 'M8', name: '鲈鱼配合料' }]))
      if (path.endsWith('/warehouse/warehouses')) return response({ items: [{ id: 3, code: 'W3', name: '主仓' }] })
      return response(page([]))
    }))

    const wrapper = mount(PurchasePage, { global: globals })
    await flushPromises()

    expect(paths).toEqual(expect.arrayContaining([
      '/api/v1/master-data/suppliers?page_size=100&status=verified', '/api/v1/master-data/materials?page_size=100&status=verified', '/api/v1/warehouse/warehouses',
    ]))
    await wrapper.get('[data-testid="purchase-action-view"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('详情 · 采购明细')
    expect(wrapper.find('[data-testid="purchase-save"]').exists()).toBe(false)
    expect(wrapper.get('[role="dialog"]').find('input,select,textarea').exists()).toBe(false)
  })

  it('carries an approved purchase into a governed receipt form', async () => {
    const approved = { ...order, status: 'approved', allowed_actions: ['view', 'receive'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/v1/purchase/orders') return response(page([approved]))
      if (path.startsWith('/api/v1/purchase/orders?')) return response(page([approved]))
      if (path.includes('/master-data/suppliers')) return response(page([{ id: 4, code: 'S4', name: '海源饲料' }]))
      if (path.includes('/master-data/materials')) return response(page([{ id: 8, code: 'M8', name: '鲈鱼配合料' }]))
      if (path.endsWith('/warehouse/warehouses')) return response({ items: [{ id: 3, code: 'W3', name: '主仓' }] })
      if (path.endsWith('/warehouse/receipts')) return response(page([]))
      return response(page([]))
    }))
    const purchaseWrapper = mount(PurchasePage, { global: globals }); await flushPromises()
    await purchaseWrapper.get('[data-testid="purchase-action-receive"]').trigger('click')
    expect(window.location.search).toContain('purchase_order_id=21')

    const receiptWrapper = mount(StockInPage, { global: globals }); await flushPromises()
    await receiptWrapper.get('.primary-action').trigger('click')
    expect((receiptWrapper.get('#warehouse-purchase_order_id').element as HTMLSelectElement).value).toBe('21')
    expect((receiptWrapper.get('#warehouse-warehouse_id').element as HTMLSelectElement).value).toBe('3')
    expect((receiptWrapper.get('#warehouse-material_id').element as HTMLSelectElement).value).toBe('8')
  })

  it('loads the requested purchase page and locks the payable source after creation', async () => {
    const laterOrder = { ...order, id: 22, code: 'PO-022', name: '第二页采购' }
    const draftPayment = { id: 42, code: 'PAY-042', name: '付款草稿', payable_id: 31, amount: 100,
      paid_at: '2026-08-17', payment_method: 'bank_transfer', status: 'draft', version: 1, row_version: 1,
      allowed_actions: ['view', 'edit', 'delete', 'submit'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/v1/purchase/orders') return response({ ...page([order]), total: 21, has_next: true })
      if (path === '/api/v1/purchase/orders?page=2&page_size=20') return response({ ...page([laterOrder]), page: 2 })
      if (path.endsWith('/payables')) return response(page([{ id: 31, order_code: 'PO-021', supplier_name: '海源饲料', amount: 520, paid_amount: 0, balance: 520, due_date: '2026-09-20', overdue_days: -20, status: 'unpaid', source_receipt_id: 88 }]))
      if (path.endsWith('/payments')) return response(page([draftPayment]))
      return response(page([]))
    }))

    const purchaseWrapper = mount(PurchasePage, { global: globals })
    await flushPromises()
    expect(purchaseWrapper.text()).not.toContain('第二页采购')
    await purchaseWrapper.get('[data-testid="table-next-page"]').trigger('click')
    await flushPromises()
    expect(purchaseWrapper.text()).toContain('第二页采购')

    const payableWrapper = mount(PayablePage, { global: globals })
    await flushPromises()
    await payableWrapper.get('[data-testid="purchase-tab-payments"]').trigger('click')
    await payableWrapper.get('[data-testid="purchase-payment-action-edit"]').trigger('click')
    expect(payableWrapper.get('#payment-payable_id').attributes('disabled')).toBeDefined()
    expect(payableWrapper.get('#payment-payment_method').element.tagName).toBe('SELECT')
  })

  it('reverses a verified payment through an append-only action', async () => {
    const paths: string[] = []
    const verified = { id: 41, code: 'PAY-041', name: '错误付款', payable_id: 31, supplier_name: '海源饲料', amount: 120,
      paid_at: '2026-08-17', payment_method: 'bank_transfer', status: 'verified', version: 3, row_version: 3, allowed_actions: ['view', 'reverse'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.endsWith('/reverse')) return response({ record: { ...verified, reversal_id: 9, allowed_actions: ['view'] } })
      if (path.endsWith('/payables')) return response(page([]))
      if (path.endsWith('/payments')) return response(page([verified]))
      return response(page([]))
    }))
    const wrapper = mount(PayablePage, { global: globals })
    await flushPromises()
    await wrapper.get('[data-testid="purchase-tab-payments"]').trigger('click')
    await wrapper.get('[data-testid="purchase-payment-action-reverse"]').trigger('click')
    await wrapper.get('#payment-reversal-reason').setValue('银行退回原付款')
    await wrapper.get('#payment-evidence').setValue('19')
    await wrapper.get('[data-testid="payment-confirm"]').trigger('click')
    await flushPromises()

    expect(paths).toContain('/api/v1/purchase/payments/41/reverse')
    expect(wrapper.find('[data-testid="purchase-payment-action-reverse"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已冲销')
  })
})

import { vi } from 'vitest'

/**
 * 退货前端测试共享夹具（非 spec，vitest include 为 tests/**\/*.spec.ts 故不会被当用例收集）。
 *
 * 契约来源（后端为准）：
 * - backend/layers/features/returns/return_store.py::create_return（INSERT 列名即真契约）
 * - backend/layers/features/purchase/purchase_service.py / sales/sales_service.py::create_return（必填 code/name/reason）
 * - backend/layers/product/purchase/routes.py 与 sales/routes.py 的 /returns 系列（submit/verify/cancel/delete）
 */

export function response(data: unknown, status = 200, message = '操作成功') {
  return Promise.resolve(new Response(JSON.stringify({
    code: status >= 400 ? 'RETURN_REQUEST_FAILED' : 'OK', message, data, request_id: 'return-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}

export const page = (items: unknown[]) => ({ items, page: 1, page_size: 20, total: items.length, has_next: false })
export const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }

export const receipt = {
  id: 88, code: 'IN-088', name: '饲料入库', status: 'verified', row_version: 3,
  warehouse_id: 3, material_id: 8, inventory_lot_id: 12, quantity: 100, unit_cost: 5.2,
  material_name: '鲈鱼配合料', inventory_lot_no: 'LOT-2026-01', warehouse_name: '主仓',
}
export const purchaseReturn = {
  id: 51, code: 'PR-051', name: '饲料变质退货', source_receipt_id: 88, payable_id: 31,
  warehouse_id: 3, material_id: 8, inventory_lot_id: 12, quantity: 10, amount: 52, reason: '到货变质',
  status: 'draft', row_version: 1, version: 1, allowed_actions: ['view', 'delete', 'submit'],
}
export const salesReturn = {
  id: 61, code: 'SR-061', name: '客户退鱼', source_delivery_id: 77, receivable_id: 41,
  quantity: 5, amount: 130, refund_amount: 130, reason: '规格不符',
  status: 'submitted', row_version: 2, version: 2, allowed_actions: ['view', 'verify', 'cancel'],
}
export const delivery = {
  id: 77, code: 'SD-077', name: '杭州水产交付', status: 'verified', row_version: 2,
  sales_order_id: 21, quantity: 50, customer_name: '杭州水产',
}

export interface StubOptions {
  purchaseReturns?: unknown[]
  salesReturns?: unknown[]
  failStatus?: number
  failPaths?: string[]
}
export interface StubCall { path: string; method: string; body: unknown }

/** 写动作 → 后端状态机与版本递增（draft→submitted→verified，可 cancelled） */
const transitions: Record<string, { status: string; version: number }> = {
  submit: { status: 'submitted', version: 2 },
  verify: { status: 'verified', version: 3 },
  cancel: { status: 'cancelled', version: 3 },
}

/** 统一的 fetch 桩；记录所有请求路径与写请求 body，便于断言后端契约 */
export function stubApi(options: StubOptions = {}): StubCall[] {
  const calls: StubCall[] = []
  const failPaths = options.failPaths ?? []
  const transitioned = (path: string) => {
    const move = transitions[path.split('/').pop() ?? '']
    if (!move) return null
    const base = path.includes('/sales/') ? options.salesReturns?.[0] ?? salesReturn : options.purchaseReturns?.[0] ?? purchaseReturn
    return {
      ...(base as Record<string, unknown>), status: move.status, version: move.version, row_version: move.version,
      allowed_actions: move.status === 'submitted' ? ['view', 'verify', 'cancel'] : ['view'],
    }
  }
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
    if (options.failStatus && (failPaths.length === 0 || failPaths.some((item) => path.includes(item)))) {
      return response(null, options.failStatus, options.failStatus === 403 ? '当前账号没有采购退货权限' : '退货服务不可用')
    }
    if (method === 'POST' && /\/returns$/.test(path)) {
      // 新建退货单：后端返回 { record: ... }，金额由后端按来源单价计算
      const body = (init?.body ? JSON.parse(String(init.body)) : {}) as Record<string, unknown>
      const isSales = path.includes('/sales/')
      return response({
        record: {
          id: isSales ? 62 : 52, ...body, status: 'draft', row_version: 1, version: 1,
          allowed_actions: ['view', 'delete', 'submit'], amount: isSales ? 0 : 52,
        },
      })
    }
    if (method !== 'GET') {
      const row = transitioned(path)
      if (row) return response({ record: row })
    }
    if (path.startsWith('/api/v1/purchase/returns')) return response(page(options.purchaseReturns ?? [purchaseReturn]))
    if (path.startsWith('/api/v1/sales/returns')) return response(page(options.salesReturns ?? []))
    if (path.startsWith('/api/v1/sales/deliveries')) return response(page([delivery]))
    if (path.startsWith('/api/v1/warehouse/receipts')) return response(page([receipt]))
    if (path.endsWith('/warehouse/warehouses')) return response({ items: [{ id: 3, code: 'W3', name: '主仓' }] })
    return response(page([]))
  }))
  return calls
}

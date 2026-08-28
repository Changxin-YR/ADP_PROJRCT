import { createApiClient } from '../../common/api/client'
import type { SalesDelivery, SalesOrder, SalesPage, SalesReceivable, SalesReceipt, SalesReturn } from '../../common/api/sales.models'

const api = createApiClient()
const base = '/api/v1/sales'
export interface SalesListQuery { page?: number; page_size?: number; status?: string; search?: string; sort_by?: string; sort_dir?: 'asc' | 'desc' }
const path = (resource: string, query?: SalesListQuery) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) if (value !== undefined && value !== '') params.set(key, String(value))
  return params.size ? `${base}/${resource}?${params}` : `${base}/${resource}`
}
const record = <T>(resource: string, id: number, action: string, version: number, extra: Record<string, unknown> = {}) => api.post<{ record: T }>(`${base}/${resource}/${id}/${action}`, { expected_version: version, ...extra })

export const listSalesOrders = (query?: SalesListQuery) => api.get<SalesPage<SalesOrder>>(path('orders', query))
export const createSalesOrder = (payload: Record<string, unknown>) => api.post<{ record: SalesOrder }>(`${base}/orders`, payload)
export const updateSalesOrder = (id: number, payload: Record<string, unknown>) => api.patch<{ record: SalesOrder }>(`${base}/orders/${id}`, payload)
export const deleteSalesOrder = (id: number) => api.delete<{ record: SalesOrder }>(`${base}/orders/${id}`)
export const submitSalesOrder = (id: number, version: number) => record<SalesOrder>('orders', id, 'submit', version)
export const approveSalesOrder = (id: number, version: number) => record<SalesOrder>('orders', id, 'approve', version)
export const cancelSalesOrder = (id: number, version: number, reason: string) => record<SalesOrder>('orders', id, 'cancel', version, { cancellation_reason: reason })

export const listSalesDeliveries = (query?: SalesListQuery) => api.get<SalesPage<SalesDelivery>>(path('deliveries', query))
export const createSalesDelivery = (payload: Record<string, unknown>) => api.post<{ record: SalesDelivery }>(`${base}/deliveries`, payload)
export const updateSalesDelivery = (id: number, payload: Record<string, unknown>) => api.patch<{ record: SalesDelivery }>(`${base}/deliveries/${id}`, payload)
export const correctSalesDelivery = (id: number, payload: Record<string, unknown>) => api.post<{ record: SalesDelivery }>(`${base}/deliveries/${id}/correct`, payload)
export const deleteSalesDelivery = (id: number) => api.delete<{ record: SalesDelivery }>(`${base}/deliveries/${id}`)
export const submitSalesDelivery = (id: number, version: number) => record<SalesDelivery>('deliveries', id, 'submit', version)
export const verifySalesDelivery = (id: number, version: number, evidence: number[]) => record<SalesDelivery>('deliveries', id, 'verify', version, { evidence_attachment_ids: evidence })
export const cancelSalesDelivery = (id: number, version: number, reason: string) => record<SalesDelivery>('deliveries', id, 'cancel', version, { cancellation_reason: reason })

export const listSalesReceivables = (query?: SalesListQuery) => api.get<SalesPage<SalesReceivable>>(path('receivables', query))
export const listSalesReceipts = (query?: SalesListQuery) => api.get<SalesPage<SalesReceipt>>(path('receipts', query))
export const createSalesReceipt = (payload: Record<string, unknown>) => api.post<{ record: SalesReceipt }>(`${base}/receipts`, payload)
export const updateSalesReceipt = (id: number, payload: Record<string, unknown>) => api.patch<{ record: SalesReceipt }>(`${base}/receipts/${id}`, payload)
export const deleteSalesReceipt = (id: number) => api.delete<{ record: SalesReceipt }>(`${base}/receipts/${id}`)
export const submitSalesReceipt = (id: number, version: number) => record<SalesReceipt>('receipts', id, 'submit', version)
export const verifySalesReceipt = (id: number, version: number, evidence: number[]) => record<SalesReceipt>('receipts', id, 'verify', version, { evidence_attachment_ids: evidence })
export const cancelSalesReceipt = (id: number, version: number, reason: string) => record<SalesReceipt>('receipts', id, 'cancel', version, { cancellation_reason: reason })
export const reverseSalesReceipt = (id: number, version: number, reason: string, evidence: number[]) => record<SalesReceipt>('receipts', id, 'reverse', version, { reversal_reason: reason, evidence_attachment_ids: evidence })
export const listSalesReturns = (query?: SalesListQuery) => api.get<SalesPage<SalesReturn>>(path('returns', query))
export const createSalesReturn = (payload: Record<string, unknown>) => api.post<{ record: SalesReturn }>(`${base}/returns`, payload)
export const submitSalesReturn = (id: number, version: number) => record<SalesReturn>('returns', id, 'submit', version)
export const verifySalesReturn = (id: number, version: number) => record<SalesReturn>('returns', id, 'verify', version)
export const cancelSalesReturn = (id: number, version: number, reason: string) => record<SalesReturn>('returns', id, 'cancel', version, { cancellation_reason: reason })
export const deleteSalesReturn = (id: number) => api.delete<{ record: SalesReturn }>(`${base}/returns/${id}`)

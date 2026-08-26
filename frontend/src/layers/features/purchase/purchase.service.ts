import { createApiClient } from '../../common/api/client'
import type { PurchaseOrder, PurchasePage, PurchasePayable, PurchasePayment } from '../../common/api/purchase.models'

const api = createApiClient()
const orders = '/api/v1/purchase/orders'
const payments = '/api/v1/purchase/payments'

interface ListQuery { page?: number; page_size?: number; status?: string; search?: string }
const path = (base: string, query?: ListQuery) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) if (value !== undefined && value !== '') params.set(key, String(value))
  return params.size ? `${base}?${params}` : base
}

export const listPurchaseOrders = (query?: ListQuery) => api.get<PurchasePage<PurchaseOrder>>(path(orders, query))
export const createPurchaseOrder = (payload: Record<string, unknown>) => api.post<{ record: PurchaseOrder }>(orders, payload)
export const updatePurchaseOrder = (id: number, payload: Record<string, unknown>) => api.patch<{ record: PurchaseOrder }>(`${orders}/${id}`, payload)
export const deletePurchaseOrder = (id: number) => api.delete<{ record: PurchaseOrder }>(`${orders}/${id}`)
export const submitPurchaseOrder = (id: number, version: number) => api.post<{ record: PurchaseOrder }>(`${orders}/${id}/submit`, { expected_version: version })
export const approvePurchaseOrder = (id: number, version: number) => api.post<{ record: PurchaseOrder }>(`${orders}/${id}/approve`, { expected_version: version })
export const cancelPurchaseOrder = (id: number, version: number, reason: string) => api.post<{ record: PurchaseOrder }>(`${orders}/${id}/cancel`, { expected_version: version, cancellation_reason: reason })

export const listPurchasePayables = (query?: ListQuery) => api.get<PurchasePage<PurchasePayable>>(path('/api/v1/purchase/payables', query))
export const listPurchasePayments = (query?: ListQuery) => api.get<PurchasePage<PurchasePayment>>(path(payments, query))
export const createPurchasePayment = (payload: Record<string, unknown>) => api.post<{ record: PurchasePayment }>(payments, payload)
export const updatePurchasePayment = (id: number, payload: Record<string, unknown>) => api.patch<{ record: PurchasePayment }>(`${payments}/${id}`, payload)
export const deletePurchasePayment = (id: number) => api.delete<{ record: PurchasePayment }>(`${payments}/${id}`)
export const submitPurchasePayment = (id: number, version: number) => api.post<{ record: PurchasePayment }>(`${payments}/${id}/submit`, { expected_version: version })
export const verifyPurchasePayment = (id: number, version: number, evidence: number[]) => api.post<{ record: PurchasePayment }>(`${payments}/${id}/verify`, { expected_version: version, evidence_attachment_ids: evidence })
export const cancelPurchasePayment = (id: number, version: number, reason: string) => api.post<{ record: PurchasePayment }>(`${payments}/${id}/cancel`, { expected_version: version, cancellation_reason: reason })
export const reversePurchasePayment = (id: number, version: number, reason: string, evidence: number[]) => api.post<{ record: PurchasePayment }>(`${payments}/${id}/reverse`, { expected_version: version, reversal_reason: reason, evidence_attachment_ids: evidence })

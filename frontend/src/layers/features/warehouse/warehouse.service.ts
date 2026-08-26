import { createApiClient } from '../../common/api/client'
import type { WarehouseLedgerRow, WarehousePage, WarehouseRecord, WarehouseResource } from '../../common/api/warehouse.models'

const api = createApiClient()
const base = (resource: WarehouseResource) => `/api/v1/warehouse/${resource}`

export const listWarehouseRecords = (resource: WarehouseResource) => api.get<WarehousePage>(base(resource))
export const listWarehouseOptions = () => api.get<{ items: Array<{ id: number; code: string; name: string }> }>('/api/v1/warehouse/warehouses')
export const createWarehouseRecord = (resource: WarehouseResource, payload: Record<string, unknown>) => api.post<{ record: WarehouseRecord }>(base(resource), payload)
export const createWarehouseCorrection = (resource: WarehouseResource, id: number, payload: Record<string, unknown>) => api.post<{ record: WarehouseRecord }>(`${base(resource)}/${id}/corrections`, payload)
export const updateWarehouseRecord = (resource: WarehouseResource, id: number, payload: Record<string, unknown>) => api.patch<{ record: WarehouseRecord }>(`${base(resource)}/${id}`, payload)
export const deleteWarehouseDraft = (resource: WarehouseResource, id: number) => api.delete<{ record: WarehouseRecord }>(`${base(resource)}/${id}`)
export const submitWarehouseRecord = (resource: WarehouseResource, id: number, expectedVersion: number) => api.post<{ record: WarehouseRecord }>(`${base(resource)}/${id}/submit`, { expected_version: expectedVersion })
export const verifyWarehouseRecord = (resource: WarehouseResource, id: number, expectedVersion: number, evidence: number[] = []) => api.post<{ record: WarehouseRecord }>(`${base(resource)}/${id}/verify`, { expected_version: expectedVersion, ...(evidence.length ? { evidence_attachment_ids: evidence } : {}) })
export const dispatchWarehouseTransfer = (id: number, expectedVersion: number) => api.post<{ record: WarehouseRecord }>(`${base('transfers')}/${id}/dispatch`, { expected_version: expectedVersion })
export const receiveWarehouseTransfer = (id: number, expectedVersion: number, receivedQuantity: number, differenceReason?: string) => api.post<{ record: WarehouseRecord }>(`${base('transfers')}/${id}/receive`, { expected_version: expectedVersion, received_quantity: receivedQuantity, ...(differenceReason ? { receipt_difference_reason: differenceReason } : {}) })
export const cancelWarehouseTransfer = (id: number, expectedVersion: number, reason: string) => api.post<{ record: WarehouseRecord }>(`${base('transfers')}/${id}/cancel`, { expected_version: expectedVersion, cancellation_reason: reason })
export const listWarehouseLedger = () => api.get<{ items: WarehouseLedgerRow[]; page: number; page_size: number; total: number; has_next: boolean }>('/api/v1/warehouse/ledger')
export const listWarehouseAlerts = () => api.get<{ items: Array<Record<string, unknown>> }>('/api/v1/warehouse/alerts')
export const handleWarehouseAlert = (alertKey: string, actionCode: string, resolutionNote: string) => api.post<{ alert: Record<string, unknown> }>(`/api/v1/warehouse/alerts/${encodeURIComponent(alertKey)}/handle`, { action_code: actionCode, resolution_note: resolutionNote })

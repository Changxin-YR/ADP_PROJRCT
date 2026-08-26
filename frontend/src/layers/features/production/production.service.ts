import { createApiClient } from '../../common/api/client'
import type { BatchReconciliation, ProductionPage, ProductionRecord, ProductionResource } from '../../common/api/production.models'

const api = createApiClient()
const base = (resource: ProductionResource) => `/api/v1/production/${resource}`

export const listProductionRecords = (resource: ProductionResource, query?: { page?: number; page_size?: number; status?: string; search?: string }) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) if (value) params.set(key, String(value))
  return api.get<ProductionPage>(params.size ? `${base(resource)}?${params}` : base(resource))
}
export const getProductionRecord = (resource: ProductionResource, id: number) => api.get<{ record: ProductionRecord }>(`${base(resource)}/${id}`)
export const createProductionRecord = (resource: ProductionResource, payload: Record<string, unknown>) => api.post<{ record: ProductionRecord }>(base(resource), payload)
export const createProductionCorrection = (resource: ProductionResource, id: number, payload: Record<string, unknown>) => api.post<{ record: ProductionRecord }>(`${base(resource)}/${id}/corrections`, payload)
export const updateProductionRecord = (resource: ProductionResource, id: number, payload: Record<string, unknown>) => api.patch<{ record: ProductionRecord }>(`${base(resource)}/${id}`, payload)
export const deleteProductionDraft = (resource: ProductionResource, id: number) => api.delete<{ record: ProductionRecord }>(`${base(resource)}/${id}`)
export const submitProductionRecord = (resource: ProductionResource, id: number, expectedVersion: number) => api.post<{ record: ProductionRecord }>(`${base(resource)}/${id}/submit`, { expected_version: expectedVersion })
export const verifyProductionRecord = (resource: ProductionResource, id: number, expectedVersion: number, evidence: number[] = []) => api.post<{ record: ProductionRecord }>(`${base(resource)}/${id}/verify`, { expected_version: expectedVersion, ...(evidence.length ? { evidence_attachment_ids: evidence } : {}) })
export const reconcileBatch = (id: number) => api.get<BatchReconciliation>(`${base('batches')}/${id}/reconciliation`)

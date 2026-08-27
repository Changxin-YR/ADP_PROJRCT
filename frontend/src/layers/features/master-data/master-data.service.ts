import { createApiClient } from '../../common/api/client'
import type { MasterPage, MasterRecord, MasterResource } from '../../common/api/master-data.models'

const api = createApiClient()
const base = (resource: MasterResource) => `/api/v1/master-data/${resource}`

export const listMasterRecords = (resource: MasterResource, query: { page?: number; page_size?: number } = {}) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) if (value != null) params.set(key, String(value))
  return api.get<MasterPage>(params.size ? `${base(resource)}?${params}` : base(resource))
}
export async function listAllMasterRecords(resource: MasterResource): Promise<MasterRecord[]> {
  const first = await listMasterRecords(resource, { page: 1, page_size: 100 })
  const items = [...first.items]
  for (let page = 2; first.has_next && page <= Math.ceil(first.total / (first.page_size || 100)); page += 1) {
    items.push(...(await listMasterRecords(resource, { page, page_size: first.page_size || 100 })).items)
  }
  return items
}
export const getMasterRecord = (resource: MasterResource, id: number) => api.get<{ record: MasterRecord }>(`${base(resource)}/${id}`)
export const listMasterOptions = (resource: MasterResource, page?: number) => api.get<MasterPage>(`${base(resource)}?page_size=100&status=verified${page ? `&page=${page}` : ''}`)
export async function listAllMasterOptions(resource: MasterResource): Promise<MasterRecord[]> {
  const first = await listMasterOptions(resource)
  const items = [...first.items]
  const pageSize = first.page_size || 100
  for (let page = 2; first.has_next && page <= Math.ceil(first.total / pageSize); page += 1) {
    items.push(...(await listMasterOptions(resource, page)).items)
  }
  return items
}
export const createMasterRecord = (resource: MasterResource, payload: Record<string, unknown>) => api.post<{ record: MasterRecord }>(base(resource), payload)
export const updateMasterRecord = (resource: MasterResource, id: number, payload: Record<string, unknown>) => api.patch<{ record: MasterRecord }>(`${base(resource)}/${id}`, payload)
export const deleteMasterDraft = (resource: MasterResource, id: number) => api.delete<{ record: MasterRecord }>(`${base(resource)}/${id}`)
export const submitMasterRecord = (resource: MasterResource, id: number, expectedVersion: number) => api.post<{ record: MasterRecord }>(`${base(resource)}/${id}/submit`, { expected_version: expectedVersion })
export const verifyMasterRecord = (resource: MasterResource, id: number, expectedVersion: number) => api.post<{ record: MasterRecord }>(`${base(resource)}/${id}/verify`, { expected_version: expectedVersion })
export const archiveMasterRecord = (resource: MasterResource, id: number, expectedVersion: number) => api.post<{ record: MasterRecord }>(`${base(resource)}/${id}/archive`, { expected_version: expectedVersion })
export const requestPondStatusChange = (id: number, payload: { to_status: string; reason: string; expected_version: number }) => api.post<{ status_change: Record<string, unknown> }>(`${base('ponds')}/${id}/status-changes`, payload)
export const verifyPondStatusChange = (pondId: number, requestId: number, expectedVersion: number, expectedPondVersion: number) => api.post<{ record: MasterRecord; status_change: Record<string, unknown> }>(`${base('ponds')}/${pondId}/status-changes/${requestId}/verify`, { expected_version: expectedVersion, expected_pond_version: expectedPondVersion })

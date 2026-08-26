import { createApiClient } from '../../common/api/client'
import type { AllocationRuleVersion, CostAllocationRun, CostAssetRecord, CostEntryPage, CostExpenseRecord, CostNetReport, CostRecordPage, CostSettlementRecord, CostStructure, SaveAllocationRules } from '../../common/api/cost.models'

const api = createApiClient()

export const getCostStructure = (start: string, end: string) => api.get<CostStructure>(`/api/v1/cost/structure?period_start=${encodeURIComponent(start)}&period_end=${encodeURIComponent(end)}`)

export const getCostEntries = (code: string, start: string, end: string, page = 1) => api.get<CostEntryPage>(`/api/v1/cost/entries?category_code=${encodeURIComponent(code)}&period_start=${encodeURIComponent(start)}&period_end=${encodeURIComponent(end)}&page=${page}`)

export const getAllocationRules = (effectiveAt: string) => api.get<AllocationRuleVersion | null>(`/api/v1/cost/allocation-rules?effective_at=${encodeURIComponent(effectiveAt)}`)

export const getLatestAllocationRules = () => api.get<AllocationRuleVersion | null>('/api/v1/cost/allocation-rules?mode=latest')

export const saveAllocationRules = (payload: SaveAllocationRules) => api.put<AllocationRuleVersion>('/api/v1/cost/allocation-rules', payload)

export interface CostListQuery { page?: number; page_size?: number; status?: string; search?: string }
const costListPath = (resource: string, query: CostListQuery | number = 1) => {
  const values = typeof query === 'number' ? { page: query, page_size: 20 } : { page: 1, page_size: 20, ...query }
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) if (value !== undefined && value !== '') params.set(key, String(value))
  return `/api/v1/cost/${resource}?${params}`
}
export const getExpenses = (query: CostListQuery | number = 1) => api.get<CostRecordPage<CostExpenseRecord>>(costListPath('expenses', query))
export const getAssets = (query: CostListQuery | number = 1) => api.get<CostRecordPage<CostAssetRecord>>(costListPath('assets', query))
export const getSettlements = (query: CostListQuery | number = 1) => api.get<CostRecordPage<CostSettlementRecord>>(costListPath('settlements', query))
const costAction = <T>(resource: string, id: number, action: string, version: number, extra: Record<string, unknown> = {}) => api.post<T>(`/api/v1/cost/${resource}/${id}/${action}`, { expected_version: version, ...extra })
export const createCostExpense = (payload: Record<string, unknown>) => api.post<CostExpenseRecord>('/api/v1/cost/expenses', payload)
export const updateCostExpense = (id: number, payload: Record<string, unknown>) => api.patch<CostExpenseRecord>(`/api/v1/cost/expenses/${id}`, payload)
export const deleteCostExpense = (id: number) => api.delete<CostExpenseRecord>(`/api/v1/cost/expenses/${id}`)
export const submitCostExpense = (id: number, version: number) => costAction<CostExpenseRecord>('expenses', id, 'submit', version)
export const verifyCostExpense = (id: number, version: number, evidence: number[]) => costAction<CostExpenseRecord>('expenses', id, 'verify', version, { evidence_attachment_ids: evidence })
export const confirmCostExpense = (id: number, version: number, evidence: number[]) => costAction<CostExpenseRecord>('expenses', id, 'confirm', version, { evidence_attachment_ids: evidence })
export const reverseCostExpense = (id: number, reason: string) => api.post<CostExpenseRecord>(`/api/v1/cost/expenses/${id}/reverse`, { reason })
export const createCostAsset = (payload: Record<string, unknown>) => api.post<CostAssetRecord>('/api/v1/cost/assets', payload)
export const updateCostAsset = (id: number, payload: Record<string, unknown>) => api.patch<CostAssetRecord>(`/api/v1/cost/assets/${id}`, payload)
export const deleteCostAsset = (id: number) => api.delete<CostAssetRecord>(`/api/v1/cost/assets/${id}`)
export const submitCostAsset = (id: number, version: number) => costAction<CostAssetRecord>('assets', id, 'submit', version)
export const verifyCostAsset = (id: number, version: number, evidence: number[]) => costAction<CostAssetRecord>('assets', id, 'verify', version, { evidence_attachment_ids: evidence })
export const confirmCostAsset = (id: number, version: number, evidence: number[]) => costAction<CostAssetRecord>('assets', id, 'confirm', version, { evidence_attachment_ids: evidence })
export const depreciateCostAsset = (id: number, period: string) => api.post<{ asset_id: number; period: string; amount: string }>(`/api/v1/cost/assets/${id}/depreciate`, { period })
export const runCostAllocation = (period_start: string, period_end: string, farm_id: number, area_id?: number) => api.post<CostAllocationRun>('/api/v1/cost/allocations', { period_start, period_end, farm_id, ...(area_id ? { area_id } : {}) })
export const createCostSettlement = (payload: Record<string, unknown>) => api.post<CostSettlementRecord>('/api/v1/cost/settlements', payload)
export const updateCostSettlement = (id: number, payload: Record<string, unknown>) => api.patch<CostSettlementRecord>(`/api/v1/cost/settlements/${id}`, payload)
export const deleteCostSettlement = (id: number) => api.delete<CostSettlementRecord>(`/api/v1/cost/settlements/${id}`)
export const submitCostSettlement = (id: number, version: number) => costAction<CostSettlementRecord>('settlements', id, 'submit', version)
export const verifyCostSettlement = (id: number, version: number) => costAction<CostSettlementRecord>('settlements', id, 'verify', version)
export const confirmCostSettlement = (id: number, version: number) => costAction<CostSettlementRecord>('settlements', id, 'confirm', version)
export const reverseCostSettlement = (id: number, version: number, reason: string) => costAction<CostSettlementRecord>('settlements', id, 'reverse', version, { reason })
export const getCostNetReport = (period_start: string, period_end: string) => api.get<CostNetReport>(`/api/v1/cost/reports/net?period_start=${encodeURIComponent(period_start)}&period_end=${encodeURIComponent(period_end)}`)

import { createApiClient } from '../../common/api/client'
import type { PageResult, PondDetail, PondSummary, WorkbenchSummary } from '../../common/api/workbench.models'
import type { MasterPage, MasterRecord } from '../../common/api/master-data.models'

const api = createApiClient()

export interface PondListQuery { search?: string; status?: string; area_id?: number; page?: number; page_size?: number }

export const getWorkbenchSummary = () => api.get<WorkbenchSummary>('/api/v1/workbench/summary')

function pond(row: MasterRecord): PondSummary {
  return {
    ...row,
    pond_code: row.code,
    area_name: String(row.area_name ?? `区域 ${row.area_id ?? '—'}`),
    area_id: Number(row.area_id ?? 0),
    group_name: String(row.group_name ?? '未分组'),
    group_id: Number(row.pond_group_id ?? 0),
    status: String(row.pond_status ?? 'build') as PondSummary['status'],
    lifecycle_status: row.status as PondSummary['lifecycle_status'],
    capacity_mu: Number(row.capacity_mu ?? 0),
    species: String(row.species ?? '待定'),
    active_batch_count: Number(row.active_batch_count ?? 0),
    updated_at: String(row.updated_at ?? ''),
  }
}

export async function listPonds(query: PondListQuery = {}): Promise<PageResult<PondSummary>> {
  const params = new URLSearchParams(Object.entries(query).filter(([, value]) => value !== undefined && value !== '').map(([key, value]) => [key, String(value)]))
  const result = await api.get<MasterPage>(`/api/v1/master-data/ponds?${params}`)
  return { ...result, items: result.items.map(pond) }
}

export async function getPond(id: number): Promise<PondDetail> {
  const result = await api.get<{ record: MasterRecord }>(`/api/v1/master-data/ponds/${id}`)
  const normalized = pond(result.record)
  return {
    ...normalized,
    manager_name: String(result.record.manager_name ?? '—'),
    water_source: String(result.record.water_source ?? '—'),
    location: String(result.record.location_text ?? '—'),
    notes: String(result.record.description ?? '—'),
    aerator_count: result.record.aerator_count == null ? undefined : Number(result.record.aerator_count),
    stocking_spec: result.record.stocking_spec == null ? undefined : String(result.record.stocking_spec),
    current_spec: result.record.current_spec == null ? undefined : String(result.record.current_spec),
    stock_quantity: result.record.stock_quantity == null ? undefined : Number(result.record.stock_quantity),
    stock_quantity_source: result.record.stock_quantity_source == null ? undefined : String(result.record.stock_quantity_source),
    timeline_preview: Array.isArray(result.record.timeline_preview) ? result.record.timeline_preview as PondDetail['timeline_preview'] : [],
    status_change_targets: Array.isArray(result.record.status_change_targets) ? result.record.status_change_targets as PondDetail['status_change_targets'] : [],
    can_request_status_change: result.record.can_request_status_change === true,
    can_verify_status_change: result.record.can_verify_status_change === true,
    pending_status_change: result.record.pending_status_change ? result.record.pending_status_change as unknown as PondDetail['pending_status_change'] : null,
  }
}

export interface WorkItemRecord {
  id: number
  title: string
  detail?: string | null
  module_code: string
  action_code: string
  object_type?: string | null
  object_id?: number | null
  object_ref?: string | null
  handling_mode?: 'manual' | 'domain'
  priority: 'low' | 'normal' | 'high' | 'critical'
  status: 'pending' | 'claimed' | 'in_progress' | 'completed' | 'cancelled' | 'escalated'
  due_at?: string | null
  overdue?: boolean
  completed_at?: string | null
  completion_note?: string | null
  cancelled_at?: string | null
  cancel_reason?: string | null
  row_version: number
}

export interface NotificationRecord {
  id: number
  title: string
  body?: string | null
  module_code: string
  level: 'low' | 'normal' | 'high' | 'critical'
  status: 'unread' | 'read' | 'closed' | 'escalated'
  last_occurred_at?: string | null
  read_at?: string | null
  closed_at?: string | null
  close_conclusion?: string | null
  occurrence_count: number
  object_type?: string | null
  object_id?: number | null
  object_ref?: string | null
}

export interface GovernanceList<T> { items: T[]; page: number; page_size: number; total: number; has_next: boolean }

export function getWorkItems(includeHistory = true, page = 1, pageSize = 100): Promise<GovernanceList<WorkItemRecord>> { return api.get(`/api/v1/work-items?include_history=${includeHistory ? 'true' : 'false'}&page=${page}&page_size=${pageSize}`) }
export function transitionWorkItem(id: number, action: 'claim' | 'start' | 'complete' | 'cancel', expectedVersion: number, note?: string): Promise<{ work_item: WorkItemRecord }> { return api.patch(`/api/v1/work-items/${id}`, { action, expected_version: expectedVersion, note }) }
export function getNotifications(includeHistory = true, page = 1, pageSize = 100): Promise<GovernanceList<NotificationRecord>> { return api.get(`/api/v1/notifications?include_history=${includeHistory ? 'true' : 'false'}&page=${page}&page_size=${pageSize}`) }
export function updateNotification(id: number, status: 'read' | 'closed', conclusion?: string): Promise<{ notification: NotificationRecord }> { return api.patch(`/api/v1/notifications/${id}`, { status, conclusion }) }

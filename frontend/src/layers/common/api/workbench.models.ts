export type PondStatus = 'build' | 'stocked' | 'farming' | 'rest' | 'clean' | 'rebuild'
export type PondLifecycleStatus = 'draft' | 'submitted' | 'verified' | 'archived'
export type BatchStatus = 'stocked' | 'farming' | 'pending_settlement' | 'closed' | 'exception'

export interface PageResult<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface TimelineEvent {
  id: number
  event_type: string
  title: string
  description: string
  happened_at: string
  operator_name: string
}

export interface PondSummary {
  id: number
  pond_code: string
  name: string
  area_name: string
  area_id: number
  group_name: string
  group_id: number
  status: PondStatus
  lifecycle_status: PondLifecycleStatus
  capacity_mu: number
  species: string
  active_batch_count: number
  updated_at: string
  version: number
  allowed_actions: string[]
}

export interface PondDetail extends PondSummary {
  manager_name: string
  water_source: string
  location: string
  notes: string
  aerator_count?: number
  stocking_spec?: string
  current_spec?: string
  stock_quantity?: number
  stock_quantity_source?: string
  timeline_preview: TimelineEvent[]
  status_change_targets: PondStatus[]
  can_request_status_change: boolean
  can_verify_status_change: boolean
  pending_status_change: PondStatusChange | null
}

export interface PondStatusChange {
  id: number
  pond_id: number
  from_status: PondStatus
  to_status: PondStatus
  reason: string
  status: 'submitted' | 'verified'
  requested_by: number
  row_version: number
  requested_at?: string
}

export interface PondGroupSummary {
  id: number
  name: string
  code: string
  area_name: string
  pond_count: number
  active_batch_count: number
  description: string
}

export interface BatchSummary {
  id: number
  batch_code: string
  name: string
  species: string
  status: BatchStatus
  status_label: string
  pond_names: string[]
  pond_ids: number[]
  stocked_at: string
  expected_harvest_date: string
  initial_stock: number
  current_stock: number
  stock_unit: string
  updated_at: string
}

export interface BatchDetail extends BatchSummary {
  source: string
  notes: string
  timeline_preview: TimelineEvent[]
  stock_records: Array<{ id: number; type: string; quantity: number; unit: string; happened_at: string; note: string }>
}

export interface WorkbenchSummary {
  date_label: string
  availability?: { production: boolean }
  kpis: {
    ponds: number | null
    active_batches: number | null
    current_stock: number | null
    todo_open: number
  }
  pond_status: Array<{ status: PondStatus; label: string; count: number }>
  todos: Array<{ id: number; title: string; type: string; due_at: string; overdue: boolean }>
  alerts: Array<{ id: number; title: string; level: 'low' | 'medium' | 'high'; created_at: string }>
  recent_batches: BatchSummary[]
}

import type { LifecycleRecord } from './lifecycle.models'

export type ProductionResource = 'batches' | 'samplings' | 'transfers' | 'losses' | 'harvests' | 'feed-plans' | 'feed-tasks' | 'feed-logs' | 'daily-operations'

export interface ProductionRecord extends LifecycleRecord {
  id: number
  code: string
  name: string
  row_version: number
  [key: string]: unknown
}

export interface ProductionPage {
  items: ProductionRecord[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

export interface BatchReconciliation {
  batch_id: number
  quantity: number
  weight_kg: number
  difference: number
}

export interface ProductionField {
  key: string
  label: string
  type?: 'text' | 'number' | 'datetime-local' | 'textarea' | 'select' | 'json'
  required?: boolean
  options?: Array<{ value: string; label: string }>
  placeholder?: string
}

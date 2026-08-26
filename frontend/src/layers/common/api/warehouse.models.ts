import type { LifecycleRecord } from './lifecycle.models'

export type WarehouseResource = 'receipts' | 'issue-requests' | 'issues' | 'returns' | 'transfers' | 'stocktakes' | 'scraps'

export interface WarehouseRecord extends LifecycleRecord {
  id: number
  code: string
  name: string
  row_version: number
  [key: string]: unknown
}

export interface WarehousePage {
  items: WarehouseRecord[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

export interface WarehouseField {
  key: string
  label: string
  type?: 'text' | 'number' | 'date' | 'datetime-local' | 'textarea' | 'select'
  required?: boolean
  options?: Array<{ value: string | number; label: string }>
}

export interface WarehouseLedgerRow {
  id: number
  source_type: string
  source_id: number
  quantity_delta: number
  material_name: string
  lot_no: string
  warehouse_name: string
  happened_at: string
  [key: string]: unknown
}

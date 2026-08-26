import type { LifecycleRecord } from './lifecycle.models'

export type MasterResource = 'farms' | 'areas' | 'pond-groups' | 'ponds' | 'materials' | 'suppliers' | 'customers' | 'settings'

export interface MasterRecord extends LifecycleRecord {
  id: number
  code: string
  name: string
  row_version: number
  [key: string]: unknown
}

export interface MasterPage {
  items: MasterRecord[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

export interface MasterField {
  key: string
  label: string
  type?: 'text' | 'number' | 'textarea'
  required?: boolean
  placeholder?: string
}

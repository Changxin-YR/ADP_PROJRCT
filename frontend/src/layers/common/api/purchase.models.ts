import type { LifecycleRecord } from './lifecycle.models'

export interface PurchaseOrder extends LifecycleRecord {
  id: number
  code: string
  name: string
  supplier_id: number
  supplier_name?: string
  material_id: number
  material_name?: string
  warehouse_id: number
  warehouse_name?: string
  quantity: number
  received_quantity: number
  unit_price: number
  total_amount: number
  paid_amount: number
  expected_delivery_date?: string
  due_date: string
  row_version: number
  note?: string
}

export interface PurchasePayable {
  id: number
  order_code: string
  supplier_name: string
  amount: number
  paid_amount: number
  balance: number
  due_date: string
  overdue_days: number
  status: string
  source_receipt_id: number
}

export interface PurchasePayment extends LifecycleRecord {
  id: number
  code: string
  name: string
  payable_id: number
  supplier_name?: string
  amount: number
  paid_at: string
  payment_method: string
  reversal_id?: number
  row_version: number
  note?: string
}

export interface PurchaseReturn extends LifecycleRecord {
  id: number; code: string; name: string; source_receipt_id: number; payable_id: number
  warehouse_id: number; material_id: number; inventory_lot_id: number; quantity: number; amount: number; reason: string
}

export interface PurchasePage<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

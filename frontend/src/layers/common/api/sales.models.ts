import type { LifecycleRecord } from './lifecycle.models'

export interface SalesOrder extends LifecycleRecord {
  id: number; code: string; name: string; customer_id: number; customer_name?: string
  pond_id: number; pond_name?: string; batch_id: number; batch_code?: string; species: string
  quantity: number; delivered_quantity: number; unit: string; unit_price: number; total_amount: number
  receivable_amount?: number; received_amount: number; sold_at: string; due_date: string; row_version: number; note?: string
}

export interface SalesDelivery extends LifecycleRecord {
  id: number; code: string; name: string; sales_order_id: number; order_code?: string
  harvest_document_id: number; customer_name?: string; quantity: number; delivered_at: string
  transport_info?: string; acceptance_note?: string; correction_of_id?: number; correction_id?: number
  row_version: number
}

export interface SalesReceivable {
  id: number; order_code: string; customer_name: string; amount: number; received_amount: number
  balance: number; due_date: string; overdue_days: number; status: string; source_delivery_id: number
}

export interface SalesReceipt extends LifecycleRecord {
  id: number; code: string; name: string; receivable_id: number; customer_name?: string
  amount: number; received_at: string; receipt_method: string; reversal_id?: number; row_version: number; note?: string
}

export interface SalesReturn extends LifecycleRecord {
  id: number; code: string; name: string; source_delivery_id: number; receivable_id: number
  quantity: number; amount: number; refund_amount: number; reason: string
}

export interface SalesReceivableSummary { total_amount: number; total_balance: number; overpaid_amount: number; overdue_count: number }
export interface SalesPage<T> { items: T[]; page: number; page_size: number; total: number; has_next: boolean; summary?: SalesReceivableSummary }

export type CostNature = 'direct' | 'public'
export type AllocationDriver = 'area' | 'equipment_count' | 'runtime_hours' | 'direct_input' | 'direct_consumption' | 'work_scope' | 'manual_ratio' | 'equal'

export interface CostCategorySummary {
  id: number
  code: string
  name: string
  nature: CostNature
  amount: string
  share: string | null
  allocation_driver: AllocationDriver
}

export interface CostStructure {
  period_start: string
  period_end: string
  total_amount: string
  direct_amount: string
  public_amount: string
  direct_share: string | null
  public_share: string | null
  confirmed_output_weight_jin: string
  confirmed_income_amount: string
  confirmed_profit_amount: string
  unit_production_cost: string | null
  unit_cost_status: 'available' | 'output_not_connected'
  source_fact_counts: { warehouse: number; purchase: number; production: number; expense: number; asset: number; sales: number }
  source_quality: 'verified' | 'legacy_import'
  confirmed_entry_count: number
  has_data: boolean
  categories: CostCategorySummary[]
}

export interface CostEntry {
  id: number
  category_code: string
  category_name: string
  amount: string
  occurred_on: string
  period_start: string
  period_end: string
  status: 'confirmed'
  source_type: string
  source_ref: string
  source_detail_json?: Record<string, unknown> | null
}

export interface CostEntryPage {
  items: CostEntry[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

export interface AllocationRule {
  category_id: number
  category_code: string
  category_name: string
  driver: AllocationDriver
  fallback_driver: 'equal'
  manual_ratio_json: Record<string, string> | null
}

export interface AllocationRuleVersion {
  id: number
  version_no: number
  effective_from: string
  effective_to: string | null
  status: 'active' | 'retired'
  change_reason: string
  created_by_name?: string | null
  rules: AllocationRule[]
}

export interface SaveAllocationRules {
  effective_from: string
  change_reason: string
  rules: Array<Pick<AllocationRule, 'category_id' | 'driver' | 'manual_ratio_json'>>
}

export type CostRecordStatus = 'draft' | 'submitted' | 'verified' | 'confirmed' | 'reversed' | 'cancelled'
export interface CostRecordPage<T> { items: T[]; page: number; page_size: number; total: number; has_next: boolean }
export interface CostExpenseRecord {
  id: number; source_ref: string; category_code: string; category_name: string; amount: string; occurred_on: string
  target_type?: string | null; target_id?: number | null; cost_nature?: CostNature; status: CostRecordStatus
  version: number; allowed_actions: import('./lifecycle.models').RecordAction[]
}
export interface CostAssetRecord {
  id: number; code: string; name: string; asset_type: 'equipment' | 'infrastructure' | 'lease'; category_name: string
  original_value: string; useful_life_months: number; accumulated_depreciation: string; area_id?: number | null
  note?: string | null; status: CostRecordStatus | 'retired' | 'disposed'; version: number; allowed_actions: import('./lifecycle.models').RecordAction[]
}
export interface CostSettlementRecord {
  id: number; code: string; name: string; farm_id: number; area_id?: number | null; period_start: string; period_end: string; allocation_run_id: number; income_amount: string
  cost_amount: string; profit_amount: string; operator?: string | null; confirmed_at?: string | null
  status: CostRecordStatus; version: number; allowed_actions: import('./lifecycle.models').RecordAction[]
}
export interface CostAllocationRun {
  id: number; source_total: string; allocated_total: string; fallback_count: number
  details: Array<{ pond_id: number; batch_id?: number | null; amount: string; fallback_used: boolean }>
}
export interface CostNetReport { income_amount: string; cost_amount: string; profit_amount: string; settlement_count: number }

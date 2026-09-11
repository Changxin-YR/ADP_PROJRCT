import type { RecordAction } from '../../common/api/lifecycle.models'

/**
 * 退货业务共享契约（供应商退货 / 客户退货）。
 *
 * 字段契约来源（后端为准，勿凭记忆改）：
 * - backend/layers/features/returns/return_store.py::create_return
 *     采购退货 INSERT 列：organization_id,source_receipt_id,payable_id,warehouse_id,material_id,
 *                        inventory_lot_id,code,name,quantity,amount,reason,created_by
 *     销售退货 INSERT 列：organization_id,source_delivery_id,receivable_id,code,name,
 *                        quantity,amount,refund_amount,reason,created_by
 *   amount 由后端按「退货数量 × 来源单据单价(unit_cost/unit_price)」计算，前端不传；
 *   payable_id / receivable_id 由后端从来源单据带出，前端不传；
 *   采购退货没有 refund_amount 字段，销售退货的 refund_amount 不能大于 amount。
 * - backend/layers/features/purchase/purchase_service.py / sales/sales_service.py
 *     create_return 必填 code / name / reason；来源单据必须是「已核验」入库单 / 交付单。
 * - 状态机：draft → submitted → verified，submitted 可 cancelled。
 *   后端没有 PATCH /returns/{id}，所以页面不提供「编辑」动作（前端不自造动作）。
 * - 权限：purchase.return.manage|purchase.manage、purchase.return.verify|purchase.verify；
 *         sales.return.manage|sales.manage、sales.return.verify|sales.verify。
 */

export type ReturnMode = 'purchase' | 'sales'

export interface ReturnRow extends Record<string, unknown> {
  id: number; code: string; name: string; quantity: number; amount: number; reason: string
  status: string; row_version: number; version: number; allowed_actions: RecordAction[]
}

export type SourceDoc = Record<string, unknown>

export interface ReturnFormField {
  key: string
  label: string
  type?: 'text' | 'number' | 'textarea' | 'select'
  required?: boolean
  options?: Array<{ value: number; label: string }>
}

export const RETURN_LABELS: Record<string, string> = {
  draft: '草稿', submitted: '待核验', verified: '已核验', cancelled: '已取消',
}
export const RETURN_TONES: Record<string, 'slate' | 'amber' | 'teal' | 'rose'> = {
  草稿: 'slate', 待核验: 'amber', 已核验: 'teal', 已取消: 'slate',
}
/** 状态 → 允许动作（后端状态机镜像：draft/submitted/verified/cancelled） */
export const STATUS_ACTIONS: Record<string, RecordAction[]> = {
  draft: ['view', 'delete', 'submit'],
  submitted: ['view', 'verify', 'cancel'],
  verified: ['view'],
  cancelled: ['view'],
}
export const MANAGE_PERMISSIONS: Record<ReturnMode, string[]> = {
  purchase: ['purchase.return.manage', 'purchase.manage'],
  sales: ['sales.return.manage', 'sales.manage'],
}
export const VERIFY_PERMISSIONS: Record<ReturnMode, string[]> = {
  purchase: ['purchase.return.verify', 'purchase.verify'],
  sales: ['sales.return.verify', 'sales.verify'],
}

export const numberOr = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0)

/** 来源单据提示：参考单价与可退数量，仅用于表单展示，绝不进请求体（amount 由后端按单价计算） */
export function sourceHintOf(source: SourceDoc | null, mode: ReturnMode): string {
  if (!source) return ''
  const quantity = numberOr(source.quantity)
  const returned = numberOr(source.returned_quantity)
  const price = numberOr(mode === 'purchase' ? source.unit_cost : source.unit_price)
  return `来源数量 ${quantity}，已退 ${returned}，可退 ${quantity - returned}；参考单价 ${price}（金额由后端按单价计算）`
}

export const optionLabel = (row: { code?: unknown; name?: unknown; id: unknown }) =>
  `${row.code ?? row.id} · ${row.name ?? ''}`.trim()

/**
 * 允许动作：优先采用服务端返回的 allowed_actions，并与后端状态机取交集（前端不自造动作，
 * 也不放宽服务端限制）；退货接口当前未返回 allowed_actions，因此退化为状态机推导。
 * 权限仍由后端兜底校验（越权返回 403），页面不按权限码裁剪按钮以免误藏可用动作。
 */
export function allowedActions(row: ReturnRow): RecordAction[] {
  const server = Array.isArray(row.allowed_actions) ? row.allowed_actions : null
  const derived = STATUS_ACTIONS[row.status] ?? ['view']
  if (!server || !server.length) return [...derived]
  return server.filter((action) => derived.includes(action))
}

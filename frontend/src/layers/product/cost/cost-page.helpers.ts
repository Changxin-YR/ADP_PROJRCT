import type { AllocationDriver, AllocationRule, CostCategorySummary, CostStructure } from '../../common/api/cost.models'

export const DRIVER_OPTIONS: Array<{ value: AllocationDriver; label: string }> = [
  { value: 'area', label: '按塘口面积' }, { value: 'equipment_count', label: '按设备数量' },
  { value: 'runtime_hours', label: '按运行时长' }, { value: 'direct_input', label: '按实际投入' },
  { value: 'direct_consumption', label: '按实际消耗' }, { value: 'work_scope', label: '按工作范围' },
  { value: 'manual_ratio', label: '手工比例' }, { value: 'equal', label: '平均分摊' },
]
export const DRIVER_LABELS = Object.fromEntries(DRIVER_OPTIONS.map((item) => [item.value, item.label])) as Record<AllocationDriver, string>

export function localDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function firstDayOfNextMonth(value = new Date()): string {
  return localDate(new Date(value.getFullYear(), value.getMonth() + 1, 1))
}

export const formatMoney = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }).format(Number(value))
export const formatShare = (value: string | null) => value === null ? '—' : `${Number(value).toFixed(1)}%`
export const safeBarWidth = (value: string | null) => `${Math.min(100, Math.max(0, Number(value ?? 0)))}%`

export function trapFocus(container: HTMLElement | null, event: KeyboardEvent) {
  const focusable = Array.from(container?.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
  ) ?? [])
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

export function manualRatios(rule: AllocationRule, textValue: string | undefined): Record<string, string> | null {
  if (rule.driver !== 'manual_ratio') return null
  const text = textValue?.trim()
  if (!text) throw new Error(`${rule.category_name}需要填写手工比例`)
  const parsed = JSON.parse(text) as unknown
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${rule.category_name}手工比例格式无效`)
  return Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, String(value)]))
}

const csv = (value: string) => (/[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value)
export function downloadCostCsv(structure: CostStructure, rows: CostCategorySummary[], drivers: Map<number, AllocationDriver>, periodEnd: string) {
  const header = ['成本类别', '金额（元）', '占比（%）', '成本性质', '当前分摊依据']
  const data = rows.map((item) => [item.name, item.amount, item.share ?? '', item.nature === 'direct' ? '直接成本' : '公共成本', DRIVER_LABELS[drivers.get(item.id) ?? item.allocation_driver]])
  const lines = [`# 导出时间：${new Date().toLocaleString('zh-CN')}`, `# 数据期间：${structure.period_start} 至 ${structure.period_end}`, `# 总成本：${structure.total_amount}`, header.map(csv).join(','), ...data.map((row) => row.map(csv).join(','))]
  const url = URL.createObjectURL(new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `成本构成明细_${periodEnd}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

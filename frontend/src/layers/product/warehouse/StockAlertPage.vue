<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import { createSessionStore } from '../../common/session/session.store'
import { hasPermission } from '../../common/security/access-control'
import { handleWarehouseAlert, listWarehouseAlerts } from '../../features/warehouse/warehouse.service'

const rows = ref<Array<Record<string, unknown>>>([])
const loading = ref(true)
const error = ref('')
const dialogError = ref('')
const handling = ref<Record<string, unknown> | null>(null)
const actionCode = ref('replenish')
const resolutionNote = ref('')
const session = createSessionStore()
const canManage = computed(() => hasPermission(session.user.value, 'warehouse.manage'))
const typeLabels: Record<string, string> = { low_stock: '低库存', expiring: '临近到期', expired: '已过期' }
const severityLabels: Record<string, string> = { high: '高', medium: '中', low: '低' }
// 无 warehouse.manage 权限时隐藏"处理"按钮（服务端仍会拦截，前端不再露出入口）
const displayRows = computed(() => rows.value.map((row) => {
  const allowed = Array.isArray(row.allowed_actions) ? (row.allowed_actions as string[]).filter((action) => action !== 'handle' || canManage.value) : []
  return { ...row, type_label: typeLabels[String(row.alert_type)] ?? row.alert_type, severity_label: severityLabels[String(row.severity)] ?? row.severity, status_label: row.status === 'pending' ? '待处理' : row.status === 'handled' ? '已处理' : row.status, allowed_actions: allowed }
}))
onMounted(async () => {
  try { rows.value = (await listWarehouseAlerts()).items }
  catch (reason) { error.value = reason instanceof ApiError ? `库存预警加载失败：${reason.message}` : '库存预警加载失败' }
  finally { loading.value = false }
})
function openHandling(_name: string, row: Record<string, unknown>) {
  if (!canManage.value) return
  handling.value = row; actionCode.value = 'replenish'; resolutionNote.value = ''; dialogError.value = ''
}
const { busy: saving, run } = useSubmitGuard()
async function saveHandling() {
  if (!handling.value) return
  if (!resolutionNote.value.trim()) { dialogError.value = '请填写处理结论'; return }
  dialogError.value = ''
  await run(async () => {
    try {
      const result = await handleWarehouseAlert(String(handling.value!.alert_key), actionCode.value, resolutionNote.value.trim())
      const index = rows.value.findIndex((row) => row.alert_key === result.alert.alert_key)
      if (index >= 0) rows.value[index] = result.alert
      handling.value = null
    } catch (reason) { dialogError.value = submitErrorText(reason, '预警处理失败，请稍后重试') }
  })
}
</script>

<template>
  <div v-if="error" class="page-card table-empty" role="alert">{{ error }}</div>
  <DataTablePage v-else export-resource="stock-alerts" title="库存预警" label="Warehouse / Alerts"
    description="由真实库存余额、安全库存线和物料批次到期日实时计算，不保存演示预警。"
    :kpis="[
      { label: '待处理预警', value: rows.length, unit: '条', tone: 'rose', hint: '当前授权范围' },
      { label: '高严重度', value: rows.filter((row) => row.severity === 'high').length, unit: '条', tone: 'rose', hint: '建议当日处理' },
      { label: '临期与过期', value: rows.filter((row) => row.alert_type !== 'low_stock').length, unit: '条', tone: 'amber', hint: '按批次到期日' },
    ]"
    :filters="[{ key: 'material_name', type: 'search', placeholder: '搜索物料 / 批次 / 仓库', wide: true }]"
    :columns="[
      { key: 'material_name', label: '物料', type: 'title', sub: 'lot_no' }, { key: 'warehouse_name', label: '仓库' },
      { key: 'type_label', label: '预警类型', type: 'badge', tones: { '低库存': 'rose', '临近到期': 'amber', '已过期': 'rose' } },
      { key: 'severity_label', label: '严重度', type: 'badge', tones: { '高': 'rose', '中': 'amber', '低': 'slate' } },
      { key: 'current_quantity', label: '当前数量', type: 'number' }, { key: 'safety_stock', label: '安全库存', type: 'number' },
      { key: 'expiry_date', label: '到期日' }, { key: 'status_label', label: '状态', type: 'badge', tones: { '待处理': 'amber', '已处理': 'teal' } },
    ]"
    :rows="displayRows" action-test-id-prefix="warehouse-alert-action" :empty-text="loading ? '正在计算库存预警…' : '当前没有库存预警'" @action="openHandling" />
  <Teleport to="body"><div v-if="handling" class="modal-overlay" role="dialog" aria-modal="true" aria-label="库存预警处理"><div class="modal-panel" style="width:min(520px,100%)"><div class="modal-panel__head"><div><p class="section-label">Alert handling</p><h2>处理库存预警</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="handling = null">×</button></div><p class="section-subtitle">{{ handling.material_name }} · {{ handling.warehouse_name }} · {{ handling.lot_no }}</p><label class="modal-field" for="warehouse-alert-action"><span>处理动作 *</span><select id="warehouse-alert-action" v-model="actionCode" class="filter-select" style="width:100%"><option value="replenish">发起补货</option><option value="transfer">办理调拨</option><option value="scrap">报损报废</option><option value="recheck">库存复核</option><option value="threshold">调整阈值</option></select></label><label class="modal-field" for="warehouse-alert-note"><span>处理结论 *</span><textarea id="warehouse-alert-note" v-model="resolutionNote" rows="4" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="handling = null">取消</button><button class="primary-action" type="button" :disabled="saving" :aria-busy="saving" @click="saveHandling">{{ saving ? '提交中…' : '保存处理结果' }}</button></div></div></div></Teleport>
</template>

<script setup lang="ts">
/**
 * 退货出口页（供应商退货 / 客户退货）。
 * 只保留 tab 骨架 + 列表渲染 + 动作编排；数据加载见 useReturns.ts，
 * 表单弹窗见 ReturnFormDialog.vue，确认弹窗见 ReturnConfirmDialog.vue。
 * 字段契约与状态机说明见 returnModel.ts 顶部注释。
 */
import { onMounted, ref, watch } from 'vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import ReturnConfirmDialog, { type ReturnConfirmAction } from './ReturnConfirmDialog.vue'
import ReturnFormDialog from './ReturnFormDialog.vue'
import { RETURN_LABELS, type ReturnMode, type ReturnRow } from './returnModel'
import { useReturns } from './useReturns'

const props = withDefaults(defineProps<{ mode?: ReturnMode }>(), { mode: 'purchase' })
const emit = defineEmits<{ modeChange: [mode: ReturnMode] }>()

const tab = ref<ReturnMode>(props.mode)
const formOpen = ref(false)
const confirmAction = ref<ReturnConfirmAction | null>(null)
const target = ref<ReturnRow | null>(null)
const store = useReturns(() => tab.value)

const pageTitle = () => (tab.value === 'purchase' ? '供应商退货' : '客户退货')
/** 另一类退货的直达入口：/purchase/returns 与 /sales/returns 各自可达 */
const alternateLink = () => (tab.value === 'purchase'
  ? { href: '/sales/returns', label: '前往客户退货' }
  : { href: '/purchase/returns', label: '前往供应商退货' })

function switchTab(next: ReturnMode) {
  if (next === tab.value) return
  tab.value = next
  store.reset()
  emit('modeChange', next)
  // 父级（router）切换路由后由 props.mode 触发重载；未接管时这里自行加载对应类型，避免空表
  void store.load()
}

function action(name: string, raw: Record<string, unknown>) {
  const row = store.rows.value.find((item) => item.id === Number(raw.id))
  if (!row) return
  if (name === 'delete' || name === 'submit' || name === 'verify' || name === 'cancel') {
    target.value = row
    confirmAction.value = name
  }
}

/** 动作名与后端路由一一对应（delete/submit/verify/cancel），不做前端自造动作 */
async function run(act: ReturnConfirmAction, row: ReturnRow, reason: string) {
  if (act === 'delete') await store.remove(row)
  else store.replace(await store.transition(act, row, reason))
  target.value = null
  confirmAction.value = null
}

function onSaved(row: ReturnRow) {
  store.replace(row)
  formOpen.value = false
}

watch(() => props.mode, (value) => {
  if (value === tab.value) return
  tab.value = value
  store.reset()
  void store.load()
})
onMounted(store.load)
</script>

<template>
  <div v-if="store.pageError.value" class="page-card table-empty" role="alert">
    {{ store.pageError.value }}
    <div style="margin-top:12px"><button class="ghost-action" type="button" @click="store.load()">重新加载</button></div>
  </div>
  <DataTablePage v-else :title="pageTitle()"
    :label="tab === 'purchase' ? 'Purchase / Returns' : 'Sales / Returns'"
    :description="tab === 'purchase'
      ? '供应商退货必须关联已核验入库单；核验后冲减应付账款并回退库存。'
      : '客户退货必须关联已核验交付单；核验后冲减应收账款。'"
    :create-label="tab === 'purchase' ? '＋ 登记供应商退货' : '＋ 登记客户退货'"
    :kpis="store.kpis.value" exportable action-test-id-prefix="return-action" server-side
    :total="store.pageMeta.total" :current-page="store.pageMeta.page" :page-size="store.pageMeta.page_size"
    :empty-text="store.loading.value ? '正在加载退货记录…' : '当前授权范围内暂无退货单'"
    :filters="[{ key: 'status', type: 'select', label: '全部业务状态', options: Object.entries(RETURN_LABELS).map(([value, label]) => ({ value, label })) }, { key: 'code', type: 'search', placeholder: '搜索退货单号 / 名称', wide: true }]"
    :columns="store.columns.value" :rows="store.displayRows.value"
    @create="formOpen = true" @action="action" @query="store.queryReturns">
    <template #tabs>
      <div class="filter-bar" role="tablist" aria-label="退货类型" style="justify-content:flex-start">
        <button type="button" role="tab" :class="tab === 'purchase' ? 'primary-action' : 'ghost-action'"
          data-testid="return-tab-purchase" :aria-selected="tab === 'purchase'" @click="switchTab('purchase')">供应商退货</button>
        <button type="button" role="tab" :class="tab === 'sales' ? 'primary-action' : 'ghost-action'"
          data-testid="return-tab-sales" :aria-selected="tab === 'sales'" @click="switchTab('sales')">客户退货</button>
        <span class="spacer" />
        <a class="ghost-action" :href="alternateLink().href" data-testid="return-alternate-link">{{ alternateLink().label }}</a>
        <span v-if="store.optionsFailed.value" class="form-error" role="status" data-testid="return-options-warning">来源单据或仓库选项加载失败，登记退货前请重新加载页面。</span>
      </div>
    </template>
  </DataTablePage>

  <ReturnFormDialog v-if="formOpen" :mode="tab" :sources="tab === 'purchase' ? store.receipts.value : store.deliveries.value"
    :source-options="store.sourceOptions.value" :pick-source="store.sourceOf"
    @close="formOpen = false" @saved="onSaved" />
  <ReturnConfirmDialog v-if="confirmAction && target" :mode="tab" :action="confirmAction" :row="target" :run="run"
    @close="confirmAction = null; target = null" />
</template>
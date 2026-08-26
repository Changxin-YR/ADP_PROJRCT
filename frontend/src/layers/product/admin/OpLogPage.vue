<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { getAuditLogs, type AuditLogRecord } from '../../features/audit/audit.service'

interface OpLogRow { id: number | string; happened_at: string; user: string; action: string; target: string; detail: string; result: string; request_id?: string | null }

const rows = ref<OpLogRow[]>([])
const loading = ref(false)
const error = ref('')
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
const dateFrom = ref('')
const dateTo = ref('')

function mapAuditLog(item: AuditLogRecord): OpLogRow {
  let detail = item.reason ?? ''
  if (item.detail_json) detail = typeof item.detail_json === 'string' ? item.detail_json : JSON.stringify(item.detail_json)
  return {
    id: item.id,
    happened_at: item.created_at,
    user: item.actor_name ?? (item.user_id ? `用户 #${item.user_id}` : '系统'),
    action: item.action_code ?? item.action,
    target: item.object_ref ?? `${item.object_type}${item.object_id ? ` #${item.object_id}` : ''}`,
    detail: detail || '—',
    result: item.result === 'success' ? '成功' : item.result === 'failure' ? '失败' : item.result,
    request_id: item.request_id,
  }
}

async function loadLogs(query: Record<string, string | number> = {}) {
  loading.value = true
  error.value = ''
  try {
    const result = await getAuditLogs({ ...query, created_from: dateFrom.value || undefined, created_to: dateTo.value || undefined, page: Number(query.page ?? 1), page_size: pageSize })
    rows.value = result.items.map(mapAuditLog); total.value = result.total; currentPage.value = result.page
  } catch { error.value = '操作日志暂时无法加载，请检查服务端审计查询和权限后重试。' } finally { loading.value = false }
}
onMounted(() => { void loadLogs() })

const resultTones: Record<string, 'teal' | 'blue' | 'amber' | 'rose' | 'slate'> = { 成功: 'teal', 通过: 'teal', 处理中: 'blue', 失败: 'rose' }
const today = new Date().toISOString().slice(0, 10)
const activeUsers = computed(() => new Set(rows.value.map((item) => item.user)).size)
const todayCount = computed(() => rows.value.filter((item) => item.happened_at.startsWith(today)).length)
const permissionChanges = computed(() => rows.value.filter((item) => /grant|permission|role|授权|权限/i.test(`${item.action}${item.detail}`)).length)
</script>

<template>
  <p v-if="error" class="field-error" role="alert">{{ error }}</p>
  <div class="page-card" style="display:flex;gap:12px;align-items:end;margin-bottom:18px">
    <label>开始日期<input v-model="dateFrom" type="date" @change="loadLogs({ page: 1 })" /></label>
    <label>结束日期<input v-model="dateTo" type="date" @change="loadLogs({ page: 1 })" /></label>
  </div>
  <DataTablePage
    title="操作日志" label="System / Audit logs"
    description="谁在什么时间对什么数据做了什么：服务端追加式日志，按请求号、动作、对象和结果追溯；日志本身不可编辑或删除。"
    :exportable="true" :persist-local="false" :read-only="true"
    :kpis="[
      { label: '今日操作', value: todayCount, unit: '条', hint: loading ? '加载中…' : '服务端实时查询' },
      { label: '活跃用户', value: activeUsers, unit: '人', hint: '当前查询范围' },
      { label: '权限类变更', value: permissionChanges, unit: '条', tone: 'amber', hint: '角色 / 数据范围 / 权限' },
    ]"
    :filters="[
      { key: 'action_code', type: 'search', placeholder: '动作代码' },
      { key: 'module_code', type: 'search', placeholder: '模块代码' },
      { key: 'object_type', type: 'search', placeholder: '对象类型' },
      { key: 'result', type: 'select', label: '全部结果', options: [{ value: 'success', label: '成功' }, { value: 'failure', label: '失败' }] },
      { key: 'user_id', type: 'search', placeholder: '操作人 ID' },
    ]"
    :columns="[
      { key: 'happened_at', label: '操作时间', type: 'title', sub: 'user' },
      { key: 'action', label: '动作' },
      { key: 'target', label: '对象' },
      { key: 'detail', label: '详情' },
      { key: 'result', label: '结果', type: 'badge', tones: resultTones },
    ]"
    :rows="rows"
    :server-side="true" :total="total" :current-page="currentPage" :page-size="pageSize" @query="loadLogs"
    empty-text="没有符合条件的日志"
  />
</template>

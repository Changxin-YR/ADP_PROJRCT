<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { ApiError } from '../../common/api/errors'
import { getNotifications, getWorkItems, transitionWorkItem, updateNotification, type NotificationRecord, type WorkItemRecord } from '../../features/workbench/workbench.service'

const props = withDefaults(defineProps<{ mode?: 'messages' | 'todos' }>(), { mode: 'messages' })

interface QueueEntry {
  id: string
  title: string
  detail: string
  time: string
  source: string
  tone: 'teal' | 'blue' | 'amber' | 'rose'
  to: string
  level: '高' | '中' | '低'
  backendId?: number
  backendKind?: 'work_item' | 'notification'
  backendStatus?: WorkItemRecord['status'] | NotificationRecord['status']
  rowVersion?: number
  handledAt?: string | null
  handledNote?: string | null
  canComplete?: boolean
}

const source = ref<QueueEntry[]>([])
const loadError = ref('')
const isBackendHandled = (item: QueueEntry) => props.mode === 'messages'
  ? ['read', 'closed'].includes(String(item.backendStatus))
  : ['completed', 'cancelled'].includes(String(item.backendStatus))
const entries = computed(() => source.value.filter((item) => !isBackendHandled(item)))
const handledEntries = computed(() => source.value.filter(isBackendHandled))

function modulePath(moduleCode: string, objectType?: string | null, objectId?: number | null): string {
  if (objectId && objectType === 'master:pond_status_change') return `/ponds/${objectId}`
  if (objectId && objectType === 'master:ponds') return `/ponds/${objectId}`
  if (objectId && objectType === 'production:batches') return `/batches/${objectId}`
  const paths: Record<string, string> = { warehouse: '/warehouse/alerts', cost: '/cost/expenses', sales: '/sales/receivables', daily_farming: '/feeding/tasks', workbench: '/workbench' }
  return paths[moduleCode] ?? '/workbench'
}

function mapWorkItem(item: WorkItemRecord): QueueEntry {
  const priority = item.priority === 'critical' || item.priority === 'high' ? '高' : item.priority === 'normal' ? '中' : '低'
  return { id: `work-item-${item.id}`, backendId: item.id, backendKind: 'work_item', backendStatus: item.status, rowVersion: item.row_version, handledAt: item.completed_at ?? item.cancelled_at, handledNote: item.completion_note ?? item.cancel_reason, title: item.title, detail: item.detail ?? '', time: item.due_at ?? '', source: item.module_code, tone: priority === '高' ? 'rose' : priority === '中' ? 'amber' : 'teal', to: modulePath(item.module_code, item.object_type, item.object_id), level: priority, canComplete: item.handling_mode === 'manual' }
}

function mapNotification(item: NotificationRecord): QueueEntry {
  const priority = item.level === 'critical' || item.level === 'high' ? '高' : item.level === 'normal' ? '中' : '低'
  return { id: `notification-${item.id}`, backendId: item.id, backendKind: 'notification', backendStatus: item.status, handledAt: item.read_at ?? item.closed_at, handledNote: item.close_conclusion, title: item.title, detail: item.body ?? '', time: item.last_occurred_at ?? '', source: item.module_code, tone: priority === '高' ? 'rose' : priority === '中' ? 'amber' : 'blue', to: modulePath(item.module_code), level: priority }
}

async function loadBackendQueue() {
  loadError.value = ''
  try {
    if (props.mode === 'messages') {
      source.value = (await getNotifications(true)).items.map(mapNotification)
    } else {
      source.value = (await getWorkItems(true)).items.map(mapWorkItem)
    }
  } catch (error) {
    source.value = []
    loadError.value = error instanceof ApiError ? error.message : '协作服务暂时不可用，请稍后重试'
  }
}

onMounted(() => { void loadBackendQueue() })

const toasts = ref<{ id: number; text: string }[]>([])
function toast(text: string) { const id = Date.now() + Math.random(); toasts.value.push({ id, text }); setTimeout(() => { toasts.value = toasts.value.filter((item) => item.id !== id) }, 3000) }
async function refresh() { await loadBackendQueue(); toast(`已刷新：当前 ${entries.value.length} 条未处理 · ${handledEntries.value.length} 条已处理` + (props.mode === 'messages' ? ' · 历史记录已保留' : '')) }

const handling = ref(false)
async function markHandled(item: QueueEntry) {
  if (handling.value) return
  handling.value = true
  try {
    if (item.backendKind === 'notification' && item.backendId) {
      try { await updateNotification(item.backendId, 'read'); await loadBackendQueue(); toast('已标记为已读，历史记录仍可查询'); return } catch { toast('消息状态更新失败，请刷新后重试'); return }
    }
    if (item.backendKind === 'work_item' && item.backendId && item.rowVersion) {
      try {
        let status = item.backendStatus
        let version = item.rowVersion
        if (status === 'pending' || status === 'escalated') { const claimed = await transitionWorkItem(item.backendId, 'claim', version); status = claimed.work_item.status; version = claimed.work_item.row_version }
        if (status === 'claimed') { const started = await transitionWorkItem(item.backendId, 'start', version); status = started.work_item.status; version = started.work_item.row_version }
        await transitionWorkItem(item.backendId, 'complete', version, '已在工作台完成处理')
        await loadBackendQueue(); toast('待办已完成，处理记录已保留'); return
      } catch { toast('待办状态更新失败，请刷新后重试'); return }
    }
    toast('当前记录缺少服务端标识，请刷新后重试')
  } finally { handling.value = false }
}

const handledLabel = computed(() => (props.mode === 'messages' ? '已读消息' : '已完成待办'))
const handledVerb = computed(() => (props.mode === 'messages' ? '已读' : '已完成'))
</script>

<template>
  <AppShell :title="props.mode === 'messages' ? '消息与预警' : '我的待办'">
    <div class="page-title">
      <div>
        <p class="section-label">{{ props.mode === 'messages' ? 'Messages & alerts' : 'Action queue' }}</p>
        <h1>{{ props.mode === 'messages' ? '消息与预警' : '我的待办' }}</h1>
        <p>{{ props.mode === 'messages' ? '库存、账期与系统通知的统一消息中心；处理结果保留处理人与时间。' : '分配给当前用户的任务、核验与审核事项；完成后从待处理队列移出，但历史记录不可删除。' }}</p>
      </div>
      <div class="page-title__actions">
        <button class="ghost-action" type="button" @click="refresh">↻ 刷新列表</button>
      </div>
    </div>

    <div v-if="loadError" class="page-card table-empty" role="alert">{{ loadError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="loadBackendQueue">重新加载</button></div></div>

    <section class="kpi-grid" aria-label="处理概览">
      <article class="page-card kpi-card kpi--rose"><div class="kpi-card__top"><span>未处理 · 高优先级</span></div><strong>{{ entries.filter((item) => item.level === '高').length }}</strong><small>建议当日处理完毕</small></article>
      <article class="page-card kpi-card kpi--amber"><div class="kpi-card__top"><span>未处理 · 中优先级</span></div><strong>{{ entries.filter((item) => item.level === '中').length }}</strong><small>按计划推进</small></article>
      <article class="page-card kpi-card kpi--teal"><div class="kpi-card__top"><span>{{ handledVerb }}（历史）</span></div><strong>{{ handledEntries.length }}</strong><small>保留处理人、时间和结论，不提供物理删除</small></article>
    </section>

    <section class="page-card dashboard-card">
      <div class="section-head">
        <div>
          <p class="section-label">{{ props.mode === 'messages' ? 'Unified alerts' : 'My queue' }}</p>
          <h2 class="section-title">{{ entries.length }} 条待处理</h2>
          <p class="section-subtitle">相同对象相同原因的提醒已合并显示</p>
        </div>
      </div>
      <div class="todo-list">
        <div v-for="item in entries" :key="item.id" class="todo-item">
          <span class="todo-item__mark" :class="{ 'is-overdue': item.level === '高' }">{{ item.level === '高' ? '!' : item.level === '中' ? '·' : '·' }}</span>
          <div class="todo-item__content">
            <strong>{{ item.title }}</strong>
            <small>{{ item.detail }}</small>
            <small style="color:#a0abb9">{{ item.time }} · 来源：{{ item.source }}</small>
          </div>
          <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
            <StatusBadge :label="item.level === '高' ? '高优先级' : item.level === '中' ? '中优先级' : '低优先级'" :tone="item.tone" />
            <RouterLink class="table-action-btn" :to="item.to" style="text-decoration:none;display:inline-block">去处理</RouterLink>
            <button v-if="props.mode === 'messages' || item.canComplete" class="table-action-btn" type="button" :disabled="handling" :aria-busy="handling" @click="markHandled(item)">{{ props.mode === 'messages' ? '已读' : '完成' }}</button>
          </div>
        </div>
        <div v-if="!entries.length" class="table-empty" style="padding:34px 10px">
          {{ props.mode === 'messages' ? '太好了，当前没有未读消息与预警' : '当前没有待处理任务' }}
          <div style="margin-top:12px"><button class="ghost-action" type="button" @click="refresh">↻ 刷新确认</button></div>
        </div>
      </div>
    </section>

    <section class="page-card dashboard-card" style="margin-top:18px">
      <div class="section-head">
        <div>
          <p class="section-label">Handled</p>
          <h2 class="section-title">{{ handledLabel }}（{{ handledEntries.length }}）</h2>
          <p class="section-subtitle">完成后保留处理人、处理时间和结论；历史记录不可物理删除</p>
        </div>
      </div>
      <div class="todo-list">
        <div v-for="item in handledEntries" :key="item.id" class="todo-item" style="opacity:.72">
          <span class="todo-item__mark" style="color:#8fbfae">✓</span>
          <div class="todo-item__content">
            <strong>{{ item.title }}</strong>
            <small>{{ item.detail }}</small>
            <small style="color:#a0abb9">{{ handledVerb }}于 {{ item.handledAt ?? '时间未记录' }} · 来源：{{ item.source }}<template v-if="item.handledNote"> · {{ item.handledNote }}</template></small>
          </div>
          <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
            <StatusBadge :label="handledVerb" tone="teal" />
          </div>
        </div>
        <div v-if="!handledEntries.length" class="table-empty" style="padding:22px 10px">暂无{{ handledLabel }}，完成或标记已读后会出现在这里</div>
      </div>
    </section>

    <Teleport to="body">
      <div class="toast-stack" aria-live="polite">
        <div v-for="item in toasts" :key="item.id" class="toast-item">{{ item.text }}</div>
      </div>
    </Teleport>
  </AppShell>
</template>

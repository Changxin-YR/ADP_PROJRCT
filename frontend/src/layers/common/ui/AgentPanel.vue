<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { createSessionStore } from '../session/session.store'
import { ApiError, errorText } from '../api/errors'
import { cancelAgentConfirmation, confirmAgent, sendAgentTurn } from '../../features/agent/agent.service'
import type { AgentConfirmation, AgentMessageRole, AgentTurnResult } from '../../features/agent/agent.models'

interface Message { id: number; role: AgentMessageRole; text: string; result?: AgentTurnResult }

const router = useRouter()
const session = createSessionStore()
const assistantName = '塘小助'
const open = ref(false)
const input = ref('')
const busy = ref(false)
const error = ref('')
const conversationId = ref<string>()
const confirmation = ref<AgentConfirmation>()
const messages = ref<Message[]>([])
const launcherElement = ref<HTMLButtonElement>()
const inputElement = ref<HTMLTextAreaElement>()
let messageId = 0

const available = computed(() => session.user.value?.status === 'active')
const panelLabel = computed(() => open.value ? `关闭${assistantName}` : `打开${assistantName}`)

function textOf(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === undefined || value === null) return '操作已完成'
  try { return JSON.stringify(value, null, 2) } catch { return '操作已完成' }
}

function append(role: AgentMessageRole, text: string, result?: AgentTurnResult): void {
  messages.value.push({ id: ++messageId, role, text, result })
}

function handleAuthError(value: unknown): boolean {
  if (value instanceof ApiError && value.status === 401) {
    session.clear()
    void router.replace({ path: '/auth/login', query: { redirect: router.currentRoute.value.fullPath } })
    return true
  }
  return false
}

function applyResult(result: AgentTurnResult): void {
  confirmation.value = result.confirmation
  if (result.kind === 'confirmation_required' && result.confirmation) {
    append('assistant', result.confirmation.summary, result)
  } else if (result.kind === 'human_only') {
    append('assistant', result.message || '该操作需要人工在管理页面完成', result)
  } else if (result.kind === 'assistant') {
    append('assistant', result.message || `${assistantName}已返回结果`, result)
  } else {
    append('assistant', textOf(result.data), result)
  }
}

async function submit(): Promise<void> {
  const message = input.value.trim()
  if (!message || busy.value || !available.value) return
  input.value = ''
  error.value = ''
  append('user', message)
  busy.value = true
  try {
    const result = await sendAgentTurn(message, conversationId.value)
    conversationId.value ||= result.conversation_id || result.confirmation?.conversation_id || result.session_id
    applyResult(result)
  } catch (value) {
    if (!handleAuthError(value)) error.value = errorText(value, `${assistantName}暂时不可用，请稍后重试`)
  } finally { busy.value = false; await nextTick(); inputElement.value?.focus() }
}

async function confirm(): Promise<void> {
  const pending = confirmation.value
  if (!pending || busy.value) return
  busy.value = true
  error.value = ''
  try {
    applyResult(await confirmAgent(pending.token))
    confirmation.value = undefined
  } catch (value) {
    if (!handleAuthError(value)) error.value = errorText(value, '确认未完成，请刷新后重试')
  } finally { busy.value = false }
}

async function cancel(): Promise<void> {
  const pending = confirmation.value
  if (!pending || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await cancelAgentConfirmation(pending.id)
    confirmation.value = undefined
    append('system', '已取消该操作')
  } catch (value) {
    if (!handleAuthError(value)) error.value = errorText(value, '取消未完成，请稍后重试')
  } finally { busy.value = false }
}

function toggle(): void {
  open.value = !open.value
  if (open.value) void nextTick(() => inputElement.value?.focus())
  else void nextTick(() => launcherElement.value?.focus())
}
</script>

<template>
  <div v-if="available" class="agent-widget">
    <button ref="launcherElement" class="agent-launcher" type="button" :aria-label="panelLabel" :aria-expanded="open" @click="toggle">
      <AppIcon :name="open ? 'close' : 'target'" :size="18" />
      <span>{{ assistantName }}</span>
    </button>

    <section v-if="open" class="agent-panel" role="dialog" aria-modal="false" :aria-label="assistantName" @keydown.esc="toggle">
      <header class="agent-panel__header">
        <div><strong>{{ assistantName }}</strong><small>当前账号权限内的 ADP 操作</small></div>
        <button class="agent-panel__close" type="button" :aria-label="`关闭${assistantName}`" @click="toggle"><AppIcon name="close" :size="17" /></button>
      </header>
      <div class="agent-panel__messages" aria-live="polite">
        <p v-if="!messages.length" class="agent-panel__empty">请输入查询或业务指令</p>
        <article v-for="item in messages" :key="item.id" class="agent-message" :class="`agent-message--${item.role}`">
          <span>{{ item.text }}</span>
          <code v-if="item.result?.request_id">{{ item.result.request_id }}</code>
        </article>
        <div v-if="confirmation" class="agent-confirmation" data-testid="agent-confirmation">
          <strong>{{ confirmation.summary }}</strong>
          <p>{{ confirmation.risk }}</p>
          <pre>{{ JSON.stringify(confirmation.arguments, null, 2) }}</pre>
          <div class="agent-confirmation__actions">
            <button type="button" data-testid="agent-cancel" :disabled="busy" @click="cancel">取消</button>
            <button type="button" data-testid="agent-confirm" :disabled="busy" @click="confirm">确认执行</button>
          </div>
        </div>
        <p v-if="error" class="agent-panel__error" role="alert">{{ error }}</p>
      </div>
      <form class="agent-panel__composer" @submit.prevent="submit">
        <textarea ref="inputElement" v-model="input" rows="2" :aria-label="`${assistantName}指令`" placeholder="例如：查询我有权限查看的鱼塘" :disabled="busy" @keydown.enter.exact.prevent="submit" />
        <button type="submit" aria-label="发送指令" :disabled="busy || !input.trim()"><AppIcon name="exchange" :size="17" /><span>发送</span></button>
      </form>
    </section>
  </div>
</template>

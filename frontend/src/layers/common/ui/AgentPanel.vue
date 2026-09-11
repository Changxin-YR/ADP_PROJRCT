<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { createSessionStore } from '../session/session.store'
import { ApiError, errorText } from '../api/errors'
import { cancelAgentConfirmation, confirmAgent, sendAgentTurn, sendAgentTurnStream } from '../../features/agent/agent.service'
import type { AgentClarification, AgentConfirmation, AgentMessageRole, AgentTurnResult } from '../../features/agent/agent.models'
import { humanTextBlock, humanizeConfirmation, humanizeTurn } from '../../features/agent/agent.humanize'
import { sanitizeTechnical } from '../../features/agent/agent.phrasing'

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
const clarification = ref<AgentClarification>()
const streamingText = ref('')
const statusHint = ref('')
const answerText = ref('')
const messages = ref<Message[]>([])
const launcherElement = ref<HTMLButtonElement>()
const inputElement = ref<HTMLTextAreaElement>()
let messageId = 0

const available = computed(() => session.user.value?.status === 'active')
const panelLabel = computed(() => open.value ? `关闭${assistantName}` : `打开${assistantName}`)
// 确认卡片按业务措辞渲染：中文动作名 + 影响对象 + 填写内容，不再展示 JSON。
const confirmationView = computed(() => (confirmation.value ? humanizeConfirmation(confirmation.value) : undefined))
// 澄清问题由模型生成，仍过一遍去技术标识；选项保持原样（点选后会原样发给后端）。
const clarificationQuestion = computed(() => (clarification.value ? sanitizeTechnical(String(clarification.value.question ?? '')) : ''))

function traceHint(item: Message): string | undefined {
  // 追踪编号只进 hover 提示，正文里不出现
  const id = item.result?.request_id
  return id ? `追踪编号：${id}` : undefined
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
  if (result.kind === 'clarification' && result.clarification) clarification.value = result.clarification
  // 澄清卡片自己会显示问题，后端没另给正文就不重复追加一条气泡。
  if (result.kind === 'clarification' && !result.message) return
  const text = humanTextBlock(humanizeTurn(result))
  if (text) append('assistant', text, result)
}

function agentErrorText(value: unknown): string {
  // 5xx from /agent/turn is an agent-runtime failure, not a business error: tell the
  // user what to actually do instead of showing "服务器暂时无法处理请求".
  if (value instanceof ApiError) {
    if (value.code === 'AGENT_TIMEOUT') return '这轮处理时间过长已被取消，请把问题拆小一点（例如一次只查一类记录）后重试'
    if (value.code === 'AGENT_PROTOCOL_ERROR' || value.code === 'AGENT_UNAVAILABLE') return `智能助手这一轮没有跑完，请重试；若反复出现，请把问题拆成更小的步骤`
  }
  return errorText(value, `${assistantName}暂时不可用，请稍后重试`)
}

async function submitText(text: string): Promise<void> {
  const message = text.trim()
  if (!message || busy.value || !available.value) return
  clarification.value = undefined
  answerText.value = ''
  error.value = ''
  append('user', message)
  busy.value = true
  try {
    const history = messages.value.slice(-8).map((item) => ({ role: item.role, text: item.text }))
    const context = { contextPath: router.currentRoute.value.fullPath, history }
    streamingText.value = ''
    statusHint.value = ''
    let result: AgentTurnResult
    try {
      result = await sendAgentTurnStream(message, conversationId.value, context, (chunk) => {
        if (chunk.type === 'delta' && chunk.text) {
          streamingText.value += chunk.text
          statusHint.value = ''   // 文字重新出现就收起状态行，避免与正文抢注意力
        }
        else if (chunk.type === 'status' && chunk.text) statusHint.value = chunk.text
      })
    } catch (streamError) {
      // 只有端点缺失（部署期）才回退到非流式；其它错误直接上报，避免写操作被重复执行。
      if (streamError instanceof ApiError && (streamError.status === 404 || streamError.status === 405)) {
        result = await sendAgentTurn(message, conversationId.value, context)
      } else {
        throw streamError
      }
    } finally {
      streamingText.value = ''
      statusHint.value = ''
    }
    conversationId.value ||= result.conversation_id || result.confirmation?.conversation_id || result.session_id
    applyResult(result)
  } catch (value) {
    if (!handleAuthError(value)) error.value = agentErrorText(value)
  } finally { busy.value = false; await nextTick(); inputElement.value?.focus() }
}

async function submit(): Promise<void> {
  const message = input.value.trim()
  if (!message || busy.value || !available.value) return
  input.value = ''
  await submitText(message)
}

async function clickOption(option: string): Promise<void> {
  clarification.value = undefined
  answerText.value = ''
  await submitText(option)
}

async function submitAnswer(): Promise<void> {
  const answer = answerText.value.trim()
  if (!answer) return
  clarification.value = undefined
  answerText.value = ''
  await submitText(answer)
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
        <article v-for="item in messages" :key="item.id" class="agent-message" :title="traceHint(item)" :class="`agent-message--${item.role}`">
          <span>{{ item.text }}</span>
        </article>
        <div v-if="confirmation && confirmationView" class="agent-confirmation" data-testid="agent-confirmation">
          <strong>即将执行：{{ confirmationView.title }}</strong>
          <p v-if="confirmationView.detail" class="agent-confirmation__detail">{{ confirmationView.detail }}</p>
          <p>影响对象：{{ confirmationView.target }}</p>
          <div class="agent-confirmation__fields">
            <span class="agent-confirmation__fields-title">填写内容</span>
            <dl v-if="confirmationView.rows.length" class="agent-confirmation__rows" data-testid="agent-confirmation-rows">
              <div v-for="row in confirmationView.rows" :key="row.label" class="agent-confirmation__row">
                <dt>{{ row.label }}</dt>
                <dd>{{ row.value }}</dd>
              </div>
            </dl>
            <p v-else class="agent-confirmation__empty">无需额外填写内容</p>
          </div>
          <p>{{ confirmationView.risk }}</p>
          <p v-if="confirmationView.expiresAt" class="agent-confirmation__expiry">{{ confirmationView.expiresAt }}</p>
          <div class="agent-confirmation__actions">
            <button type="button" data-testid="agent-cancel" :disabled="busy" @click="cancel">取消</button>
            <button type="button" data-testid="agent-confirm" :disabled="busy" @click="confirm">确认执行</button>
          </div>
        </div>
        <div v-if="clarification" class="agent-clarification" data-testid="agent-clarification">
          <strong>{{ clarificationQuestion }}</strong>
          <div v-if="clarification.options?.length" class="agent-clarification__options">
            <button
              v-for="option in clarification.options"
              :key="option"
              type="button"
              :disabled="busy"
              data-testid="agent-clarification-option"
              @click="clickOption(option)"
            >{{ option }}</button>
          </div>
          <form v-if="clarification.allow_free_text !== false" class="agent-clarification__answer" @submit.prevent="submitAnswer">
            <input
              v-model="answerText"
              type="text"
              :disabled="busy"
              placeholder="请输入补充说明或选择上面的选项"
              data-testid="agent-clarification-input"
              aria-label="补充说明"
            />
            <button type="submit" :disabled="busy || !answerText.trim()">提交</button>
          </form>
        </div>
        <p v-if="statusHint" class="agent-status" data-testid="agent-status">{{ statusHint }}</p>
        <article v-if="streamingText" class="agent-message agent-message--assistant" data-testid="agent-streaming">
          <span>{{ streamingText }}</span>
        </article>
        <p v-if="error" class="agent-panel__error" role="alert">{{ error }}</p>
      </div>
      <form class="agent-panel__composer" @submit.prevent="submit">
        <textarea ref="inputElement" v-model="input" rows="2" :aria-label="`${assistantName}指令`" placeholder="例如：查询我有权限查看的鱼塘" :disabled="busy" @keydown.enter.exact.prevent="submit" />
        <button type="submit" aria-label="发送指令" :disabled="busy || !input.trim()"><AppIcon name="exchange" :size="17" /><span>发送</span></button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createSessionStore } from '../session/session.store'
import { hasPermission } from '../security/access-control'
import { logout } from '../../features/auth/public'
import ActionButton from './ActionButton.vue'
import AppIcon from './AppIcon.vue'
import { listPonds } from '../../features/workbench/workbench.service'
import { getNotifications, getWorkItems, type NotificationRecord } from '../../features/workbench/workbench.service'
import type { PondSummary } from '../../common/api/workbench.models'
import { helpSections, navGroups, type NavGroup, type NavItem } from './app-shell/navigation'

const props = withDefaults(defineProps<{ title?: string; eyebrow?: string; breadcrumbs?: string[] }>(), { title: '工作台', eyebrow: 'ADP / OPERATIONS' })
watchEffect(() => { document.title = `${props.title} · ADP 养殖运营平台` })
const route = useRoute()
const router = useRouter()
const session = createSessionStore()
const displayName = computed(() => session.user.value?.name || '管理员')
const roleName = computed(() => session.user.value?.roles[0]?.name || '业务成员')
const activePath = computed(() => route.path)

const visibleGroups = computed<NavGroup[]>(() => navGroups
  .map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.requiredPermission || hasPermission(session.user.value, item.requiredPermission)),
  }))
  .filter((group) => group.items.length > 0))
const groupActive = (group: NavGroup) => group.items.some((item) => activePath.value === item.to || activePath.value.startsWith(`${item.to}/`))
const overrides = ref<Record<string, boolean>>({})
const isOpen = (group: NavGroup) => overrides.value[group.code] ?? groupActive(group)
const toggle = (group: NavGroup) => { overrides.value[group.code] = !isOpen(group) }
const mobileNavOpen = ref(false)
const mobileNavToggle = ref<HTMLButtonElement>()
const mobileNav = ref<HTMLElement>()
const mobileNavClose = ref<HTMLButtonElement>()
function closeMobileNav() {
  if (!mobileNavOpen.value) return
  mobileNavOpen.value = false
  mobileNavToggle.value?.focus()
}
async function toggleMobileNav() {
  if (mobileNavOpen.value) { closeMobileNav(); return }
  mobileNavOpen.value = true
  await nextTick()
  mobileNavClose.value?.focus()
}
function trapMobileNavFocus(event: KeyboardEvent) {
  if (!mobileNavOpen.value || event.key !== 'Tab' || !mobileNav.value) return
  const focusable = [...mobileNav.value.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')]
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

// 帮助浮层（功能文档 15.3 使用帮助：分模块操作指引）
const helpOpen = ref(false)

async function signOut() {
  try { await logout() } catch { /* session is still cleared for offline/demo mode */ }
  session.clear()
  await router.replace('/auth/login')
}

// ===== 顶部全局搜索：匹配菜单页面与塘口档案（塘口数据懒加载，仅首次聚焦时拉取） =====
interface SearchHit { to: string; title: string; sub: string }
const searchQuery = ref('')
const searchOpen = ref(false)
const searchInput = ref<HTMLInputElement>()
const searchRoot = ref<HTMLElement>()
const ponds = ref<PondSummary[]>([])
let pondsLoaded = false
async function ensurePonds() {
  if (pondsLoaded) return
  pondsLoaded = true
  try { ponds.value = (await listPonds()).items } catch { /* 离线/演示环境下仅搜索菜单 */ }
}
const quickLinks: NavItem[] = [
  { to: '/workbench', label: '工作台' },
  { to: '/messages', label: '消息与预警' },
  { to: '/todos', label: '我的待办' },
]
const searchHits = computed<SearchHit[]>(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return []
  const hits: SearchHit[] = []
  for (const link of quickLinks) if (link.label.toLowerCase().includes(query)) hits.push({ to: link.to, title: link.label, sub: '快速入口' })
  for (const group of visibleGroups.value) for (const item of group.items)
    if (item.label.toLowerCase().includes(query)) hits.push({ to: item.to, title: item.label, sub: `业务模块 · ${group.label}` })
  for (const pond of ponds.value)
    if (`${pond.name}${pond.pond_code}${pond.area_name}${pond.species}`.toLowerCase().includes(query)) hits.push({ to: `/ponds/${pond.id}`, title: pond.name, sub: `塘口档案 · ${pond.pond_code} · ${pond.area_name}` })
  return hits.slice(0, 8)
})
function goHit(hit: SearchHit) { searchOpen.value = false; searchQuery.value = ''; searchInput.value?.blur(); router.push(hit.to) }
function goFirstHit() { if (searchHits.value.length) goHit(searchHits.value[0]) }

// ===== 顶部通知面板：库存预警 / 应付逾期 / 应收逾期（与消息中心同源） =====
interface NoticeItem { id: string; title: string; detail: string; to: string; tone: 'rose' | 'amber' }
const noticeOpen = ref(false)
const noticeRoot = ref<HTMLElement>()
const notices = ref<NoticeItem[]>([])
const noticeCount = ref(0)
const todoCount = ref(0)
const collaborationError = ref('')
const canViewQueue = computed(() => hasPermission(session.user.value, 'work_item.view'))
const modulePath = (code: string) => ({ master_data: '/ponds', production: '/batches', warehouse: '/warehouse/alerts', purchase: '/purchase/payables', sales: '/sales/receivables', cost: '/cost/expenses' }[code] ?? '/workbench')
function notice(item: NotificationRecord): NoticeItem {
  return { id: String(item.id), title: item.title, detail: item.body ?? `${item.occurrence_count} 次提醒`, to: modulePath(item.module_code), tone: item.level === 'high' || item.level === 'critical' ? 'rose' : 'amber' }
}
async function loadCollaboration() {
  if (!canViewQueue.value) return
  collaborationError.value = ''
  try {
    const [notificationPage, workItemPage] = await Promise.all([getNotifications(false), getWorkItems(false)])
    notices.value = notificationPage.items.map(notice)
    noticeCount.value = notificationPage.total
    todoCount.value = workItemPage.total
  } catch { collaborationError.value = '协作数据加载失败，请进入消息中心重试' }
}

// ===== 全局快捷键（Ctrl/Cmd+K 聚焦搜索）与点击外部关闭浮层 =====
function onGlobalKeydown(event: KeyboardEvent) {
  trapMobileNavFocus(event)
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); searchOpen.value = true; ensurePonds(); searchInput.value?.focus() }
  if (event.key === 'Escape') { searchOpen.value = false; noticeOpen.value = false; if (mobileNavOpen.value) closeMobileNav() }
}
function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (!searchRoot.value?.contains(target)) searchOpen.value = false
  if (!noticeRoot.value?.contains(target)) noticeOpen.value = false
}
onMounted(() => { window.addEventListener('keydown', onGlobalKeydown); document.addEventListener('click', onDocumentClick); void loadCollaboration() })
onBeforeUnmount(() => { window.removeEventListener('keydown', onGlobalKeydown); document.removeEventListener('click', onDocumentClick) })

// ===== 退出登录确认（避免误触直接登出） =====
const signOutOpen = ref(false)
</script>

<template>
  <div class="workbench-app">
    <aside ref="mobileNav" class="workbench-sidebar" :class="{ 'is-mobile-open': mobileNavOpen }">
      <RouterLink class="workspace-brand" to="/workbench" aria-label="返回工作台">
        <span class="workspace-brand__mark"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 26c7-13 19-17 31-7-4 2-6 5-7 8 5 1 8 3 10 6-13 6-25 3-34-7Zm12-5c2 3 4 4 8 5" /></svg></span>
        <span><strong>ADP</strong><small>养殖运营平台</small></span>
      </RouterLink>
      <button ref="mobileNavClose" class="mobile-nav-close" type="button" aria-label="关闭导航" @click="closeMobileNav"><AppIcon name="close" :size="19" /></button>

      <div class="sidebar-caption">运营总览</div>
      <nav class="side-nav" aria-label="主导航">
        <RouterLink to="/workbench" :class="{ 'is-current': activePath === '/workbench' }" @click="closeMobileNav"><AppIcon class="nav-icon" name="home" :size="17" /><span>工作台</span></RouterLink>
      </nav>

      <div v-if="canViewQueue" class="sidebar-caption sidebar-caption--spaced">协作中心</div>
      <nav v-if="canViewQueue" class="side-nav" aria-label="协作导航">
        <RouterLink to="/messages" :class="{ 'is-current': activePath === '/messages' }" @click="closeMobileNav"><AppIcon class="nav-icon" name="bell" :size="17" /><span>消息与预警</span><b v-if="noticeCount" data-testid="notification-count" class="nav-count">{{ noticeCount }}</b></RouterLink>
        <RouterLink to="/todos" :class="{ 'is-current': activePath === '/todos' }" @click="closeMobileNav"><AppIcon class="nav-icon" name="check" :size="17" /><span>我的待办</span><b v-if="todoCount" data-testid="todo-count" class="nav-count nav-count--amber">{{ todoCount }}</b></RouterLink>
      </nav>

      <div class="sidebar-caption sidebar-caption--spaced">业务模块</div>
      <nav class="side-nav side-nav--scroll" aria-label="业务模块导航">
        <div v-for="group in visibleGroups" :key="group.code" class="nav-group" :class="{ 'is-open': isOpen(group), 'is-active': groupActive(group) }">
          <button class="nav-group__head" type="button" :aria-expanded="isOpen(group)" @click="toggle(group)">
            <AppIcon class="nav-icon" :name="group.icon" :size="17" />
            <span>{{ group.label }}</span>
            <AppIcon class="nav-group__caret" name="chevron-down" :size="15" />
          </button>
          <div v-show="isOpen(group)" class="nav-group__body">
              <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" :class="{ 'is-current': activePath === item.to || activePath.startsWith(`${item.to}/`) }" @click="closeMobileNav">
              <span>{{ item.label }}</span>
              <b v-if="item.count" class="nav-count" :class="item.countTone === 'rose' ? 'nav-count--rose' : item.countTone === 'teal' ? 'nav-count--teal' : 'nav-count--amber'">{{ item.count }}</b>
            </RouterLink>
          </div>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="environment-pill"><i />生产工作区 <span>WEB</span></div>
        <button class="sidebar-help" type="button" @click="helpOpen = true"><AppIcon name="help" :size="14" /> 使用帮助</button>
      </div>
    </aside>

    <div v-if="mobileNavOpen" class="mobile-nav-backdrop" aria-hidden="true" @click="closeMobileNav" />

    <section class="workbench-main">
      <header class="workbench-header">
        <button ref="mobileNavToggle" class="mobile-nav-toggle" type="button" :aria-label="mobileNavOpen ? '关闭导航' : '打开导航'" :aria-expanded="mobileNavOpen" @click="toggleMobileNav"><AppIcon :name="mobileNavOpen ? 'close' : 'menu'" :size="19" /></button>
        <div class="header-breadcrumbs"><span>{{ eyebrow }}</span><i>/</i><strong>{{ title }}</strong><template v-if="breadcrumbs?.length"><i>/</i><span v-for="item in breadcrumbs" :key="item">{{ item }}</span></template></div>
        <div class="header-actions">
          <div ref="searchRoot" class="header-popover-wrap">
            <label class="global-search" :class="{ 'is-focused': searchOpen }"><AppIcon class="global-search__icon" name="search" :size="16" /><input ref="searchInput" v-model="searchQuery" placeholder="搜索塘口、批次或编号" aria-label="全局搜索" @focus="searchOpen = true; ensurePonds()" @keydown.enter.prevent="goFirstHit" @keydown.esc="searchOpen = false" /><kbd>Ctrl K</kbd></label>
            <div v-if="searchOpen && searchQuery.trim()" class="header-popover search-panel" role="listbox" aria-label="搜索结果">
              <p v-if="!searchHits.length" class="search-panel__empty">没有匹配的页面或塘口，换个关键字试试（支持：菜单名称、塘口名称、编号、区域、品种）</p>
              <button v-for="hit in searchHits" :key="hit.to + hit.title" type="button" class="search-panel__hit" role="option" @click="goHit(hit)"><strong>{{ hit.title }}</strong><small>{{ hit.sub }}</small></button>
            </div>
          </div>
          <div ref="noticeRoot" class="header-popover-wrap">
            <button class="header-icon-button" type="button" aria-label="消息与预警" :aria-expanded="noticeOpen" @click="noticeOpen = !noticeOpen"><AppIcon name="bell" :size="17" /><i v-if="noticeCount">{{ noticeCount > 9 ? '9+' : noticeCount }}</i></button>
            <div v-if="noticeOpen" class="header-popover notice-panel" role="dialog" aria-label="未读通知">
              <div class="notice-panel__head"><strong>未读通知（{{ noticeCount }}）</strong><RouterLink class="table-link" to="/messages" @click="noticeOpen = false">全部消息</RouterLink></div>
              <p v-if="collaborationError" class="search-panel__empty" role="alert">{{ collaborationError }}</p>
              <button v-for="item in notices.slice(0, 5)" :key="item.id" type="button" class="notice-panel__item" :class="`notice-panel__item--${item.tone}`" @click="noticeOpen = false; router.push(item.to)">
                <strong>{{ item.title }}</strong><small>{{ item.detail }}</small><small class="notice-panel__go">去处理 →</small>
              </button>
              <p v-if="!noticeCount" class="search-panel__empty">暂无未读预警与逾期提醒</p>
              <RouterLink class="notice-panel__foot" to="/messages" @click="noticeOpen = false">查看全部 {{ noticeCount }} 条消息与预警 →</RouterLink>
            </div>
          </div>
          <div class="header-user"><span class="user-avatar">{{ displayName.slice(0, 1) }}</span><span><strong>{{ displayName }}</strong><small>{{ roleName }}</small></span><button type="button" class="header-user__exit" aria-label="退出登录" @click="signOutOpen = true">退出</button></div>
        </div>
      </header>
      <main class="workbench-content"><slot /></main>
    </section>

    <Teleport to="body">
      <div v-if="signOutOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="退出登录确认" @click.self="signOutOpen = false">
        <div class="modal-panel" style="width:min(440px,100%)">
          <div class="modal-panel__head">
            <div><p class="section-label">Sign out</p><h2>退出当前账号？</h2></div>
            <ActionButton variant="quiet" compact icon="close" label="关闭退出确认" @click="signOutOpen = false" />
          </div>
          <p class="section-subtitle" style="line-height:1.8">确认退出「{{ displayName }}」的登录状态。退出后需重新登录才能继续操作，当前页面未提交的临时内容将被清除。</p>
          <div class="modal-panel__foot">
            <ActionButton @click="signOutOpen = false">取消，继续操作</ActionButton>
            <ActionButton variant="danger" icon="logout" @click="signOutOpen = false; signOut()">确认退出</ActionButton>
          </div>
        </div>
      </div>

      <div v-if="helpOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="使用帮助" @click.self="helpOpen = false">
        <div class="modal-panel" style="width:min(640px,100%)">
          <div class="modal-panel__head">
            <div><p class="section-label">Help center</p><h2>使用帮助 · 分模块操作指引</h2></div>
            <ActionButton variant="quiet" compact icon="close" label="关闭使用帮助" @click="helpOpen = false" />
          </div>
          <div class="help-sections">
            <section v-for="section in helpSections" :key="section.title" class="help-section">
              <strong>{{ section.title }}</strong>
              <p>{{ section.body }}</p>
            </section>
          </div>
          <p class="section-subtitle" style="margin-top:6px">如需新增操作指引或调整流程规则，请联系管理员在「业务参数」中维护。</p>
          <div class="modal-panel__foot"><ActionButton variant="primary" @click="helpOpen = false">我知道了</ActionButton></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

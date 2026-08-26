<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AuthLayout from './AuthLayout.vue'
import { getCurrentUser, logout } from '../../features/auth/public'
import { createSessionStore } from '../../common/session/session.store'
import { hasAnyPermission } from '../../common/security/access-control'
import { useRouter } from 'vue-router'

const router = useRouter(); const session = createSessionStore(); const name = ref('管理员')
const canManageAccounts = computed(() => hasAnyPermission(session.user.value, ['auth.review', 'auth.user.manage']))
const roleLabel = computed(() => session.user.value?.roles.map((role) => role.name).join('、') || '正式成员')
onMounted(async () => { try { const result = await getCurrentUser(); name.value = result.user.name; session.setUser(result.user) } catch { /* 路由守卫已完成身份校验，保留工作区骨架 */ } })
async function signOut() { try { await logout() } finally { session.clear(); await router.replace('/auth/login') } }
</script>
<template>
  <AuthLayout wide>
    <div class="workspace-shell">
      <div class="workspace-hero">
        <div><p class="status-kicker">正式工作区 / {{ canManageAccounts ? '系统管理' : '业务协作' }}</p><h2>欢迎回来，{{ name }}</h2><p class="status-description">今天也从清晰的记录开始。你的账号已完成身份验证，当前角色为 {{ roleLabel }}。</p></div>
        <span class="workspace-badge"><i /> 已验证</span>
      </div>
      <div class="metric-grid" aria-label="工作区概览">
        <div class="metric-card"><span>当前状态</span><strong>运行正常</strong><small>会话与权限已同步</small></div>
        <div class="metric-card"><span>数据范围</span><strong>{{ session.user.value?.data_scopes.length || 0 }} 个区域</strong><small>按授权范围展示</small></div>
        <div class="metric-card"><span>下一步</span><strong>{{ canManageAccounts ? '处理审核' : '查看业务模块' }}</strong><small>从快捷入口继续</small></div>
      </div>
      <section class="workspace-section" aria-labelledby="workspace-entry-title">
        <div class="section-heading"><div><p class="status-kicker">快捷入口</p><h3 id="workspace-entry-title">从这里继续</h3></div><span class="section-caption">功能模块将逐步接入</span></div>
        <nav v-if="canManageAccounts" class="workbench-nav" aria-label="系统管理"><RouterLink class="management-link" to="/admin/applications"><span><strong>申请审核</strong><small>查看并处理待审核注册</small></span></RouterLink><RouterLink class="management-link" to="/admin/users"><span><strong>账号管理</strong><small>管理账号、状态与初始密码</small></span></RouterLink></nav>
        <div v-else class="workspace-empty"><span class="empty-mark">⌁</span><div><strong>业务模块准备中</strong><p>塘口、喂养和库存模块将在后续功能阶段接入。</p></div></div>
      </section>
      <button class="secondary-action" type="button" @click="signOut">退出登录</button>
    </div>
  </AuthLayout>
</template>

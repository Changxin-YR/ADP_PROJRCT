<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthLayout from './AuthLayout.vue'
import { getCurrentUser, logout } from '../../features/auth/public'
import { getApplication } from '../../features/registration/public'
import { createSessionStore } from '../../common/session/session.store'
import type { ApplicationSummary, UserSummary } from '../../common/api/models'

const router = useRouter()
const route = useRoute()
const session = createSessionStore()
const user = ref<UserSummary | null>(null)
const application = ref<ApplicationSummary | null>(null)
const loadError = ref('')
const submitted = ref(route.query.submitted === '1')

function display(value: string | number | null | undefined): string { return value === null || value === undefined || value === '' ? '—' : String(value) }

onMounted(async () => {
  try {
    const [current, record] = await Promise.all([getCurrentUser(), getApplication()])
    user.value = current.user
    application.value = record.application
    session.setUser(current.user)
  } catch { loadError.value = '审核状态暂时无法加载，请稍后重试' }
})

async function signOut() {
  try { await logout() } finally { session.clear(); await router.push('/auth/login') }
}
</script>

<template>
  <AuthLayout>
    <div class="status-panel">
      <span class="status-icon pending-icon" aria-hidden="true">◌</span>
      <p class="status-kicker">申请状态</p>
      <h2>审核中</h2>
      <p class="status-description">你的注册申请已收到，管理员审核通过后会开放业务数据。</p>
      <div v-if="submitted" class="success-message" role="status"><strong>注册申请提交成功</strong><span>资料已保存，管理员审核通过后会开放对应工作区。</span></div>
      <div class="status-banner"><span class="status-icon pending-icon" aria-hidden="true">◌</span><div><strong>申请已提交，正在等待管理员审核</strong><span>审核通过后会按最终角色和数据范围开放工作区</span></div></div>
      <p v-if="loadError" class="field-error" role="alert">{{ loadError }}</p>
      <dl v-if="user" class="status-details">
        <div><dt>姓名</dt><dd>{{ user.name }}</dd></div>
        <div><dt>手机号</dt><dd>{{ user.phone }}</dd></div>
        <div><dt>申请岗位</dt><dd>{{ display(application?.desired_role_name) }}</dd></div>
        <div><dt>所属区域/基地</dt><dd>{{ display(application?.area_name) }}</dd></div>
        <div><dt>提交时间</dt><dd>{{ display(application?.submitted_at || application?.created_at) }}</dd></div>
        <div><dt>最近更新时间</dt><dd>{{ display(application?.updated_at) }}</dd></div>
        <div><dt>管理员说明</dt><dd>{{ application?.admin_message || '申请正在等待管理员审核。' }}</dd></div>
        <div><dt>申请版本</dt><dd>第 {{ application?.version_no ?? 1 }} 版</dd></div>
      </dl>
      <div class="timeline" aria-label="审核流程"><div class="timeline-step done"><strong>已提交申请</strong>资料已安全保存</div><div class="timeline-step"><strong>管理员审核</strong>审核通过后即可进入正式工作区</div><div class="timeline-step"><strong>开放业务权限</strong>按最终角色和数据范围开放</div></div>
      <button class="secondary-action" type="button" @click="signOut">退出登录</button>
    </div>
  </AuthLayout>
</template>

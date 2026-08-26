<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthLayout from './AuthLayout.vue'
import FormField from '../../common/ui/FormField.vue'
import { getCurrentUser, logout } from '../../features/auth/public'
import { fetchRegistrationOptions, getApplication, resubmitApplication, type RegistrationOptions } from '../../features/registration/public'
import { createSessionStore } from '../../common/session/session.store'
import type { ApplicationSummary, UserSummary } from '../../common/api/models'
import { ApiError } from '../../common/api/errors'

const router = useRouter()
const session = createSessionStore()
const user = ref<UserSummary | null>(null)
const application = ref<ApplicationSummary | null>(null)
const form = reactive({ name: '', desired_role_id: 0, area_id: 0, desired_scope_type: 'area' as 'farm' | 'area' | 'personal', application_note: '' })
const options = ref<RegistrationOptions>({ roles: [], areas: [], data_scopes: [] })
const error = ref('')
const submitting = ref(false)

onMounted(async () => {
  try {
    const [loadedOptions, current, record] = await Promise.all([fetchRegistrationOptions(), getCurrentUser(), getApplication()])
    options.value = loadedOptions
    user.value = current.user; session.setUser(current.user); application.value = record.application
    if (record.application) Object.assign(form, { name: record.application.name, desired_role_id: record.application.desired_role_id, area_id: record.application.area_id, desired_scope_type: record.application.desired_scope_type ?? 'area', application_note: record.application.application_note })
  } catch { error.value = '申请信息暂时无法加载' }
})

async function submit() {
  submitting.value = true; error.value = ''
  try { await resubmitApplication(form); await router.push('/auth/pending') }
  catch (reason) { error.value = reason instanceof ApiError ? reason.message : '网络异常，请稍后重试' }
  finally { submitting.value = false }
}

async function signOut() { try { await logout() } finally { session.clear(); await router.push('/auth/login') } }
</script>

<template>
  <AuthLayout>
    <div class="status-panel">
      <span class="status-icon rejected-icon" aria-hidden="true">!</span>
      <p class="status-kicker">申请状态</p>
      <h2>需要补充申请</h2>
      <div class="reason-banner"><strong>管理员审核意见</strong>{{ application?.rejection_reason || '请根据管理员意见修改申请资料。' }}</div>
      <p v-if="error" class="field-error" role="alert">{{ error }}</p>
      <form @submit.prevent="submit">
        <div class="auth-field-grid"><FormField id="rejected-name" label="姓名"><input id="rejected-name" v-model="form.name" /></FormField><FormField id="rejected-role" label="申请岗位"><select id="rejected-role" v-model="form.desired_role_id"><option v-for="role in options.roles" :key="role.id" :value="role.id">{{ role.name }}</option></select></FormField><FormField id="rejected-scope" label="申请数据范围"><select id="rejected-scope" v-model="form.desired_scope_type"><option value="farm">全场数据（所有基地）</option><option value="area">区域数据（指定基地）</option><option value="personal">仅本人数据</option></select></FormField><FormField v-if="form.desired_scope_type === 'area'" id="rejected-area" label="所属区域/基地"><select id="rejected-area" v-model="form.area_id"><option v-for="area in options.areas" :key="area.id" :value="area.id">{{ area.name }}</option></select></FormField></div>
        <FormField id="rejected-note" label="申请说明"><textarea id="rejected-note" v-model="form.application_note" maxlength="500" /></FormField>
        <button class="primary-button" type="submit" :disabled="submitting || !options.roles.length">{{ submitting ? '重新提交中…' : '重新提交申请' }}</button>
      </form>
      <button class="secondary-action" type="button" @click="signOut">退出登录</button>
    </div>
  </AuthLayout>
</template>

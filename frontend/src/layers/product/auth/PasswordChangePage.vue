<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthLayout from './AuthLayout.vue'
import FormField from '../../common/ui/FormField.vue'
import { changePassword, getCurrentUser, logout } from '../../features/auth/public'
import { createSessionStore } from '../../common/session/session.store'
import { ApiError } from '../../common/api/errors'

const router = useRouter()
const route = useRoute()
const session = createSessionStore()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const submitting = ref(false)
const showCurrent = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)
const firstLogin = computed(() => route.meta.mode === 'first-login')

async function submit() {
  if (newPassword.value.length < 8 || !/[A-Za-z]/.test(newPassword.value) || !/\d/.test(newPassword.value)) { error.value = '新密码至少 8 位且包含字母和数字'; return }
  if (newPassword.value !== confirmPassword.value) { error.value = '两次输入的密码不一致'; return }
  submitting.value = true; error.value = ''
  try {
    if (!currentPassword.value) { error.value = firstLogin.value ? '请输入当前临时密码' : '请输入当前密码'; return }
    await changePassword(currentPassword.value, newPassword.value, confirmPassword.value)
    const current = await getCurrentUser(); session.setUser(current.user); currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = ''
    await router.push(current.next_path)
  } catch (reason) {
      // 后端弱密码校验（BUG-M4-08）：WEAK_PASSWORD 消息直接映射到新密码提示
      if (reason instanceof ApiError && reason.code === 'WEAK_PASSWORD') error.value = `新密码不符合安全要求：${reason.message}`
      else error.value = reason instanceof ApiError ? reason.message : '网络异常，请稍后重试'
    }
  finally { submitting.value = false }
}
async function switchAccount() {
  try { await logout() } catch { /* the local session is still cleared */ }
  session.clear()
  await router.replace('/auth/login')
}
</script>

<template>
  <AuthLayout>
    <h2>{{ firstLogin ? '首次设置密码' : '修改密码' }}</h2>
    <p class="auth-subtitle">{{ firstLogin ? '为了保护账号安全，请先完成密码更新。' : '修改成功后，其他设备上的旧会话会失效。' }}</p>
    <div class="security-strip" aria-label="密码设置进度"><span class="security-step done" /><span class="security-step current" /><span class="security-step" /></div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <form @submit.prevent="submit">
      <FormField id="current-password" :label="firstLogin ? '当前临时密码' : '当前密码'"><div class="password-control"><input id="current-password" v-model="currentPassword" :type="showCurrent ? 'text' : 'password'" autocomplete="current-password" /><button type="button" class="password-toggle" @click="showCurrent = !showCurrent">{{ showCurrent ? '隐藏' : '显示' }}</button></div></FormField>
      <FormField id="new-password" label="新密码" hint="至少 8 位，并包含字母和数字"><div class="password-control"><input id="new-password" v-model="newPassword" :type="showNew ? 'text' : 'password'" autocomplete="new-password" /><button type="button" class="password-toggle" @click="showNew = !showNew">{{ showNew ? '隐藏' : '显示' }}</button></div></FormField>
      <FormField id="confirm-password" label="确认新密码"><div class="password-control"><input id="confirm-password" v-model="confirmPassword" :type="showConfirm ? 'text' : 'password'" autocomplete="new-password" /><button type="button" class="password-toggle" @click="showConfirm = !showConfirm">{{ showConfirm ? '隐藏' : '显示' }}</button></div></FormField>
      <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '保存中…' : '保存新密码' }}</button>
      <button class="secondary-action" type="button" :disabled="submitting" @click="switchAccount">退出并切换账号</button>
    </form>
  </AuthLayout>
</template>

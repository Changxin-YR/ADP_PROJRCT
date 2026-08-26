<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthLayout from './AuthLayout.vue'
import FormField from '../../common/ui/FormField.vue'
import { login } from '../../features/auth/public'
import { createSessionStore } from '../../common/session/session.store'
import { validateLogin, type FieldErrors } from '../../common/validation/auth.validation'
import { ApiError } from '../../common/api/errors'

const router = useRouter()
const route = useRoute()
const session = createSessionStore()
const identifier = ref('')
const password = ref('')
const showPassword = ref(false)
const errors = ref<FieldErrors>({})
const serverError = ref('')
const submitting = ref(false)
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

async function submit() {
  errors.value = validateLogin(identifier.value, password.value)
  serverError.value = ''
  if (Object.keys(errors.value).length) return
  submitting.value = true
  try {
    const result = await login(identifier.value, password.value)
    session.setUser(result.user)
    password.value = ''
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : result.next_path
    await router.push(redirect)
  } catch (error) {
    serverError.value = error instanceof ApiError ? error.message : '网络异常，请稍后重试'
  } finally { submitting.value = false }
}
</script>

<template>
  <AuthLayout active-tab="login" @tab="(tab) => tab === 'register' && router.push('/auth/register')">
    <h2>欢迎回来</h2>
    <p class="auth-subtitle">登录后继续处理你的养殖日常</p>
    <p v-if="demoMode" class="page-notice">演示环境：请使用本地开发种子账号。</p>
    <p v-if="serverError" class="field-error" role="alert">{{ serverError }}</p>
    <form @submit.prevent="submit">
      <FormField id="identifier" label="手机号或账号" :error="errors.identifier">
        <input id="identifier" v-model="identifier" autocomplete="username" inputmode="tel" />
      </FormField>
      <FormField id="password" label="密码" :error="errors.password">
        <div class="password-control">
          <input id="password" v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" />
          <button type="button" class="password-toggle" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示密码' }}</button>
        </div>
      </FormField>
      <button class="primary-button" type="submit" :disabled="submitting" :aria-busy="submitting">{{ submitting ? '登录中…' : '登录' }}</button>
    </form>
    <div class="divider">或</div>
    <div class="auth-links">
      <RouterLink to="/auth/register">申请加入</RouterLink>
      <button class="secondary-link" type="button" @click="serverError = '请联系系统管理员处理账号问题'">联系管理员</button>
    </div>
    <div class="card-note"><strong>提示</strong><span>账号审核通过后，将开放对应的业务数据与工作台。</span></div>
  </AuthLayout>
</template>

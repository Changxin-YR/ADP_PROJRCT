<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthLayout from './AuthLayout.vue'
import FormField from '../../common/ui/FormField.vue'
import { fetchRegistrationOptions, register, type RegistrationOptions } from '../../features/registration/registration.service'
import { createSessionStore } from '../../common/session/session.store'
import { validateRegistration, type FieldErrors } from '../../common/validation/auth.validation'
import { ApiError } from '../../common/api/errors'

const router = useRouter()
const session = createSessionStore()
const form = reactive({
  phone: '',
  name: '',
  password: '',
  confirm_password: '',
  desired_role_id: '' as number | '',
  area_id: '' as number | '',
  desired_scope_type: 'area' as 'farm' | 'area' | 'personal',
  application_note: '',
})
const errors = ref<FieldErrors>({})
const serverError = ref('')
const submitting = ref(false)
const showPassword = ref(false)
const optionsLoaded = ref(false)
const optionsError = ref('')

const options = ref<RegistrationOptions>({ roles: [], areas: [], data_scopes: [] })
onMounted(async () => {
  try {
    options.value = await fetchRegistrationOptions()
  } catch (reason) {
    optionsError.value = reason instanceof ApiError ? reason.message : '注册配置加载失败，请稍后重试'
  }
  optionsLoaded.value = true
})

const roles = computed(() => options.value.roles)
const areas = computed(() => options.value.areas)
const scopeTypeOptions = [
  { value: 'farm' as const, label: '全场数据（所有基地）' },
  { value: 'area' as const, label: '区域数据（指定基地）' },
  { value: 'personal' as const, label: '仅本人数据' },
]
const selectedRole = computed(() => roles.value.find((role) => role.id === Number(form.desired_role_id)))

async function submit() {
  if (!optionsLoaded.value || optionsError.value) { serverError.value = optionsError.value || '注册配置仍在加载'; return }
  errors.value = validateRegistration(form)
  serverError.value = ''
  if (Object.keys(errors.value).length) return
  submitting.value = true
  try {
    const result = await register({
      ...form,
      desired_role_id: Number(form.desired_role_id),
      area_id: Number(form.area_id),
      desired_scope_type: form.desired_scope_type,
    })
    session.setUser({ ...result.user, phone: form.phone, roles: [], data_scopes: [], permissions: [] })
    form.password = ''
    form.confirm_password = ''
    await router.push({ path: '/auth/pending', query: { submitted: '1' } })
  } catch (error) {
    // 后端弱密码校验（BUG-M4-08）：WEAK_PASSWORD 映射到密码字段中文提示
    if (error instanceof ApiError && error.code === 'WEAK_PASSWORD') errors.value = { ...errors.value, password: error.message }
    else serverError.value = error instanceof ApiError ? error.message : '网络异常，请稍后重试'
  } finally { submitting.value = false }
}
</script>

<template>
  <AuthLayout active-tab="register" @tab="(tab) => tab === 'login' && router.push('/auth/login')">
    <h2>申请注册</h2>
    <p class="auth-subtitle">填写基础资料，提交后由管理员审核。</p>
    <p v-if="optionsError || serverError" class="field-error" role="alert">{{ optionsError || serverError }}</p>
    <form @submit.prevent="submit">
      <div class="auth-field-grid">
        <FormField id="register-phone" label="手机号" :error="errors.phone"><input id="register-phone" v-model="form.phone" inputmode="tel" autocomplete="tel" /></FormField>
        <FormField id="register-name" label="姓名" :error="errors.name"><input id="register-name" v-model="form.name" autocomplete="name" /></FormField>
        <FormField id="register-password" label="密码" hint="至少 8 位，并包含字母和数字" :error="errors.password"><div class="password-control"><input id="register-password" v-model="form.password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" /><button type="button" class="password-toggle" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示密码' }}</button></div></FormField>
        <FormField id="register-confirm" label="确认密码" :error="errors.confirm_password"><input id="register-confirm" v-model="form.confirm_password" type="password" autocomplete="new-password" /></FormField>
        <FormField id="register-role" label="申请岗位" hint="共 7 类岗位，与功能文档一致" :error="errors.desired_role_id"><select id="register-role" v-model="form.desired_role_id"><option value="" disabled>请选择申请岗位</option><option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option></select></FormField>
        <FormField id="register-scope" label="申请数据范围" hint="全场 / 区域 / 个人 三级" :error="errors.desired_scope_type"><select id="register-scope" v-model="form.desired_scope_type"><option v-for="scope in scopeTypeOptions" :key="scope.value" :value="scope.value">{{ scope.label }}</option></select></FormField>
        <FormField v-if="form.desired_scope_type === 'area'" id="register-area" label="所属区域/基地" :error="errors.area_id"><select id="register-area" v-model="form.area_id"><option value="" disabled>请选择所属区域/基地</option><option v-for="area in areas" :key="area.id" :value="area.id">{{ area.name }}</option></select></FormField>
      </div>
      <p v-if="selectedRole?.description" class="page-notice" style="margin:0 0 12px">岗位说明：{{ selectedRole.description }}</p>
      <FormField id="register-note" label="申请说明" hint="选填，最多 500 个字符" :error="errors.application_note"><textarea id="register-note" v-model="form.application_note" maxlength="500" /></FormField>
      <button class="primary-button" type="submit" :disabled="submitting || !optionsLoaded || Boolean(optionsError)" :aria-busy="submitting">{{ submitting ? '提交中…' : '提交注册申请' }}</button>
    </form>
    <p class="page-notice">提交后进入审核，审核通过后按所申请的数据范围开放业务数据。{{ optionsLoaded ? '' : '正在加载企业角色与数据范围…' }}</p>
    <div class="auth-links"><RouterLink to="/auth/login">返回登录</RouterLink></div>
  </AuthLayout>
</template>

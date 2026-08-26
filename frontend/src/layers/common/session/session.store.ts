import { computed, ref } from 'vue'
import type { ApiClient } from '../api/client'
import type { UserSummary } from '../api/models'
import { ApiError } from '../api/errors'

const pathByStatus: Record<UserSummary['status'], string> = {
  pending: '/auth/pending', rejected: '/auth/rejected', active: '/workbench', disabled: '/auth/login', must_change_password: '/auth/first-password', retired: '/auth/login',
}

const user = ref<UserSummary | null>(null)
const loading = ref(false)

export function createSessionStore() {
  const nextPath = computed(() => user.value ? pathByStatus[user.value.status] : '/auth/login')
  function setUser(value: UserSummary | null): void { user.value = value }
  async function load(client: ApiClient): Promise<UserSummary | null> {
    loading.value = true
    try {
      const data = await client.get<{ user: UserSummary }>('/api/v1/auth/me')
      user.value = data.user
      return data.user
    } catch (error) {
      if (error instanceof ApiError && ['UNAUTHENTICATED', 'SESSION_EXPIRED', 'SESSION_REPLACED'].includes(error.code)) user.value = null
      return null
    } finally { loading.value = false }
  }
  return { user, loading, nextPath, setUser, load, clear: () => setUser(null) }
}

import { ref } from 'vue'
import type { Ref } from 'vue'

export interface SubmitGuard {
  /** 是否正在提交；绑定到按钮 disabled / aria-busy */
  busy: Ref<boolean>
  /** 包裹异步提交任务：busy 期间重复调用直接忽略，防止双击/连点产生重复请求 */
  run: <T>(task: () => Promise<T>) => Promise<T | undefined>
}

/**
 * 保存/确认按钮防重复提交守卫（BUG-M2-05 / BUG-M4-09）。
 * 所有 save/confirm/submit 类的写操作都应通过 run() 包裹。
 */
export function useSubmitGuard(): SubmitGuard {
  const busy = ref(false)
  async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
    if (busy.value) return undefined
    busy.value = true
    try {
      return await task()
    } finally {
      busy.value = false
    }
  }
  return { busy, run }
}

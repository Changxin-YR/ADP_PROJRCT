const PREFIX = 'adp:offline-draft:'
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000

interface DraftEnvelope<T> { version: 1; saved_at: string; payload: T }

function storage(): Storage | null {
  try { return typeof window === 'undefined' ? null : window.localStorage } catch { return null }
}

const keyOf = (scope: string) => `${PREFIX}${scope}`

export function saveOfflineDraft<T>(scope: string, payload: T): void {
  const target = storage()
  if (!target) return
  try { target.setItem(keyOf(scope), JSON.stringify({ version: 1, saved_at: new Date().toISOString(), payload })) } catch { /* storage may be unavailable or full */ }
}

export function loadOfflineDraft<T>(scope: string): { payload: T; savedAt: string } | null {
  const target = storage()
  if (!target) return null
  try {
    const raw = target.getItem(keyOf(scope))
    if (!raw) return null
    const envelope = JSON.parse(raw) as Partial<DraftEnvelope<T>>
    const timestamp = Date.parse(String(envelope.saved_at ?? ''))
    if (envelope.version !== 1 || !envelope.payload || typeof envelope.payload !== 'object' || !Number.isFinite(timestamp) || Date.now() - timestamp > MAX_AGE_MS) {
      target.removeItem(keyOf(scope)); return null
    }
    return { payload: envelope.payload as T, savedAt: String(envelope.saved_at) }
  } catch { return null }
}

export function clearOfflineDraft(scope: string): void {
  try { storage()?.removeItem(keyOf(scope)) } catch { /* ignore unavailable storage */ }
}

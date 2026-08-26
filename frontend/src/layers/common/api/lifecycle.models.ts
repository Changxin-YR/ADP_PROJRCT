export type RecordAction = 'view' | 'edit' | 'delete' | 'submit' | 'approve' | 'verify' | 'confirm' | 'correct' | 'reverse' | 'depreciate' | 'dispatch' | 'receive' | 'cancel' | 'handle'

export interface LifecycleRecord {
  status: string
  version: number
  allowed_actions: RecordAction[]
}

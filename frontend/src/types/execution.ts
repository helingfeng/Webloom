export interface Execution {
  id: number
  target_type: string // 包含历史执行类型，新任务仅支持脚本
  target_id: number
  mode: string
  inputs: Record<string, any>
  status: 'pending' | 'running' | 'success' | 'failed'
  logs: string
  outputs: Record<string, any>
  started_at: string
  finished_at: string | null
}

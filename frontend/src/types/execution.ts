export interface Execution {
  id: number
  target_type: 'script' | 'flow'
  target_id: number
  mode: string
  inputs: Record<string, any>
  status: 'pending' | 'running' | 'success' | 'failed'
  logs: string
  outputs: Record<string, any>
  started_at: string
  finished_at: string | null
}

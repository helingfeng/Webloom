export interface CollectorDraft {
  name: string; slug: string; script_id: number; description: string; app_ids: number[]; enabled: boolean
}
export interface Collector extends CollectorDraft { id: number; created_at: string; updated_at: string }
export interface InputProperty { type: string; description: string; default?: unknown; writeOnly?: boolean }
export interface CollectorContract {
  id: number; name: string; slug: string; description: string; path: string
  input_schema: { properties: Record<string, InputProperty>; required: string[] }
  outputs: { name: string; description: string }[]
  example: { inputs: Record<string, unknown>; wait_seconds: number }; auth: string
}
export interface CollectorTask {
  task_id: number; execution_id: number; collector_id: number; collector_name: string; app_id: number
  status: 'pending' | 'running' | 'success' | 'failed'; finished: boolean; error: string | null
  created_at: string; finished_at: string | null; result_url: string; data_url: string
  outputs?: Record<string, unknown>; logs?: string; inputs?: Record<string, unknown>
}
export interface CollectorData {
  status: string; finished: boolean; error: string | null; fields: string[]; field: string | null
  items: Record<string, unknown>[]; columns: string[]; total: number; skip: number; limit: number
}
export interface Page<T> { items: T[]; total: number }

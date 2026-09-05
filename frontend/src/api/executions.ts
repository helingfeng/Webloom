import client from './client'
import type { Execution } from '@/types/execution'

export interface ExecutionPage {
  items: Execution[]
  total: number
}

export function listExecutions(skip = 0, limit = 20, workspaceId?: number, scriptId?: number) {
  return client.get<ExecutionPage>('/executions', {
    params: {
      skip,
      limit,
      ...(workspaceId !== undefined ? { workspace_id: workspaceId } : {}),
      ...(scriptId !== undefined ? { script_id: scriptId } : {}),
    },
  })
}

export function getExecution(id: number) {
  return client.get<Execution>(`/executions/${id}`)
}

export function deleteExecution(id: number) {
  return client.delete(`/executions/${id}`)
}

export function clearExecutions() {
  return client.delete('/executions')
}

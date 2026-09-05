import client from './client'
import type { Flow, FlowCreate, FlowRunRequest } from '@/types/flow'

export function listFlows(workspaceId?: number) {
  return client.get<Flow[]>('/flows', {
    params: workspaceId !== undefined ? { workspace_id: workspaceId } : {},
  })
}

export function getFlow(id: number) {
  return client.get<Flow>(`/flows/${id}`)
}

export function createFlow(data: FlowCreate) {
  return client.post<Flow>('/flows', data)
}

export function updateFlow(id: number, data: FlowCreate) {
  return client.put<Flow>(`/flows/${id}`, data)
}

export function deleteFlow(id: number) {
  return client.delete(`/flows/${id}`)
}

export function runFlow(id: number, data: FlowRunRequest) {
  return client.post<{ execution_id: number; status: string; outputs: Record<string, any>; logs: string }>(`/flows/${id}/run`, data)
}

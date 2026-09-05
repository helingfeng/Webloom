import client from './client'
import type { Script, ScriptCreate, ScriptRunRequest, ScriptRunResponse } from '@/types/script'

export function listScripts(workspaceId?: number) {
  return client.get<Script[]>('/scripts', {
    params: workspaceId !== undefined ? { workspace_id: workspaceId } : {},
  })
}

export function getScript(id: number) {
  return client.get<Script>(`/scripts/${id}`)
}

export function createScript(data: ScriptCreate) {
  return client.post<Script>('/scripts', data)
}

export function updateScript(id: number, data: ScriptCreate) {
  return client.put<Script>(`/scripts/${id}`, data)
}

export function deleteScript(id: number) {
  return client.delete(`/scripts/${id}`)
}

export function batchDeleteScripts(ids: number[]) {
  return client.post<{ deleted: number }>('/scripts/batch-delete', { ids })
}

export function runScript(id: number, data: ScriptRunRequest) {
  return client.post<ScriptRunResponse>(`/scripts/${id}/run`, data)
}

import client from './client'
import type { Workspace, WorkspaceCreate, WorkspaceUpdate } from '@/types/workspace'

export function listWorkspaces() {
  return client.get<Workspace[]>('/workspaces')
}

export function createWorkspace(data: WorkspaceCreate) {
  return client.post<Workspace>('/workspaces', data)
}

export function updateWorkspace(id: number, data: WorkspaceUpdate) {
  return client.put<Workspace>(`/workspaces/${id}`, data)
}

export function deleteWorkspace(id: number) {
  return client.delete(`/workspaces/${id}`)
}

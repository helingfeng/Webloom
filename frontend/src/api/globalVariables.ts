import client from './client'
import type { GlobalVariable, GlobalVariableCreate } from '@/types/globalVariable'

export function listGlobalVariables() {
  return client.get<GlobalVariable[]>('/global-variables')
}

export function createGlobalVariable(data: GlobalVariableCreate) {
  return client.post<GlobalVariable>('/global-variables', data)
}

export function updateGlobalVariable(id: number, data: GlobalVariableCreate) {
  return client.put<GlobalVariable>(`/global-variables/${id}`, data)
}

export function deleteGlobalVariable(id: number) {
  return client.delete(`/global-variables/${id}`)
}

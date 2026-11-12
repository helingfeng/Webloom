import client from './client'
import type { GlobalVariable, GlobalVariableCreate, GlobalVariableDetail, GlobalVariableUpdate } from '@/types/globalVariable'

export function listGlobalVariables() {
  return client.get<GlobalVariable[]>('/global-variables')
}

export function createGlobalVariable(data: GlobalVariableCreate) {
  return client.post<GlobalVariable>('/global-variables', data)
}

export function updateGlobalVariable(id: number, data: GlobalVariableUpdate) {
  return client.put<GlobalVariable>(`/global-variables/${id}`, data)
}

export function deleteGlobalVariable(id: number) {
  return client.delete(`/global-variables/${id}`)
}

export const getGlobalVariable = (id: number) => client.get<GlobalVariableDetail>(`/global-variables/${id}`)

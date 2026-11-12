import client from './client'
import type { Collector, CollectorDraft, CollectorContract, CollectorTask, CollectorData, Page } from '@/types/collector'
export const listCollectors = (skip = 0) => client.get<Page<Collector>>('/collectors', { params: { skip, limit: 20 } })
export const saveCollector = (data: CollectorDraft, id?: number) => id ? client.put<Collector>(`/collectors/${id}`, data) : client.post<Collector>('/collectors', data)
export const removeCollector = (id: number) => client.delete(`/collectors/${id}`)
export const getContract = (id: number) => client.get<CollectorContract>(`/collectors/${id}/contract`)
export const debugCollector = (id: number, app_id: number, inputs: Record<string, unknown>) => client.post<CollectorTask>(`/collectors/${id}/debug`, { app_id, inputs, wait_seconds: 0 })
export const listCollectorTasks = (params: Record<string, unknown>) => client.get<Page<CollectorTask>>('/collector-tasks', { params })
export const getCollectorTask = (id: number) => client.get<CollectorTask>(`/collector-tasks/${id}`)
export const getCollectorData = (id: number, params: Record<string, unknown>) => client.get<CollectorData>(`/collector-tasks/${id}/data`, { params })
export function apiError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((e) => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('；')
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

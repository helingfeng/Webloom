import client from './client'
import type { DataView, DataViewCreate, DataViewUpdate } from '@/types/dataView'
import type { QueryResult } from '@/types/datasource'

export function listDataViews() {
  return client.get<DataView[]>('/data-views')
}

export function createDataView(data: DataViewCreate) {
  return client.post<DataView>('/data-views', data)
}

export function updateDataView(id: number, data: DataViewUpdate) {
  return client.put<DataView>(`/data-views/${id}`, data)
}

export function deleteDataView(id: number) {
  return client.delete(`/data-views/${id}`)
}

// 后端 SQL 超时 30s + 网络开销，需覆盖 client 默认 30s 超时
export function runDataView(id: number) {
  return client.post<QueryResult>(`/data-views/${id}/run`, null, {
    timeout: 60000,
  })
}

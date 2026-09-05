import client from './client'
import type {
  Datasource,
  DatasourceCreate,
  DatasourceUpdate,
  DatasourceTestRequest,
  DatasourceTestResult,
  DatasourceTable,
  DatasourceColumn,
  QueryRequest,
  QueryResult,
  QueryHistoryDetail,
  QueryHistoryPage,
} from '@/types/datasource'

export function listDatasources() {
  return client.get<Datasource[]>('/datasources')
}

export function createDatasource(data: DatasourceCreate) {
  return client.post<Datasource>('/datasources', data)
}

export function updateDatasource(id: number, data: DatasourceUpdate) {
  return client.put<Datasource>(`/datasources/${id}`, data)
}

export function deleteDatasource(id: number) {
  return client.delete(`/datasources/${id}`)
}

export function testDatasource(data: DatasourceTestRequest) {
  return client.post<DatasourceTestResult>('/datasources/test', data)
}

export function testDatasourceById(id: number) {
  return client.post<DatasourceTestResult>(`/datasources/${id}/test`)
}

export function listDatabases(id: number) {
  return client.get<string[]>(`/datasources/${id}/databases`)
}

export function listTables(id: number, database?: string) {
  return client.get<DatasourceTable[]>(`/datasources/${id}/tables`, {
    params: database ? { database } : {},
  })
}

export function getTableSchema(id: number, tableName: string, database?: string) {
  return client.get<DatasourceColumn[]>(
    `/datasources/${id}/tables/${encodeURIComponent(tableName)}/schema`,
    { params: database ? { database } : {} }
  )
}

// 后端 SQL 超时 30s + 网络开销，需覆盖 client 默认 30s 超时
export function runQuery(id: number, data: QueryRequest) {
  return client.post<QueryResult>(`/datasources/${id}/query`, data, {
    timeout: 60000,
  })
}

export function listQueryHistory(id: number, skip = 0, limit = 20) {
  return client.get<QueryHistoryPage>(`/datasources/${id}/query-history`, {
    params: { skip, limit },
  })
}

export function getQueryHistoryDetail(id: number, historyId: number) {
  return client.get<QueryHistoryDetail>(
    `/datasources/${id}/query-history/${historyId}`
  )
}

export function deleteQueryHistory(id: number, historyId: number) {
  return client.delete(`/datasources/${id}/query-history/${historyId}`)
}

export function clearQueryHistory(id: number) {
  return client.delete(`/datasources/${id}/query-history`)
}

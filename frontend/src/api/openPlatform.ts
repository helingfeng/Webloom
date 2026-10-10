import client from './client'
import type {
  OpenApiLogPage,
  OpenApiRoute,
  OpenApiRouteCreate,
  OpenApiRoutePage,
  OpenApiRouteUpdate,
  OpenApp,
  OpenAppCreate,
  OpenAppDetail,
  OpenAppPage,
  OpenAppSecret,
  OpenAppUpdate,
} from '@/types/openPlatform'

// ---------- 开放应用 ----------

export function listOpenApps(skip = 0, limit = 100) {
  return client.get<OpenAppPage>('/open-apps', { params: { skip, limit } })
}

export function createOpenApp(data: OpenAppCreate) {
  return client.post<OpenAppDetail>('/open-apps', data)
}

export function getOpenApp(id: number) {
  return client.get<OpenAppDetail>(`/open-apps/${id}`)
}

export function updateOpenApp(id: number, data: OpenAppUpdate) {
  return client.put<OpenApp>(`/open-apps/${id}`, data)
}

export function regenerateOpenAppSecret(id: number) {
  return client.post<OpenAppSecret>(`/open-apps/${id}/regenerate-secret`)
}

export function deleteOpenApp(id: number) {
  return client.delete(`/open-apps/${id}`)
}

// ---------- 开放接口（代理规则）----------

export function listOpenApis(skip = 0, limit = 100) {
  return client.get<OpenApiRoutePage>('/open-apis', { params: { skip, limit } })
}

export function createOpenApi(data: OpenApiRouteCreate) {
  return client.post<OpenApiRoute>('/open-apis', data)
}

export function updateOpenApi(id: number, data: OpenApiRouteUpdate) {
  return client.put<OpenApiRoute>(`/open-apis/${id}`, data)
}

export function deleteOpenApi(id: number) {
  return client.delete(`/open-apis/${id}`)
}

// ---------- 调用日志 ----------

export function listOpenLogs(
  skip = 0,
  limit = 20,
  params: { app_id?: number; success?: boolean } = {}
) {
  return client.get<OpenApiLogPage>('/open-logs', {
    params: { skip, limit, ...params },
  })
}

export function clearOpenLogs() {
  return client.delete('/open-logs')
}

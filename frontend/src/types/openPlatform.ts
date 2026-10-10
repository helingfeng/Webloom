export interface OpenApp {
  id: number
  name: string
  app_key: string
  enabled: boolean
  description: string
  created_at: string
  updated_at: string
}

export interface OpenAppDetail extends OpenApp {
  app_secret: string
}

export interface OpenAppSecret {
  app_key: string
  app_secret: string
}

export interface OpenAppCreate {
  name: string
  description: string
  enabled: boolean
}

export interface OpenAppUpdate {
  name?: string
  description?: string
  enabled?: boolean
}

export interface OpenAppPage {
  items: OpenApp[]
  total: number
}

export type OpenApiMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

export interface OpenApiRoute {
  id: number
  name: string
  method: OpenApiMethod
  path: string
  target_path: string
  enabled: boolean
  description: string
  created_at: string
  updated_at: string
}

export interface OpenApiRouteCreate {
  name: string
  method: OpenApiMethod
  path: string
  target_path: string
  enabled: boolean
  description: string
}

export interface OpenApiRouteUpdate {
  name?: string
  method?: OpenApiMethod
  path?: string
  target_path?: string
  enabled?: boolean
  description?: string
}

export interface OpenApiRoutePage {
  items: OpenApiRoute[]
  total: number
}

export interface OpenApiLog {
  id: number
  app_id: number | null
  app_key: string
  path: string
  method: string
  status_code: number
  success: boolean
  execution_id: number | null
  request_ip: string
  detail: string
  created_at: string
}

export interface OpenApiLogPage {
  items: OpenApiLog[]
  total: number
}

export interface OpenCollectTask {
  execution_id: number
  script_id: number
  status: string
  finished: boolean
  started_at: string | null
  finished_at: string | null
}

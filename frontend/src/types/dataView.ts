export interface DataView {
  id: number
  name: string
  slug: string
  datasource_id: number
  database: string
  sql: string
  description: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface DataViewCreate {
  name: string
  slug: string
  datasource_id: number
  database?: string
  sql: string
  description?: string
  enabled?: boolean
}

export interface DataViewUpdate {
  name?: string
  slug?: string
  datasource_id?: number
  database?: string
  sql?: string
  description?: string
  enabled?: boolean
}

// 预览结果复用 @/types/datasource 的 QueryResult

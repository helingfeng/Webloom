export interface Datasource {
  id: number
  name: string
  host: string
  port: number
  user: string
  database: string
  description: string
  created_at: string
  updated_at: string
}

export interface DatasourceCreate {
  name: string
  host: string
  port?: number
  user: string
  password: string
  database?: string
  description?: string
}

export interface DatasourceUpdate {
  name?: string
  host?: string
  port?: number
  user?: string
  password?: string
  database?: string
  description?: string
}

export interface DatasourceTestRequest {
  host: string
  port?: number
  user: string
  password: string
  database?: string
}

export interface DatasourceTestResult {
  success: boolean
  elapsed_ms: number
  server_version: string | null
  error: string | null
}

export interface DatasourceTable {
  name: string
  table_type: string
  table_rows: number | null
  comment: string
}

export interface DatasourceColumn {
  name: string
  column_type: string
  nullable: boolean
  column_key: string
  default: string | null
  extra: string
  comment: string
}

export interface QueryRequest {
  sql: string
  database?: string
}

export interface QueryResult {
  success: boolean
  statement_type: 'query' | 'execute'
  columns: string[]
  rows: any[][]
  row_count: number
  affected_rows: number
  truncated: boolean
  elapsed_ms: number
  error: string | null
}

export interface QueryHistoryItem {
  id: number
  database: string
  sql: string
  success: boolean
  statement_type: string
  row_count: number
  affected_rows: number
  elapsed_ms: number
  error: string | null
  created_at: string
}

export interface QueryHistoryDetail extends QueryHistoryItem {
  columns: string[]
  rows: any[][]
  truncated: boolean
}

export interface QueryHistoryPage {
  items: QueryHistoryItem[]
  total: number
}

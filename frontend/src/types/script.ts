export interface VariableDefinition {
  name: string
  type: 'string' | 'number' | 'boolean' | 'secret' | 'header' | 'cookie' | 'localStorage'
  description?: string
  default?: any
  required?: boolean
}

export interface OutputDefinition {
  name: string
  description?: string
}

export interface Script {
  id: number
  workspace_id: number
  name: string
  description: string
  start_url: string
  inputs: VariableDefinition[]
  outputs: OutputDefinition[]
  code: string
  inherit_global: boolean
  run_mode: 'manual' | 'mock'
  headless: boolean
  created_at: string
  updated_at: string
}

export interface ScriptCreate {
  workspace_id: number
  name: string
  description?: string
  start_url?: string
  inputs?: VariableDefinition[]
  outputs?: OutputDefinition[]
  code?: string
  inherit_global?: boolean
  run_mode?: 'manual' | 'mock'
  headless?: boolean
}

export interface ScriptRunRequest {
  mode: 'manual' | 'mock'
  inputs: Record<string, any>
  headless?: boolean
}

export interface ScriptRunResponse {
  execution_id: number
  status: string
  outputs: Record<string, any>
  logs: string
}

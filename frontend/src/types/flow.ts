export interface FlowNode {
  id: string
  type: 'start' | 'end' | 'script'
  position: { x: number; y: number }
  data: {
    script_id?: number
    input_mapping?: Record<string, string>
    label?: string
  }
}

export interface FlowEdge {
  id: string
  source: string
  target: string
}

export interface Flow {
  id: number
  workspace_id: number
  name: string
  description: string
  run_mode: 'manual' | 'mock'
  global_inputs: Record<string, any>
  nodes: FlowNode[]
  edges: FlowEdge[]
  created_at: string
  updated_at: string
}

export interface FlowCreate {
  workspace_id: number
  name: string
  description?: string
  run_mode?: 'manual' | 'mock'
  global_inputs?: Record<string, any>
  nodes?: FlowNode[]
  edges?: FlowEdge[]
}

export interface FlowRunRequest {
  mode: 'manual' | 'mock'
  global_inputs: Record<string, any>
}

export interface GlobalVariable {
  id: number
  name: string
  has_value: boolean
  type: 'header' | 'variable' | 'localStorage' | 'cookie'
  domain: string
  enabled: boolean
  description: string
  created_at: string
  updated_at: string
}

export interface GlobalVariableCreate {
  name: string
  value?: string
  type?: 'header' | 'variable' | 'localStorage' | 'cookie'
  domain?: string
  enabled?: boolean
  description?: string
}

export interface GlobalVariableDetail extends GlobalVariable { value: string }
export type GlobalVariableUpdate = Partial<GlobalVariableCreate>

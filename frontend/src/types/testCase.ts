export type CaseStatus = 'pending' | 'in_progress' | 'completed' | 'blocked'

export const CASE_STATUS_OPTIONS: { value: CaseStatus; label: string; tagType: 'info' | 'primary' | 'success' | 'danger' }[] = [
  { value: 'pending', label: '未开始', tagType: 'info' },
  { value: 'in_progress', label: '进行中', tagType: 'primary' },
  { value: 'completed', label: '已完成', tagType: 'success' },
  { value: 'blocked', label: '阻塞', tagType: 'danger' },
]

export function statusLabel(status: CaseStatus): string {
  return CASE_STATUS_OPTIONS.find((o) => o.value === status)?.label ?? status
}

export interface Requirement {
  id: number
  workspace_id: number
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface RequirementCreate {
  workspace_id: number
  name: string
  description?: string
}

export interface TestModule {
  id: number
  requirement_id: number
  name: string
  created_at: string
  updated_at: string
}

export interface TestModuleCreate {
  requirement_id: number
  name: string
}

export interface TestCase {
  id: number
  requirement_id: number
  module_id: number | null
  title: string
  precondition: string
  steps: string[]
  expected_result: string
  status: CaseStatus
  created_at: string
  updated_at: string
}

export interface TestCaseCreate {
  requirement_id: number
  module_id?: number | null
  title: string
  precondition?: string
  steps?: string[]
  expected_result?: string
  status?: CaseStatus
}

export interface BatchStatusPayload {
  ids: number[]
  status: CaseStatus
}

export interface BatchStatusResult {
  updated: number
}

export interface BatchDeleteResult {
  deleted: number
}

export interface ImportCaseIn {
  title: string
  precondition?: string
  steps: string[]
  expected_result?: string
}

export interface ImportModuleIn {
  name: string
  cases: ImportCaseIn[]
}

export interface TestCaseImportPayload {
  workspace_id: number
  requirement_id?: number | null
  requirement_name?: string
  modules: ImportModuleIn[]
  cases: ImportCaseIn[]
}

export interface TestCaseImportResult {
  requirement_id: number
  requirement_name: string
  module_count: number
  case_count: number
}

export interface MindmapNode {
  content: string
  children: MindmapNode[]
}

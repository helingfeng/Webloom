import client from './client'
import type {
  BatchDeleteResult,
  BatchStatusPayload,
  BatchStatusResult,
  CaseStatus,
  Requirement,
  RequirementCreate,
  TestCase,
  TestCaseCreate,
  TestCaseImportPayload,
  TestCaseImportResult,
  TestModule,
  TestModuleCreate,
} from '@/types/testCase'

export function listRequirements(workspaceId?: number) {
  return client.get<Requirement[]>('/requirements', {
    params: workspaceId !== undefined ? { workspace_id: workspaceId } : {},
  })
}

export function createRequirement(data: RequirementCreate) {
  return client.post<Requirement>('/requirements', data)
}

export function updateRequirement(id: number, data: RequirementCreate) {
  return client.put<Requirement>(`/requirements/${id}`, data)
}

export function deleteRequirement(id: number) {
  return client.delete(`/requirements/${id}`)
}

export function listModules(requirementId?: number) {
  return client.get<TestModule[]>('/modules', {
    params: requirementId !== undefined ? { requirement_id: requirementId } : {},
  })
}

export function createModule(data: TestModuleCreate) {
  return client.post<TestModule>('/modules', data)
}

export function updateModule(id: number, data: TestModuleCreate) {
  return client.put<TestModule>(`/modules/${id}`, data)
}

export function deleteModule(id: number) {
  return client.delete(`/modules/${id}`)
}

export function listTestCases(params: {
  workspace_id?: number
  requirement_id?: number
  module_id?: number
  status?: CaseStatus
}) {
  return client.get<TestCase[]>('/test-cases', { params })
}

export function createTestCase(data: TestCaseCreate) {
  return client.post<TestCase>('/test-cases', data)
}

export function updateTestCase(id: number, data: TestCaseCreate) {
  return client.put<TestCase>(`/test-cases/${id}`, data)
}

export function deleteTestCase(id: number) {
  return client.delete(`/test-cases/${id}`)
}

export function updateCaseStatus(id: number, status: CaseStatus) {
  return client.patch<TestCase>(`/test-cases/${id}/status`, { status })
}

export function batchUpdateStatus(payload: BatchStatusPayload) {
  return client.post<BatchStatusResult>('/test-cases/batch-status', payload)
}

export function batchDeleteCases(ids: number[]) {
  return client.post<BatchDeleteResult>('/test-cases/batch-delete', { ids })
}

export function importTestCases(payload: TestCaseImportPayload) {
  return client.post<TestCaseImportResult>('/test-cases/import', payload)
}

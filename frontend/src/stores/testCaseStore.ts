import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/testCases'
import type {
  CaseStatus,
  Requirement,
  RequirementCreate,
  TestCase,
  TestCaseCreate,
  TestCaseImportPayload,
  TestModule,
  TestModuleCreate,
} from '@/types/testCase'

export const useTestCaseStore = defineStore('testCases', () => {
  const requirements = ref<Requirement[]>([])
  const modules = ref<TestModule[]>([])
  const cases = ref<TestCase[]>([])
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const [reqRes, modRes, caseRes] = await Promise.all([
        api.listRequirements(),
        api.listModules(),
        api.listTestCases({}),
      ])
      requirements.value = reqRes.data
      modules.value = modRes.data
      cases.value = caseRes.data
    } finally {
      loading.value = false
    }
  }

  async function createRequirement(data: RequirementCreate) {
    await api.createRequirement(data)
    await fetchAll()
  }

  async function updateRequirement(id: number, data: RequirementCreate) {
    await api.updateRequirement(id, data)
    await fetchAll()
  }

  async function deleteRequirement(id: number) {
    await api.deleteRequirement(id)
    await fetchAll()
  }

  async function createModule(data: TestModuleCreate) {
    await api.createModule(data)
    await fetchAll()
  }

  async function updateModule(id: number, data: TestModuleCreate) {
    await api.updateModule(id, data)
    await fetchAll()
  }

  async function deleteModule(id: number) {
    await api.deleteModule(id)
    await fetchAll()
  }

  async function createCase(data: TestCaseCreate) {
    await api.createTestCase(data)
    await fetchAll()
  }

  async function updateCase(id: number, data: TestCaseCreate) {
    await api.updateTestCase(id, data)
    await fetchAll()
  }

  async function deleteCase(id: number) {
    await api.deleteTestCase(id)
    await fetchAll()
  }

  async function updateCaseStatus(id: number, status: CaseStatus) {
    const res = await api.updateCaseStatus(id, status)
    const index = cases.value.findIndex((c) => c.id === id)
    if (index !== -1) cases.value[index] = res.data
    return res.data
  }

  async function batchUpdateStatus(ids: number[], status: CaseStatus) {
    await api.batchUpdateStatus({ ids, status })
    await fetchAll()
  }

  async function batchDeleteCases(ids: number[]) {
    await api.batchDeleteCases(ids)
    await fetchAll()
  }

  async function importCases(payload: TestCaseImportPayload) {
    const res = await api.importTestCases(payload)
    await fetchAll()
    return res.data
  }

  return {
    requirements,
    modules,
    cases,
    loading,
    fetchAll,
    createRequirement,
    updateRequirement,
    deleteRequirement,
    createModule,
    updateModule,
    deleteModule,
    createCase,
    updateCase,
    deleteCase,
    updateCaseStatus,
    batchUpdateStatus,
    batchDeleteCases,
    importCases,
  }
})

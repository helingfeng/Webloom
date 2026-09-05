import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as executionsApi from '@/api/executions'
import type { Execution } from '@/types/execution'

const PAGE_SIZE = 20

export const useExecutionStore = defineStore('executions', () => {
  const executions = ref<Execution[]>([])
  const currentExecution = ref<Execution | null>(null)
  const loading = ref(false)
  const total = ref(0)
  const page = ref(1)

  async function fetchExecutions(targetPage = 1, workspaceId?: number) {
    loading.value = true
    try {
      const res = await executionsApi.listExecutions(
        (targetPage - 1) * PAGE_SIZE,
        PAGE_SIZE,
        workspaceId
      )
      executions.value = res.data.items
      total.value = res.data.total
      page.value = targetPage
    } finally {
      loading.value = false
    }
  }

  async function fetchExecution(id: number) {
    const res = await executionsApi.getExecution(id)
    currentExecution.value = res.data
    return res.data
  }

  async function deleteExecution(id: number) {
    await executionsApi.deleteExecution(id)
    await fetchExecutions(page.value)
  }

  async function clearExecutions() {
    await executionsApi.clearExecutions()
    await fetchExecutions(1)
  }

  return {
    executions,
    currentExecution,
    loading,
    total,
    page,
    pageSize: PAGE_SIZE,
    fetchExecutions,
    fetchExecution,
    deleteExecution,
    clearExecutions,
  }
})

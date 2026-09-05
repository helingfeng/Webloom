import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as flowsApi from '@/api/flows'
import type { Flow, FlowCreate, FlowRunRequest } from '@/types/flow'

export const useFlowStore = defineStore('flows', () => {
  const flows = ref<Flow[]>([])
  const currentFlow = ref<Flow | null>(null)
  const loading = ref(false)

  async function fetchFlows(workspaceId?: number) {
    loading.value = true
    try {
      const res = await flowsApi.listFlows(workspaceId)
      flows.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchFlow(id: number) {
    const res = await flowsApi.getFlow(id)
    currentFlow.value = res.data
    return res.data
  }

  async function createFlow(data: FlowCreate) {
    const res = await flowsApi.createFlow(data)
    flows.value.push(res.data)
    // 与 updateFlow 一致：写入 currentFlow，供路由切换到 /flows/:id 后
    // FlowDetailView 的 initialData 取到画布数据，否则编辑器会被空数据清空
    currentFlow.value = res.data
    return res.data
  }

  async function updateFlow(id: number, data: FlowCreate) {
    const res = await flowsApi.updateFlow(id, data)
    const index = flows.value.findIndex((f) => f.id === id)
    if (index !== -1) {
      flows.value[index] = res.data
    }
    currentFlow.value = res.data
    return res.data
  }

  async function deleteFlow(id: number) {
    await flowsApi.deleteFlow(id)
    flows.value = flows.value.filter((f) => f.id !== id)
  }

  async function runFlow(id: number, request: FlowRunRequest) {
    const res = await flowsApi.runFlow(id, request)
    return res.data
  }

  return {
    flows,
    currentFlow,
    loading,
    fetchFlows,
    fetchFlow,
    createFlow,
    updateFlow,
    deleteFlow,
    runFlow,
  }
})

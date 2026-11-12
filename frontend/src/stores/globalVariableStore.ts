import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as gvApi from '@/api/globalVariables'
import type { GlobalVariable, GlobalVariableCreate, GlobalVariableUpdate } from '@/types/globalVariable'

export const useGlobalVariableStore = defineStore('globalVariables', () => {
  const variables = ref<GlobalVariable[]>([])
  const loading = ref(false)

  async function fetchVariables() {
    loading.value = true
    try {
      const res = await gvApi.listGlobalVariables()
      variables.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function createVariable(data: GlobalVariableCreate) {
    const res = await gvApi.createGlobalVariable(data)
    await fetchVariables()
    return res.data
  }

  async function updateVariable(id: number, data: GlobalVariableUpdate) {
    const res = await gvApi.updateGlobalVariable(id, data)
    await fetchVariables()
    return res.data
  }

  async function deleteVariable(id: number) {
    await gvApi.deleteGlobalVariable(id)
    variables.value = variables.value.filter((v) => v.id !== id)
  }

  return {
    variables,
    loading,
    fetchVariables,
    createVariable,
    updateVariable,
    deleteVariable,
  }
})

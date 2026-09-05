import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as scriptsApi from '@/api/scripts'
import type { Script, ScriptCreate, ScriptRunRequest, ScriptRunResponse } from '@/types/script'

export const useScriptStore = defineStore('scripts', () => {
  const scripts = ref<Script[]>([])
  const currentScript = ref<Script | null>(null)
  const loading = ref(false)

  async function fetchScripts(workspaceId?: number) {
    loading.value = true
    try {
      const res = await scriptsApi.listScripts(workspaceId)
      scripts.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchScript(id: number) {
    const res = await scriptsApi.getScript(id)
    currentScript.value = res.data
    return res.data
  }

  async function createScript(data: ScriptCreate) {
    const res = await scriptsApi.createScript(data)
    scripts.value.push(res.data)
    currentScript.value = res.data
    return res.data
  }

  async function updateScript(id: number, data: ScriptCreate) {
    const res = await scriptsApi.updateScript(id, data)
    const index = scripts.value.findIndex((s) => s.id === id)
    if (index !== -1) {
      scripts.value[index] = res.data
    }
    currentScript.value = res.data
    return res.data
  }

  async function deleteScript(id: number) {
    await scriptsApi.deleteScript(id)
    scripts.value = scripts.value.filter((s) => s.id !== id)
  }

  async function batchDeleteScripts(ids: number[]) {
    const res = await scriptsApi.batchDeleteScripts(ids)
    const idSet = new Set(ids)
    scripts.value = scripts.value.filter((s) => !idSet.has(s.id))
    return res.data
  }

  async function runScript(id: number, request: ScriptRunRequest) {
    const res = await scriptsApi.runScript(id, request)
    return res.data
  }

  return {
    scripts,
    currentScript,
    loading,
    fetchScripts,
    fetchScript,
    createScript,
    updateScript,
    deleteScript,
    batchDeleteScripts,
    runScript,
  }
})

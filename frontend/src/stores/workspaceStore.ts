import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import * as wsApi from '@/api/workspace'
import type { Workspace, WorkspaceCreate, WorkspaceUpdate } from '@/types/workspace'

const STORAGE_KEY = 'atp_current_workspace_id'

export const useWorkspaceStore = defineStore('workspaces', () => {
  const workspaces = ref<Workspace[]>([])
  const loading = ref(false)
  const currentWorkspaceId = ref<number | null>(
    localStorage.getItem(STORAGE_KEY) ? Number(localStorage.getItem(STORAGE_KEY)) : null
  )

  const currentWorkspace = computed(() =>
    workspaces.value.find((w) => w.id === currentWorkspaceId.value)
  )

  watch(currentWorkspaceId, (id) => {
    if (id === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  })

  function setCurrentWorkspace(id: number) {
    currentWorkspaceId.value = id
  }

  async function fetchWorkspaces() {
    loading.value = true
    try {
      const res = await wsApi.listWorkspaces()
      workspaces.value = res.data
      // 持久化的 id 已被删除时回退第一个空间
      const first = workspaces.value[0]
      if (first && !workspaces.value.some((w) => w.id === currentWorkspaceId.value)) {
        currentWorkspaceId.value = first.id
      }
    } finally {
      loading.value = false
    }
  }

  async function createWorkspace(data: WorkspaceCreate) {
    const res = await wsApi.createWorkspace(data)
    await fetchWorkspaces()
    return res.data
  }

  async function updateWorkspace(id: number, data: WorkspaceUpdate) {
    const res = await wsApi.updateWorkspace(id, data)
    const index = workspaces.value.findIndex((w) => w.id === id)
    if (index !== -1) workspaces.value[index] = res.data
    return res.data
  }

  async function deleteWorkspace(id: number) {
    await wsApi.deleteWorkspace(id)
    await fetchWorkspaces()
  }

  return {
    workspaces,
    loading,
    currentWorkspaceId,
    currentWorkspace,
    setCurrentWorkspace,
    fetchWorkspaces,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
  }
})

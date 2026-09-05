import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dvApi from '@/api/dataViews'
import type { DataView, DataViewCreate, DataViewUpdate } from '@/types/dataView'

export const useDataViewStore = defineStore('dataViews', () => {
  const dataViews = ref<DataView[]>([])
  const loading = ref(false)

  async function fetchDataViews() {
    loading.value = true
    try {
      const res = await dvApi.listDataViews()
      dataViews.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function createDataView(data: DataViewCreate) {
    const res = await dvApi.createDataView(data)
    dataViews.value.push(res.data)
    return res.data
  }

  async function updateDataView(id: number, data: DataViewUpdate) {
    const res = await dvApi.updateDataView(id, data)
    const index = dataViews.value.findIndex((d) => d.id === id)
    if (index !== -1) {
      dataViews.value[index] = res.data
    }
    return res.data
  }

  async function deleteDataView(id: number) {
    await dvApi.deleteDataView(id)
    dataViews.value = dataViews.value.filter((d) => d.id !== id)
  }

  return {
    dataViews,
    loading,
    fetchDataViews,
    createDataView,
    updateDataView,
    deleteDataView,
  }
})

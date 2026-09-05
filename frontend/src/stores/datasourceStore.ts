import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as dsApi from '@/api/datasources'
import type { Datasource, DatasourceCreate, DatasourceTable, DatasourceUpdate } from '@/types/datasource'

export const useDatasourceStore = defineStore('datasources', () => {
  const datasources = ref<Datasource[]>([])
  const currentDatasource = ref<Datasource | null>(null)
  const tables = ref<DatasourceTable[]>([])
  const databases = ref<string[]>([])
  const loading = ref(false)

  async function fetchDatasources() {
    loading.value = true
    try {
      const res = await dsApi.listDatasources()
      datasources.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchDatasource(id: number) {
    const res = await dsApi.listDatasources()
    currentDatasource.value = res.data.find((d) => d.id === id) || null
    return currentDatasource.value
  }

  async function createDatasource(data: DatasourceCreate) {
    const res = await dsApi.createDatasource(data)
    datasources.value.push(res.data)
    return res.data
  }

  async function updateDatasource(id: number, data: DatasourceUpdate) {
    const res = await dsApi.updateDatasource(id, data)
    const index = datasources.value.findIndex((d) => d.id === id)
    if (index !== -1) {
      datasources.value[index] = res.data
    }
    return res.data
  }

  async function deleteDatasource(id: number) {
    await dsApi.deleteDatasource(id)
    datasources.value = datasources.value.filter((d) => d.id !== id)
  }

  async function fetchTables(id: number, database?: string) {
    const res = await dsApi.listTables(id, database)
    tables.value = res.data
    return res.data
  }

  async function fetchDatabases(id: number) {
    const res = await dsApi.listDatabases(id)
    databases.value = res.data
    return res.data
  }

  return {
    datasources,
    currentDatasource,
    tables,
    databases,
    loading,
    fetchDatasources,
    fetchDatasource,
    createDatasource,
    updateDatasource,
    deleteDatasource,
    fetchTables,
    fetchDatabases,
  }
})

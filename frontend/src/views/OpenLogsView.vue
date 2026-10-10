<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import { clearOpenLogs, listOpenLogs } from '@/api/openPlatform'
import type { OpenApiLog } from '@/types/openPlatform'
import type { OpenApp } from '@/types/openPlatform'
import { listOpenApps } from '@/api/openPlatform'

const loading = ref(false)
const logs = ref<OpenApiLog[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filterAppId = ref<number | null>(null)
const filterSuccess = ref<boolean | null>(null)
const apps = ref<OpenApp[]>([])

async function fetchLogs() {
  loading.value = true
  try {
    const params: { app_id?: number; success?: boolean } = {}
    if (filterAppId.value !== null) params.app_id = filterAppId.value
    if (filterSuccess.value !== null) params.success = filterSuccess.value
    const res = await listOpenLogs((page.value - 1) * pageSize, pageSize, params)
    logs.value = res.data.items
    total.value = res.data.total
  } catch (error) {
    ElMessage.error('加载调用日志失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

async function fetchApps() {
  try {
    const res = await listOpenApps(0, 100)
    apps.value = res.data.items
  } catch (error) {
    console.error(error)
  }
}

onMounted(() => {
  fetchLogs()
  fetchApps()
})

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空全部调用日志吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await clearOpenLogs()
    ElMessage.success('已清空')
    page.value = 1
    await fetchLogs()
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

function statusTagType(code: number) {
  if (code >= 200 && code < 300) return 'success'
  if (code >= 400 && code < 500) return 'warning'
  return 'danger'
}

function handleFilter() {
  page.value = 1
  fetchLogs()
}

function handlePageChange() {
  fetchLogs()
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>调用日志</h2>
      <el-button type="danger" plain @click="handleClear">清空日志</el-button>
    </div>

    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="应用">
          <el-select
            v-model="filterAppId"
            placeholder="全部应用"
            clearable
            style="width: 200px"
            @change="handleFilter"
          >
            <el-option v-for="app in apps" :key="app.id" :label="app.name" :value="app.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果">
          <el-select
            v-model="filterSuccess"
            placeholder="全部"
            clearable
            style="width: 140px"
            @change="handleFilter"
          >
            <el-option label="成功" :value="true" />
            <el-option label="失败" :value="false" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading">
      <el-table :data="logs" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="应用" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ apps.find((a) => a.id === row.app_id)?.name || (row.app_key || '未知调用方') }}
          </template>
        </el-table-column>
        <el-table-column label="方法" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="路径" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态码" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status_code)" size="small">{{ row.status_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行 ID" width="100">
          <template #default="{ row }">
            <span v-if="row.execution_id">{{ row.execution_id }}</span>
            <span v-else class="dim">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="摘要" min-width="180" show-overflow-tooltip />
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          layout="total, prev, pager, next, jumper"
          :total="total"
          :page-size="pageSize"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.dim {
  color: #c0c4cc;
}
</style>

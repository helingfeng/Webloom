<script setup lang="ts">
import { ref, watch } from 'vue'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import ExecutionPanel from '@/components/ExecutionPanel.vue'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'

const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()
const showPanel = ref(false)

watch(
  () => wsStore.currentWorkspaceId,
  (id) => executionStore.fetchExecutions(1, id ?? undefined),
  { immediate: true }
)

function viewExecution(id: number) {
  executionStore.fetchExecution(id)
  showPanel.value = true
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该执行记录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await executionStore.deleteExecution(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

async function handleClear() {
  try {
    await ElMessageBox.confirm(
      `确定清空全部 ${executionStore.total} 条执行记录吗？此操作不可恢复。`,
      '清空执行记录',
      {
        confirmButtonText: '清空',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      }
    )
    await executionStore.clearExecutions()
    ElMessage.success('已清空')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

function handlePageChange(targetPage: number) {
  executionStore.fetchExecutions(targetPage)
}

function statusType(status: string) {
  const map: Record<string, string> = {
    success: 'success',
    failed: 'danger',
    running: 'primary',
    pending: 'info',
  }
  return map[status] || 'info'
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>执行记录 <span class="total-count">共 {{ executionStore.total }} 条</span></h2>
      <el-button type="danger" :disabled="executionStore.total === 0" @click="handleClear">
        <el-icon><Delete /></el-icon> 一键清空
      </el-button>
    </div>

    <el-card v-loading="executionStore.loading">
      <el-table :data="executionStore.executions" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="target_type" label="目标类型" min-width="100" />
        <el-table-column prop="target_id" label="目标 ID" width="90" />
        <el-table-column prop="mode" label="模式" min-width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="170">
          <template #default="{ row }">
            {{ formatDateTime(row.finished_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewExecution(row.id)">查看</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="executionStore.page"
          :page-size="executionStore.pageSize"
          :total="executionStore.total"
          layout="total, prev, pager, next, jumper"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <ExecutionPanel v-model:visible="showPanel" :execution="executionStore.currentExecution" />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.total-count {
  color: #909399;
  font-size: 14px;
  font-weight: normal;
  margin-left: 10px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 15px;
}
</style>

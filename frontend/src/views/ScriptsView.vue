<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useScriptStore } from '@/stores/scriptStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { listExecutions } from '@/api/executions'
import { apiError } from '@/api/collectors'
import ExecutionPanel from '@/components/ExecutionPanel.vue'
import { formatDateTime } from '@/utils/format'
import type { Execution } from '@/types/execution'
import type { Script } from '@/types/script'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const scriptStore = useScriptStore()
const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()

watch(
  () => wsStore.currentWorkspaceId,
  (id) => scriptStore.fetchScripts(id ?? undefined),
  { immediate: true }
)

// 执行记录弹窗（局部状态，不污染全局 executionStore 分页）
const execDialogVisible = ref(false)
const execDialogScriptName = ref('')
const execItems = ref<Execution[]>([])
const execLoading = ref(false)
const panelVisible = ref(false)

async function openExecDialog(row: { id: number; name: string }) {
  execDialogScriptName.value = row.name
  execDialogVisible.value = true
  execLoading.value = true
  try {
    const res = await listExecutions(0, 100, undefined, row.id)
    execItems.value = res.data.items
  } catch (error) {
    ElMessage.error('获取执行记录失败')
    console.error(error)
  } finally {
    execLoading.value = false
  }
}

async function viewExecution(id: number) {
  execDialogVisible.value = false
  await executionStore.fetchExecution(id)
  panelVisible.value = true
}

function handleEdit(id: number) {
  router.push(`/scripts/${id}`)
}

function handleCreate() {
  router.push('/scripts/new')
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

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该脚本吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await scriptStore.deleteScript(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(apiError(error))
      console.error(error)
    }
  }
}

// 列表快捷运行：manual 模式且有输入变量的脚本跳编辑页填写，其余按保存的运行配置直接执行
const runningIds = ref(new Set<number>())

async function handleRun(row: Script) {
  if ((row.inputs?.length ?? 0) > 0) {
    ElMessage.info('该脚本有输入变量，请在运行配置中填写后运行')
    router.push(`/scripts/${row.id}`)
    return
  }
  runningIds.value.add(row.id)
  runningIds.value = new Set(runningIds.value)
  try {
    const result = await scriptStore.runScript(row.id, {
      mode: 'manual',
      inputs: {},
      headless: row.headless ?? true,
    })
    if (result.execution_id) {
      await executionStore.fetchExecution(result.execution_id)
    }
    panelVisible.value = true
  } catch (error) {
    ElMessage.error('运行请求失败')
    console.error(error)
  } finally {
    runningIds.value.delete(row.id)
    runningIds.value = new Set(runningIds.value)
  }
}

// 批量删除
const selectedScripts = ref<Script[]>([])

function handleSelectionChange(rows: Script[]) {
  selectedScripts.value = rows
}

async function handleBatchDelete() {
  if (selectedScripts.value.length === 0) {
    ElMessage.warning('请先选择要删除的脚本')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedScripts.value.length} 个脚本吗？删除后不可恢复。`, '批量删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await scriptStore.batchDeleteScripts(selectedScripts.value.map((s) => s.id))
    selectedScripts.value = []
    ElMessage.success('批量删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>脚本管理</h2>
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon> 新建脚本
      </el-button>
    </div>

    <el-card v-loading="scriptStore.loading">
      <div class="table-toolbar">
        <el-button type="danger" :disabled="selectedScripts.length === 0" @click="handleBatchDelete">
          <el-icon><Delete /></el-icon> 批量删除
          <span v-if="selectedScripts.length > 0">（{{ selectedScripts.length }}）</span>
        </el-button>
      </div>
      <el-table :data="scriptStore.scripts" style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="脚本名称" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="start_url" label="起始 URL" show-overflow-tooltip />
        <el-table-column label="输入变量" width="120">
          <template #default="{ row }">
            {{ row.inputs?.length || 0 }} 个
          </template>
        </el-table-column>
        <el-table-column label="操作" width="410">
          <template #default="{ row }">
            <el-button
              size="small"
              type="success"
              :loading="runningIds.has(row.id)"
              @click="handleRun(row)"
            >运行</el-button>
            <el-button size="small" @click="openExecDialog(row)">执行记录</el-button>
            <el-button size="small" @click="handleEdit(row.id)">编辑</el-button>
            <el-button size="small" type="primary" plain @click="router.push({ path: '/collectors', query: { script_id: row.id } })">发布接口</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="execDialogVisible"
      :title="`执行记录 - ${execDialogScriptName}`"
      width="60%"
    >
      <el-table v-loading="execLoading" :data="execItems" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="mode" label="模式" width="100" />
        <el-table-column label="开始时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.finished_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewExecution(row.id)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无执行记录</template>
      </el-table>
    </el-dialog>

    <ExecutionPanel
      v-model:visible="panelVisible"
      :execution="executionStore.currentExecution"
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.table-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
</style>

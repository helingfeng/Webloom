<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFlowStore } from '@/stores/flowStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const flowStore = useFlowStore()
const wsStore = useWorkspaceStore()

watch(
  () => wsStore.currentWorkspaceId,
  (id) => flowStore.fetchFlows(id ?? undefined),
  { immediate: true }
)

function handleCreate() {
  router.push('/flows/new')
}

function handleEdit(id: number) {
  router.push(`/flows/${id}`)
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该流程吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await flowStore.deleteFlow(id)
    ElMessage.success('删除成功')
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
      <h2>流程编排</h2>
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon> 新建流程
      </el-button>
    </div>

    <el-card v-loading="flowStore.loading">
      <el-empty v-if="flowStore.flows.length === 0" description="暂无流程，点击右上角新建" />
      <el-table v-else :data="flowStore.flows" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="流程名称" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column label="节点数" width="100">
          <template #default="{ row }">
            {{ row.nodes?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row.id)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
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
</style>

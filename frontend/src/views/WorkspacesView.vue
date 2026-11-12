<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { WorkspaceCreate } from '@/types/workspace'

const wsStore = useWorkspaceStore()

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)

const form = reactive<WorkspaceCreate>({
  name: '',
  description: '',
})

onMounted(() => {
  wsStore.fetchWorkspaces()
})

function openCreate() {
  editingId.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.description = row.description
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入空间名称')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await wsStore.updateWorkspace(editingId.value, { ...form })
      ElMessage.success('更新成功')
    } else {
      await wsStore.createWorkspace({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '保存失败')
    console.error(error)
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该项目空间吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await wsStore.deleteWorkspace(id)
    ElMessage.success('删除成功')
  } catch (error: any) {
    if (error !== 'cancel') {
      const detail = error?.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : '删除失败')
      console.error(error)
    }
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>项目空间</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建空间
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="项目空间用于组织采集脚本。左侧切换空间后，脚本管理、执行记录与首页脚本统计按当前空间过滤；空间下仍有脚本时不可删除。"
    />

    <el-card v-loading="wsStore.loading">
      <el-table :data="wsStore.workspaces" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="180">
          <template #default="{ row }">
            <el-tag v-if="row.id === wsStore.currentWorkspaceId" type="success" size="small" style="margin-right: 6px">当前</el-tag>
            {{ row.name }}
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑项目空间' : '新建项目空间'"
      width="480px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="空间名称，如：电商后台" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
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

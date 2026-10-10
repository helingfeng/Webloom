<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import {
  createOpenApi,
  deleteOpenApi,
  listOpenApis,
  updateOpenApi,
} from '@/api/openPlatform'
import type { OpenApiMethod, OpenApiRoute, OpenApiRouteCreate } from '@/types/openPlatform'

const loading = ref(false)
const routes = ref<OpenApiRoute[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<OpenApiRouteCreate>({
  name: '',
  method: 'GET',
  path: '',
  target_path: '',
  enabled: true,
  description: '',
})

const methodTagType = (method: string) =>
  method === 'GET' ? 'success' : method === 'POST' ? 'primary' : method === 'DELETE' ? 'danger' : 'warning'

async function fetchRoutes() {
  loading.value = true
  try {
    const res = await listOpenApis((page.value - 1) * pageSize, pageSize)
    routes.value = res.data.items
    total.value = res.data.total
  } catch (error) {
    ElMessage.error('加载开放接口失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

onMounted(fetchRoutes)

function openCreate() {
  editingId.value = null
  form.name = ''
  form.method = 'GET'
  form.path = ''
  form.target_path = ''
  form.enabled = true
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row: OpenApiRoute) {
  editingId.value = row.id
  form.name = row.name
  form.method = row.method
  form.path = row.path
  form.target_path = row.target_path
  form.enabled = row.enabled
  form.description = row.description
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入接口名称')
    return
  }
  if (!form.path.startsWith('/')) {
    ElMessage.warning('外部路径必须以 / 开头（无需携带 /open 前缀）')
    return
  }
  if (!form.target_path.startsWith('/api/')) {
    ElMessage.warning('内部目标路径必须以 /api/ 开头')
    return
  }
  try {
    if (editingId.value) {
      await updateOpenApi(editingId.value, { ...form })
      ElMessage.success('更新成功')
    } else {
      await createOpenApi({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchRoutes()
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleToggle(row: OpenApiRoute) {
  try {
    await updateOpenApi(row.id, { enabled: row.enabled })
    ElMessage.success(row.enabled ? '已启用' : '已停用')
  } catch (error) {
    row.enabled = !row.enabled
    ElMessage.error('操作失败')
    console.error(error)
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('删除后外部将无法再调用该接口，确定删除吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteOpenApi(id)
    ElMessage.success('删除成功')
    await fetchRoutes()
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

function handlePageChange() {
  fetchRoutes()
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>开放接口</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建接口
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      title="内置采集接口无需配置即可使用：POST /open/api/v1/collect/trigger（传链接发起采集）、GET /open/api/v1/collect/result（查询采集结果）、GET /open/api/v1/collect/tasks（任务列表）。详见「接入文档」。"
    />
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="下方为代理接口：把平台内部 /api 接口封装为开放接口供外部调用（服务端转发，外部只需开放域名 + 应用凭证）。外部路径支持 {param} 占位，会替换到目标路径同名占位。"
    />

    <el-card v-loading="loading">
      <el-table :data="routes" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="接口名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="方法" width="90">
          <template #default="{ row }">
            <el-tag :type="methodTagType(row.method)">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="外部路径" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="mono">/open{{ row.path }}</code>
          </template>
        </el-table-column>
        <el-table-column label="内部目标" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="mono">{{ row.target_path }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑开放接口' : '新建开放接口'"
      width="560px"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="接口名称" required>
          <el-input v-model="form.name" placeholder="例如：查询执行记录" />
        </el-form-item>
        <el-form-item label="HTTP 方法" required>
          <el-select v-model="form.method" style="width: 140px">
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
            <el-option label="PUT" value="PUT" />
            <el-option label="DELETE" value="DELETE" />
            <el-option label="PATCH" value="PATCH" />
          </el-select>
        </el-form-item>
        <el-form-item label="外部路径" required>
          <el-input
            v-model="form.path"
            placeholder="/v1/executions/{execution_id}（相对 /open 前缀）"
          />
        </el-form-item>
        <el-form-item label="内部目标路径" required>
          <el-input
            v-model="form.target_path"
            placeholder="/api/executions/{execution_id}（以 /api/ 开头）"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="说明该接口的用途与权限要求" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
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

.mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 13px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>

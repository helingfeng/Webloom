<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDatasourceStore } from '@/stores/datasourceStore'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import { testDatasource, testDatasourceById } from '@/api/datasources'
import type { DatasourceTestResult } from '@/types/datasource'

const router = useRouter()
const dsStore = useDatasourceStore()

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const testing = ref(false)
const testingRowId = ref<number | null>(null)

const form = reactive({
  name: '',
  host: '',
  port: 3306,
  user: 'root',
  password: '',
  database: '',
  description: '',
})

onMounted(() => {
  dsStore.fetchDatasources()
})

function openCreate() {
  editingId.value = null
  form.name = ''
  form.host = ''
  form.port = 3306
  form.user = 'root'
  form.password = ''
  form.database = ''
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.host = row.host
  form.port = row.port
  form.user = row.user
  form.password = ''
  form.database = row.database || ''
  form.description = row.description || ''
  dialogVisible.value = true
}

async function handleTestInDialog() {
  if (!form.host.trim() || !form.user.trim()) {
    ElMessage.warning('请先填写主机和用户名')
    return
  }
  testing.value = true
  try {
    const res = await testDatasource({
      host: form.host,
      port: form.port,
      user: form.user,
      password: form.password,
      database: form.database,
    })
    showTestResult(res.data)
  } catch (error) {
    ElMessage.error('测试请求失败')
    console.error(error)
  } finally {
    testing.value = false
  }
}

async function handleTestRow(id: number) {
  testingRowId.value = id
  try {
    const res = await testDatasourceById(id)
    showTestResult(res.data)
  } catch (error) {
    ElMessage.error('测试请求失败')
    console.error(error)
  } finally {
    testingRowId.value = null
  }
}

function showTestResult(result: DatasourceTestResult) {
  if (result.success) {
    ElMessage.success(`连接成功（${result.elapsed_ms}ms，${result.server_version}）`)
  } else {
    ElMessage.error(`连接失败：${result.error || '未知错误'}`)
  }
}

async function handleSave() {
  if (!form.name.trim() || !form.host.trim() || !form.user.trim()) {
    ElMessage.warning('请填写名称、主机和用户名')
    return
  }
  if (!editingId.value && !form.password) {
    ElMessage.warning('请填写密码')
    return
  }
  try {
    if (editingId.value) {
      // 密码留空 = 不修改
      const payload: Record<string, any> = {
        name: form.name,
        host: form.host,
        port: form.port,
        user: form.user,
        database: form.database,
        description: form.description,
      }
      if (form.password) {
        payload.password = form.password
      }
      await dsStore.updateDatasource(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await dsStore.createDatasource({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该数据源吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await dsStore.deleteDatasource(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

function openWorkbench(id: number) {
  router.push(`/datasources/${id}/workbench`)
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>数据源</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建连接
      </el-button>
    </div>

    <el-card v-loading="dsStore.loading">
      <el-table :data="dsStore.datasources" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="主机" min-width="160">
          <template #default="{ row }">
            {{ row.host }}:{{ row.port }}
          </template>
        </el-table-column>
        <el-table-column prop="user" label="用户" width="100" />
        <el-table-column prop="database" label="数据库" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.database">{{ row.database }}</span>
            <el-tag v-else type="info" size="small">未指定</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :loading="testingRowId === row.id"
              @click="handleTestRow(row.id)"
            >测试</el-button>
            <el-button size="small" type="primary" @click="openWorkbench(row.id)">工作台</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑数据源' : '新建数据源'"
      width="520px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="连接名称，如：测试库" />
        </el-form-item>
        <el-form-item label="主机" required>
          <el-input v-model="form.host" placeholder="例如：127.0.0.1" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="用户名" required>
          <el-input v-model="form.user" placeholder="例如：root" />
        </el-form-item>
        <el-form-item label="密码" :required="!editingId">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editingId ? '留空则不修改' : '数据库密码'"
          />
        </el-form-item>
        <el-form-item label="数据库">
          <el-input v-model="form.database" placeholder="默认连接的库名（列出表/表结构依赖此项）" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="testing" @click="handleTestInDialog">测试连接</el-button>
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
</style>

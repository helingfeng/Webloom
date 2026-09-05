<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useDataViewStore } from '@/stores/dataViewStore'
import { useDatasourceStore } from '@/stores/datasourceStore'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import { runDataView } from '@/api/dataViews'
import { listDatabases } from '@/api/datasources'
import SqlInput from '@/components/SqlInput.vue'
import type { QueryResult } from '@/types/datasource'
import type { DataView } from '@/types/dataView'

const dvStore = useDataViewStore()
const dsStore = useDatasourceStore()

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewResult = ref<QueryResult | null>(null)

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,63}$/

const form = reactive({
  name: '',
  slug: '',
  datasource_id: null as number | null,
  database: '',
  sql: '',
  description: '',
  enabled: true,
})

// 数据库下拉选项（随数据源变化）
const databaseOptions = ref<string[]>([])
const databasesLoading = ref(false)

async function loadDatabaseOptions(dsId: number) {
  databasesLoading.value = true
  try {
    const res = await listDatabases(dsId)
    databaseOptions.value = res.data
  } catch {
    databaseOptions.value = []
  } finally {
    databasesLoading.value = false
  }
}

function handleDatasourceChange(dsId: number) {
  // 仅用户交互触发：切换数据源后旧库失效，清空并重载选项
  form.database = ''
  if (dsId) loadDatabaseOptions(dsId)
}

onMounted(() => {
  dvStore.fetchDataViews()
  dsStore.fetchDatasources()
})

function getDatasourceName(id: number) {
  return dsStore.datasources.find((d) => d.id === id)?.name
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.slug = ''
  form.datasource_id = dsStore.datasources[0]?.id ?? null
  form.database = ''
  form.sql = 'SELECT '
  form.description = ''
  form.enabled = true
  databaseOptions.value = []
  if (form.datasource_id) loadDatabaseOptions(form.datasource_id)
  dialogVisible.value = true
}

function openEdit(row: DataView) {
  editingId.value = row.id
  form.name = row.name
  form.slug = row.slug
  form.datasource_id = row.datasource_id
  form.database = row.database || ''
  form.sql = row.sql
  form.description = row.description
  form.enabled = row.enabled
  loadDatabaseOptions(row.datasource_id)
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入视图名称')
    return
  }
  if (!SLUG_RE.test(form.slug)) {
    ElMessage.warning('slug 仅允许小写字母、数字和中划线，且以字母或数字开头（最长 64 字符）')
    return
  }
  if (!form.datasource_id) {
    ElMessage.warning('请选择数据源')
    return
  }
  if (!form.sql.trim()) {
    ElMessage.warning('请输入 SQL 语句')
    return
  }
  saving.value = true
  try {
    const payload = { ...form, datasource_id: form.datasource_id }
    if (editingId.value) {
      await dvStore.updateDataView(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await dvStore.createDataView(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    if (typeof detail === 'string') {
      ElMessage.error(detail)
    } else {
      ElMessage.error('保存失败')
    }
    console.error(error)
  } finally {
    saving.value = false
  }
}

async function handleRun(row: DataView) {
  previewTitle.value = `${row.name}（${row.slug}）`
  previewResult.value = null
  previewVisible.value = true
  previewLoading.value = true
  try {
    const res = await runDataView(row.id)
    previewResult.value = res.data
  } catch (error) {
    ElMessage.error('运行请求失败')
    console.error(error)
  } finally {
    previewLoading.value = false
  }
}

async function handleCopyLink(row: DataView) {
  const url = `${window.location.origin}/api/data/${row.slug}`
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(`已复制：${url}`)
  } catch {
    // clipboard API 不可用时降级
    const input = document.createElement('textarea')
    input.value = url
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    ElMessage.success(`已复制：${url}`)
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该数据视图吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await dvStore.deleteDataView(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

// 预览结果：二维数组转对象数组
const previewRows = computed(() => {
  const r = previewResult.value
  if (!r || !r.success || r.statement_type !== 'query') return []
  return r.rows.map((row) => Object.fromEntries(r.columns.map((c, i) => [c, row[i]])))
})

function formatCell(value: any) {
  if (value === null || value === undefined) return 'NULL'
  return value
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>数据视图</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建视图
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="数据视图 = 数据源 + 只读 SQL。保存后外部系统可通过 GET /api/data/{slug} 直接获取 JSON 数据，无需鉴权；停用的视图对外表现为不存在。脚本中可通过 DATA_VIEWS[&quot;slug&quot;] 直接引用启用中的视图数据（Playwright 脚本自动注入），DATA_VIEWS_ONE[&quot;slug&quot;] 取首行对象（空结果为 None）。"
    />

    <el-card v-loading="dvStore.loading">
      <el-table :data="dvStore.dataViews" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="Slug" min-width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.slug }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据源" min-width="130">
          <template #default="{ row }">
            <span v-if="getDatasourceName(row.datasource_id)">{{ getDatasourceName(row.datasource_id) }}</span>
            <el-tag v-else type="danger" size="small">数据源已删除</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据库" min-width="110">
          <template #default="{ row }">{{ row.database || '默认库' }}</template>
        </el-table-column>
        <el-table-column prop="sql" label="SQL" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="handleRun(row)">运行</el-button>
            <el-button size="small" @click="handleCopyLink(row)">复制链接</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑数据视图' : '新建数据视图'"
      width="640px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="视图名称，如：用户列表" />
        </el-form-item>
        <el-form-item label="数据源" required>
          <el-select
            v-model="form.datasource_id"
            placeholder="选择数据源"
            style="width: 100%"
            @change="handleDatasourceChange"
          >
            <el-option
              v-for="ds in dsStore.datasources"
              :key="ds.id"
              :label="`${ds.name} (${ds.host}:${ds.port}/${ds.database || '-'})`"
              :value="ds.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据库">
          <el-select
            v-model="form.database"
            filterable
            clearable
            placeholder="沿用数据源默认库"
            :loading="databasesLoading"
            :disabled="!form.datasource_id"
            style="width: 100%"
          >
            <el-option
              v-for="db in databaseOptions"
              :key="db"
              :label="db"
              :value="db"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Slug" required>
          <el-input v-model="form.slug" placeholder="外部访问标识，如：users-list（小写字母/数字/中划线）" />
        </el-form-item>
        <el-form-item label="SQL" required>
          <SqlInput
            v-model="form.sql"
            :rows="8"
            placeholder="仅允许只读查询：SELECT / SHOW / DESC / DESCRIBE / EXPLAIN / WITH / VALUES / TABLE"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="`运行预览 - ${previewTitle}`" width="85%">
      <div v-loading="previewLoading">
        <template v-if="previewResult">
          <div class="result-status">
            <el-tag v-if="previewResult.success" type="success">成功</el-tag>
            <el-tag v-else type="danger">失败</el-tag>
            <span class="status-item">耗时 {{ previewResult.elapsed_ms }} ms</span>
            <span v-if="previewResult.success" class="status-item">
              返回 {{ previewResult.row_count }} 行
            </span>
            <el-tag v-if="previewResult.truncated" type="warning">结果超过 1000 行，已截断</el-tag>
          </div>
          <pre v-if="previewResult.error" class="error-block">{{ previewResult.error }}</pre>
          <el-table
            v-else
            :data="previewRows"
            size="small"
            border
            max-height="480"
          >
            <el-table-column
              v-for="(col, i) in previewResult.columns"
              :key="col + i"
              :prop="col"
              :label="col"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ formatCell(row[col]) }}
              </template>
            </el-table-column>
          </el-table>
        </template>
        <el-empty v-else-if="!previewLoading" description="无结果" :image-size="60" />
      </div>
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

.result-status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.status-item {
  font-size: 13px;
  color: #606266;
}

.error-block {
  background-color: #1e1e1e;
  color: #f56c6c;
  padding: 12px;
  border-radius: 4px;
  font-family: 'SF Mono', 'Menlo', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDatasourceStore } from '@/stores/datasourceStore'
import {
  clearQueryHistory,
  deleteQueryHistory,
  getQueryHistoryDetail,
  getTableSchema,
  listQueryHistory,
  runQuery,
  testDatasourceById,
} from '@/api/datasources'
import SqlInput from '@/components/SqlInput.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import type {
  DatasourceColumn,
  QueryHistoryDetail,
  QueryHistoryItem,
  QueryResult,
} from '@/types/datasource'

const route = useRoute()
const router = useRouter()
const dsStore = useDatasourceStore()

const dsId = computed(() => Number(route.params.id))
const tableSearch = ref('')
const selectedTable = ref('')
const tableColumns = ref<DatasourceColumn[]>([])
const columnsLoading = ref(false)
const currentDatabase = ref('')
const databasesLoading = ref(false)

const sql = ref('SELECT 1')
const executing = ref(false)
const result = ref<QueryResult | null>(null)
const testing = ref(false)

const resultTab = ref('result')
const HISTORY_PAGE_SIZE = 20
const historyItems = ref<QueryHistoryItem[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyLoading = ref(false)
const historyDetailVisible = ref(false)
const historyDetailLoading = ref(false)
const historyDetail = ref<QueryHistoryDetail | null>(null)

onMounted(async () => {
  await dsStore.fetchDatasource(dsId.value)
  try {
    databasesLoading.value = true
    await dsStore.fetchDatabases(dsId.value)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取数据库列表失败')
  } finally {
    databasesLoading.value = false
  }
  currentDatabase.value =
    dsStore.currentDatasource?.database || dsStore.databases[0] || ''
  try {
    await dsStore.fetchTables(dsId.value, currentDatabase.value || undefined)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取表列表失败')
  }
})

const filteredTables = computed(() => {
  const keyword = tableSearch.value.trim().toLowerCase()
  if (!keyword) return dsStore.tables
  return dsStore.tables.filter((t) => t.name.toLowerCase().includes(keyword))
})

async function loadTableSchema(table: string) {
  selectedTable.value = table
  tableColumns.value = []
  columnsLoading.value = true
  try {
    const res = await getTableSchema(
      dsId.value,
      table,
      currentDatabase.value || undefined
    )
    tableColumns.value = res.data
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取表结构失败')
  } finally {
    columnsLoading.value = false
  }
}

async function handleDatabaseChange() {
  selectedTable.value = ''
  tableColumns.value = []
  try {
    await dsStore.fetchTables(dsId.value, currentDatabase.value || undefined)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取表列表失败')
  }
}

function insertTableToSql(table: string) {
  const current = sql.value
  const trimmed = current && !current.endsWith('\n') ? current + '\n' : current
  sql.value = `${trimmed}${table} `
}

async function handleExecute() {
  if (!sql.value.trim()) {
    ElMessage.warning('请输入 SQL 语句')
    return
  }
  executing.value = true
  try {
    const res = await runQuery(dsId.value, {
      sql: sql.value,
      database: currentDatabase.value || undefined,
    })
    result.value = res.data
    resultTab.value = 'result'
    fetchHistory(1)
  } catch (error) {
    console.error(error)
    ElMessage.error('执行请求失败')
  } finally {
    executing.value = false
  }
}

async function fetchHistory(page = historyPage.value) {
  historyLoading.value = true
  try {
    const res = await listQueryHistory(
      dsId.value,
      (page - 1) * HISTORY_PAGE_SIZE,
      HISTORY_PAGE_SIZE
    )
    historyItems.value = res.data.items
    historyTotal.value = res.data.total
    historyPage.value = page
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取执行历史失败')
  } finally {
    historyLoading.value = false
  }
}

function handleTabChange(tab: string | number) {
  if (tab === 'history') fetchHistory(1)
}

async function openHistoryDetail(item: QueryHistoryItem) {
  historyDetail.value = null
  historyDetailVisible.value = true
  historyDetailLoading.value = true
  try {
    const res = await getQueryHistoryDetail(dsId.value, item.id)
    historyDetail.value = res.data
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取历史详情失败')
    historyDetailVisible.value = false
  } finally {
    historyDetailLoading.value = false
  }
}

function loadHistorySql(item: QueryHistoryItem) {
  sql.value = item.sql
}

async function handleDeleteHistory(item: QueryHistoryItem) {
  try {
    await deleteQueryHistory(dsId.value, item.id)
    if (historyItems.value.length === 1 && historyPage.value > 1) {
      fetchHistory(historyPage.value - 1)
    } else {
      fetchHistory()
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '删除失败')
  }
}

async function handleClearHistory() {
  try {
    await ElMessageBox.confirm('确定清空该数据源的全部执行历史吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await clearQueryHistory(dsId.value)
    fetchHistory(1)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
}

// 历史详情结果：二维数组转对象数组（复用结果区逻辑）
const historyDetailRows = computed(() => {
  const d = historyDetail.value
  if (!d || !d.success || d.statement_type !== 'query') return []
  return d.rows.map((row) =>
    Object.fromEntries(d.columns.map((c, i) => [c, row[i]]))
  )
})

async function handleTest() {
  testing.value = true
  try {
    const res = await testDatasourceById(dsId.value)
    if (res.data.success) {
      ElMessage.success(`连接成功（${res.data.elapsed_ms}ms，${res.data.server_version}）`)
    } else {
      ElMessage.error(`连接失败：${res.data.error || '未知错误'}`)
    }
  } finally {
    testing.value = false
  }
}

// 动态列：把 rows（二维数组）转成 el-table 需要的对象数组
const resultRows = computed(() => {
  const r = result.value
  if (!r || !r.success || r.statement_type !== 'query') return []
  return r.rows.map((row) =>
    Object.fromEntries(r.columns.map((c, i) => [c, row[i]]))
  )
})

function formatCell(value: any) {
  if (value === null || value === undefined) return 'NULL'
  return value
}
</script>

<template>
  <div class="workbench">
    <div class="page-header">
      <div class="header-left">
        <el-button @click="router.push('/datasources')">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <h2>
          {{ dsStore.currentDatasource?.name || '数据源' }}
          <span class="ds-info">
            {{ dsStore.currentDatasource?.user }}@{{ dsStore.currentDatasource?.host }}:{{ dsStore.currentDatasource?.port }}/{{ dsStore.currentDatasource?.database || '-' }}
          </span>
        </h2>
      </div>
      <el-button :loading="testing" @click="handleTest">测试连接</el-button>
    </div>

    <div class="workbench-layout">
      <div class="table-panel">
        <el-select
          v-model="currentDatabase"
          filterable
          placeholder="选择数据库"
          size="small"
          :loading="databasesLoading"
          style="width: 100%; margin-bottom: 10px"
          @change="handleDatabaseChange"
        >
          <el-option
            v-for="db in dsStore.databases"
            :key="db"
            :label="db"
            :value="db"
          />
        </el-select>
        <el-input
          v-model="tableSearch"
          placeholder="搜索表名"
          clearable
          size="small"
          style="margin-bottom: 10px"
        />
        <div v-loading="dsStore.loading" class="table-list">
          <div
            v-for="t in filteredTables"
            :key="t.name"
            class="table-item"
            :class="{ active: selectedTable === t.name }"
            @click="loadTableSchema(t.name)"
          >
            <div class="table-item-main">
              <span class="table-name">{{ t.name }}</span>
              <el-tag v-if="t.table_type === 'VIEW'" size="small" type="warning">VIEW</el-tag>
              <span v-else-if="t.table_rows !== null" class="table-rows">约 {{ t.table_rows }}</span>
            </div>
            <div v-if="t.comment" class="table-comment">{{ t.comment }}</div>
            <el-button
              class="insert-btn"
              size="small"
              text
              type="primary"
              title="插入到 SQL 编辑器"
              @click.stop="insertTableToSql(t.name)"
            >+</el-button>
          </div>
          <el-empty v-if="!dsStore.loading && !filteredTables.length" description="暂无表" :image-size="60" />
        </div>

        <div v-if="selectedTable" class="schema-panel" v-loading="columnsLoading">
          <h4>{{ selectedTable }} 结构</h4>
          <el-table :data="tableColumns" size="small" max-height="260" border>
            <el-table-column prop="name" label="字段" min-width="110" show-overflow-tooltip />
            <el-table-column prop="column_type" label="类型" min-width="110" show-overflow-tooltip />
            <el-table-column label="Key" width="60">
              <template #default="{ row }">
                <el-tag v-if="row.column_key === 'PRI'" size="small" type="danger">PRI</el-tag>
                <el-tag v-else-if="row.column_key" size="small" type="warning">{{ row.column_key }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可空" width="55">
              <template #default="{ row }">{{ row.nullable ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="comment" label="注释" min-width="100" show-overflow-tooltip />
          </el-table>
        </div>
      </div>

      <div class="query-panel">
        <div class="editor-area">
          <div class="editor-toolbar">
            <span class="hint">Ctrl/⌘ + Enter 执行</span>
            <el-button type="primary" :loading="executing" @click="handleExecute">
              执行 SQL
            </el-button>
          </div>
          <SqlInput
            v-model="sql"
            :rows="10"
            placeholder="输入 SQL，如：SELECT * FROM your_table LIMIT 100"
            @execute="handleExecute"
          />
        </div>

        <div class="result-area">
          <el-tabs v-model="resultTab" class="result-tabs" @tab-change="handleTabChange">
            <el-tab-pane label="执行结果" name="result">
              <template v-if="result">
                <div class="result-status">
                  <el-tag v-if="result.success" type="success">成功</el-tag>
                  <el-tag v-else type="danger">失败</el-tag>
                  <span class="status-item">耗时 {{ result.elapsed_ms }} ms</span>
                  <span v-if="result.success && result.statement_type === 'query'" class="status-item">
                    返回 {{ result.row_count }} 行
                  </span>
                  <span v-else-if="result.success" class="status-item">
                    影响 {{ result.affected_rows }} 行
                  </span>
                  <el-tag v-if="result.truncated" type="warning">结果超过 1000 行，已截断</el-tag>
                </div>
                <pre v-if="result.error" class="error-block">{{ result.error }}</pre>
                <el-table
                  v-else-if="result.statement_type === 'query'"
                  :data="resultRows"
                  size="small"
                  border
                  max-height="420"
                >
                  <el-table-column
                    v-for="(col, i) in result.columns"
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
              <el-empty v-else description="执行 SQL 后在此查看结果" :image-size="80" />
            </el-tab-pane>

            <el-tab-pane label="执行历史" name="history">
              <div class="history-toolbar">
                <span class="status-item">共 {{ historyTotal }} 条，点击查看 SQL 与结果</span>
                <el-button size="small" :disabled="!historyTotal" @click="handleClearHistory">
                  清空历史
                </el-button>
              </div>
              <el-table
                :data="historyItems"
                v-loading="historyLoading"
                size="small"
                border
                @row-click="openHistoryDetail"
                class="history-table"
              >
                <el-table-column label="时间" width="155">
                  <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="状态" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                      {{ row.success ? '成功' : '失败' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="sql" label="SQL" min-width="240" show-overflow-tooltip />
                <el-table-column prop="database" label="库" width="110" show-overflow-tooltip />
                <el-table-column label="结果" width="100">
                  <template #default="{ row }">
                    <span v-if="row.success && row.statement_type === 'query'">{{ row.row_count }} 行</span>
                    <span v-else-if="row.success">影响 {{ row.affected_rows }} 行</span>
                    <span v-else class="cell-error">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="耗时" width="80">
                  <template #default="{ row }">{{ row.elapsed_ms }} ms</template>
                </el-table-column>
                <el-table-column label="操作" width="180" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" text type="primary" @click.stop="openHistoryDetail(row)">详情</el-button>
                    <el-button size="small" text type="primary" @click.stop="loadHistorySql(row)">载入编辑器</el-button>
                    <el-button size="small" text type="danger" @click.stop="handleDeleteHistory(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-pagination
                v-if="historyTotal > HISTORY_PAGE_SIZE"
                v-model:current-page="historyPage"
                :page-size="HISTORY_PAGE_SIZE"
                :total="historyTotal"
                layout="total, prev, pager, next"
                style="margin-top: 10px; justify-content: flex-end"
                @current-change="fetchHistory"
              />
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>

    <el-dialog v-model="historyDetailVisible" title="执行历史详情" width="85%">
      <div v-loading="historyDetailLoading">
        <template v-if="historyDetail">
          <div class="result-status">
            <el-tag v-if="historyDetail.success" type="success">成功</el-tag>
            <el-tag v-else type="danger">失败</el-tag>
            <span class="status-item">{{ formatDateTime(historyDetail.created_at) }}</span>
            <span v-if="historyDetail.database" class="status-item">库：{{ historyDetail.database }}</span>
            <span class="status-item">耗时 {{ historyDetail.elapsed_ms }} ms</span>
            <span v-if="historyDetail.success && historyDetail.statement_type === 'query'" class="status-item">
              返回 {{ historyDetail.row_count }} 行
            </span>
            <span v-else-if="historyDetail.success" class="status-item">
              影响 {{ historyDetail.affected_rows }} 行
            </span>
            <el-tag v-if="historyDetail.truncated" type="warning">结果超过 1000 行，已截断</el-tag>
          </div>
          <pre class="sql-block">{{ historyDetail.sql }}</pre>
          <pre v-if="historyDetail.error" class="error-block">{{ historyDetail.error }}</pre>
          <template v-else-if="historyDetail.statement_type === 'query'">
            <div v-if="historyDetail.rows.length < historyDetail.row_count" class="sample-tip">
              历史记录仅保留前 {{ historyDetail.rows.length }} 行样本（当时共 {{ historyDetail.row_count }} 行）
            </div>
            <el-table :data="historyDetailRows" size="small" border max-height="420">
              <el-table-column
                v-for="(col, i) in historyDetail.columns"
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
        </template>
        <el-empty v-else-if="!historyDetailLoading" description="无内容" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 15px;
}

.header-left h2 {
  margin: 0;
  font-size: 18px;
}

.ds-info {
  font-size: 13px;
  font-weight: normal;
  color: #909399;
  margin-left: 8px;
}

.workbench-layout {
  flex: 1;
  display: flex;
  gap: 15px;
  min-height: 0;
}

.table-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 12px;
  overflow: hidden;
}

.table-list {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
}

.table-item {
  position: relative;
  padding: 6px 26px 6px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.table-item:hover {
  background-color: #f5f7fa;
}

.table-item.active {
  background-color: #ecf5ff;
}

.table-item-main {
  display: flex;
  align-items: center;
  gap: 6px;
}

.table-name {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-rows {
  font-size: 11px;
  color: #c0c4cc;
}

.table-comment {
  font-size: 11px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.insert-btn {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0;
}

.table-item:hover .insert-btn {
  opacity: 1;
}

.schema-panel {
  flex-shrink: 0;
  margin-top: 12px;
  border-top: 1px solid #ebeef5;
  padding-top: 10px;
}

.schema-panel h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #606266;
}

.query-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.editor-toolbar .hint {
  font-size: 12px;
  color: #909399;
}

.result-area {
  flex: 1;
  min-height: 200px;
  background-color: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 12px;
  overflow: auto;
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

.result-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.result-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.history-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.history-table {
  cursor: pointer;
}

.cell-error {
  color: #c0c4cc;
}

.sql-block {
  background-color: #f5f7fa;
  border: 1px solid #ebeef5;
  padding: 12px;
  border-radius: 4px;
  font-family: 'SF Mono', 'Menlo', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0 0 10px 0;
}

.sample-tip {
  font-size: 12px;
  color: #e6a23c;
  margin-bottom: 8px;
}
</style>

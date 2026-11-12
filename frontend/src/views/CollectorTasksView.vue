<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listCollectorTasks, getCollectorTask, listCollectors, apiError } from '@/api/collectors'
import { listOpenApps } from '@/api/openPlatform'
import type { Collector, CollectorTask } from '@/types/collector'
import type { OpenApp } from '@/types/openPlatform'
import CollectorResult from '@/components/CollectorResult.vue'
import { formatDateTime } from '@/utils/format'
const route = useRoute()
const items = ref<CollectorTask[]>([]), collectors = ref<Collector[]>([]), apps = ref<OpenApp[]>([])
const total = ref(0), page = ref(1), loading = ref(false), visible = ref(false), task = ref<CollectorTask>()
const collectorId = ref<number>(), appId = ref<number>(), status = ref<string>()
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false, activeId = 0
const labels = { pending: '排队中', running: '采集中', success: '采集完成', failed: '采集失败' }
async function refresh(silent = false) {
  if (loading.value) return
  loading.value = true
  try { const r = await listCollectorTasks({ skip: (page.value - 1) * 20, limit: 20, collector_id: collectorId.value, app_id: appId.value, status: status.value }); if (!disposed) { items.value = r.data.items; total.value = r.data.total } }
  catch (e) { if (!silent) ElMessage.error(apiError(e)) } finally { loading.value = false }
}
async function open(id: number) {
  activeId = id; task.value = undefined; visible.value = true
  try { const r = await getCollectorTask(id); if (activeId === id && visible.value) task.value = r.data }
  catch (e) { ElMessage.error(apiError(e)) }
}
async function poll() {
  if (disposed) return
  if (visible.value && task.value && !task.value.finished) {
    const id = activeId
    try { const r = await getCollectorTask(id); if (activeId === id) task.value = r.data } catch { /* 下个周期重试 */ }
  }
  if (items.value.some(i => !i.finished)) await refresh(true)
  if (!disposed) timer = setTimeout(poll, 2500)
}
function filter() { page.value = 1; void refresh() }
onMounted(async () => {
  await refresh()
  try { const [c,a] = await Promise.all([listCollectors(),listOpenApps()]); collectors.value = c.data.items; apps.value = a.data.items } catch (e) { ElMessage.error(apiError(e)) }
  const id = Number(route.query.execution_id); if (id) await open(id)
  void poll()
})
onUnmounted(() => { disposed = true; clearTimeout(timer) })
</script>
<template>
  <div><div class="header"><div><h2>采集任务与数据</h2><p>追踪外部调用和在线调试，查看采集结果、失败原因与执行日志。</p></div><el-button @click="refresh()">刷新</el-button></div>
    <el-card class="filters"><el-select v-model="collectorId" clearable placeholder="全部接口" @change="filter"><el-option v-for="c in collectors" :key="c.id" :label="c.name" :value="c.id" /></el-select><el-select v-model="appId" clearable placeholder="全部应用" @change="filter"><el-option v-for="a in apps" :key="a.id" :label="a.name" :value="a.id" /></el-select><el-select v-model="status" clearable placeholder="全部状态" @change="filter"><el-option v-for="(label,key) in labels" :key="key" :value="key" :label="label" /></el-select></el-card>
    <el-card><el-table v-loading="loading" :data="items" empty-text="暂无采集任务，可从采集接口页在线调试"><el-table-column prop="execution_id" label="任务 ID" width="100" /><el-table-column prop="collector_name" label="采集接口" min-width="180" /><el-table-column label="应用" min-width="140"><template #default="{ row }">{{ apps.find(a => a.id === row.app_id)?.name ?? `#${row.app_id}` }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">{{ labels[row.status as keyof typeof labels] }}</el-tag></template></el-table-column><el-table-column label="提交时间" width="170"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column><el-table-column label="完成时间" width="170"><template #default="{ row }">{{ row.finished_at ? formatDateTime(row.finished_at) : '—' }}</template></el-table-column><el-table-column prop="error" label="失败原因" min-width="160" show-overflow-tooltip /><el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><el-button type="primary" link @click="open(row.execution_id)">查看数据 / 日志</el-button></template></el-table-column></el-table><el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="refresh()" /></el-card>
    <el-drawer v-model="visible" title="采集结果" size="min(1000px, 95vw)"><CollectorResult v-if="task" :task="task" /><el-skeleton v-else animated /></el-drawer>
  </div>
</template>
<style scoped>.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px } h2 { margin:0 0 8px } p { color:#909399;font-size:13px } .filters { margin-bottom:16px } .filters :deep(.el-select) { width:200px; margin-right:12px; } .el-pagination { margin-top:16px }</style>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { CollectorContract, CollectorTask, Page } from '@/types/collector'
import CollectorInputs from '@/components/CollectorInputs.vue'
import CollectorResult from '@/components/CollectorResult.vue'
import { formatDateTime } from '@/utils/format'
import BrandIdentity from '@/components/BrandIdentity.vue'
const token = ref(''), connected = ref(false), busy = ref(false), running = ref(false)
const collectors = ref<CollectorContract[]>([]), tasks = ref<CollectorTask[]>([]), total = ref(0), page = ref(1), catalogTotal = ref(0), catalogPage = ref(1)
const selectedId = ref<number>(), inputs = ref<Record<string, unknown>>({}), result = ref<CollectorTask>(), error = ref('')
const selected = computed(() => collectors.value.find(c => c.id === selectedId.value))
let timer: ReturnType<typeof setTimeout> | undefined, epoch = 0, retryKey = ''
watch(selected, value => { inputs.value = { ...value?.example.inputs }; retryKey = '' })
watch(inputs, () => { retryKey = '' }, { deep: true })
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/open/v1${path}`, { ...options, headers: { Authorization: `Bearer ${token.value.trim()}`, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } })
  const body = await response.json()
  if (!response.ok) {
    if (response.status === 401) disconnect(false)
    throw new Error(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((e: {msg: string}) => e.msg).join('；') : '请求失败')
  }
  return body as T
}
function disconnect(clear = true) { epoch++; connected.value = false; clearTimeout(timer); collectors.value = []; tasks.value = []; result.value = undefined; if (clear) token.value = '' }
async function loadCatalog() {
  const version = epoch
  try {
    const data = await request<Page<CollectorContract>>(`/collectors?skip=${(catalogPage.value - 1) * 20}&limit=20`)
    if (version !== epoch) return
    collectors.value = data.items; catalogTotal.value = data.total; selectedId.value = data.items[0]?.id
  } catch(e) { error.value = String(e instanceof Error ? e.message : e) }
}
async function refreshTasks() {
  const version = epoch
  try { const data = await request<Page<CollectorTask>>(`/tasks?skip=${(page.value - 1) * 10}&limit=10`); if (version === epoch) { tasks.value = data.items; total.value = data.total } }
  catch(e) { error.value = e instanceof Error ? e.message : String(e) }
}
async function connect() {
  if (!token.value.trim()) { error.value = '请输入应用调用凭证'; return }
  busy.value = true; error.value = ''; epoch++; clearTimeout(timer)
  try {
    const data = await request<Page<CollectorContract>>('/collectors?limit=20')
    collectors.value = data.items; catalogTotal.value = data.total; catalogPage.value = 1; selectedId.value = data.items[0]?.id
    connected.value = true; await refreshTasks(); void poll(epoch)
  } catch(e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
async function poll(version: number) {
  if (version !== epoch || !connected.value) return
  try {
    if (result.value && !result.value.finished) {
      const id = result.value.execution_id
      const data = await request<CollectorTask>(`/tasks/${id}`)
      if (version === epoch && result.value?.execution_id === id) result.value = data
    }
    if (tasks.value.some(t => !t.finished)) await refreshTasks()
  } catch(e) { error.value = e instanceof Error ? e.message : String(e) }
  if (version === epoch && connected.value) timer = setTimeout(() => poll(version), 2500)
}
async function run() {
  if (!selected.value || running.value) return
  running.value = true; error.value = ''; retryKey ||= crypto.randomUUID()
  const version = epoch
  try {
    const data = await request<CollectorTask>(`/collectors/${selected.value.slug}/runs`, { method: 'POST', headers: { 'Idempotency-Key': retryKey }, body: JSON.stringify({ inputs: inputs.value }) })
    if (version === epoch) { result.value = data; retryKey = ''; page.value = 1; await refreshTasks(); ElMessage.success('采集任务已提交') }
  } catch(e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { running.value = false }
}
async function showTask(id: number) {
  const version = epoch
  try { const task = await request<CollectorTask>(`/tasks/${id}`); if (version === epoch) result.value = task } catch(e) { error.value = e instanceof Error ? e.message : String(e) }
}
onUnmounted(() => { epoch++; clearTimeout(timer) })
</script>
<template>
  <div class="portal"><header><div><BrandIdentity :size="44" /><h1>网页数据采集</h1><p>选择采集接口，提交参数，获取可下载的结构化数据。</p></div><el-button v-if="connected" @click="disconnect()">退出连接</el-button></header>
    <el-alert v-if="error" :title="error" type="error" closable @close="error = ''" />
    <el-card v-if="!connected" class="login"><h2>连接采集服务</h2><p>请输入发布者提供的应用凭证，格式为 App Key.App Secret。</p><el-input v-model="token" type="password" show-password placeholder="fkxxxxxxxx.应用密钥" size="large" @keyup.enter="connect" /><el-button type="primary" size="large" :loading="busy" @click="connect">连接并查看可用接口</el-button><p class="hint">凭证仅保留在当前页面内存中，退出或刷新后需重新输入。</p></el-card>
    <template v-else><div class="workspace"><el-card class="form"><h2>发起采集</h2><el-empty v-if="!catalogTotal" description="暂无已授权的采集接口，请联系发布者授权。" /><template v-else><el-select v-model="selectedId" style="width:100%" placeholder="选择采集接口"><el-option v-for="c in collectors" :key="c.id" :label="c.name" :value="c.id" /></el-select><el-pagination v-if="catalogTotal > 20" v-model:current-page="catalogPage" :total="catalogTotal" :page-size="20" layout="prev, next" @current-change="loadCatalog" /><template v-if="selected"><p>{{ selected.description }}</p><CollectorInputs v-model="inputs" :contract="selected" /><el-button type="primary" :loading="running" @click="run">开始采集</el-button></template></template></el-card><el-card class="result"><CollectorResult v-if="result" :task="result" /><el-empty v-else description="提交采集后在这里查看结果，也可从历史任务中选择。" /></el-card></div>
    <el-card><div class="task-header"><h2>我的采集任务</h2><el-button @click="refreshTasks">刷新</el-button></div><el-table :data="tasks"><el-table-column prop="execution_id" label="任务" width="100" /><el-table-column prop="collector_name" label="采集接口" min-width="180" /><el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">{{ { pending: '排队中', running: '采集中', success: '已完成', failed: '失败' }[row.status as string] }}</el-tag></template></el-table-column><el-table-column label="提交时间" min-width="180"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="120"><template #default="{ row }"><el-button type="primary" link @click="showTask(row.execution_id)">查看结果</el-button></template></el-table-column></el-table><el-pagination v-model:current-page="page" :total="total" :page-size="10" layout="total, prev, pager, next" @current-change="refreshTasks" /></el-card></template>
  </div>
</template>
<style scoped>.portal { max-width:1360px; margin:auto; padding:32px; font-family:system-ui,sans-serif; color:#243247; } header,.task-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px } h1 { font-size:32px; margin:12px 0 } h2 { font-size:18px; margin:0 0 16px } p { color:#7b8798; line-height:1.7 } .login { max-width:520px; margin:60px auto } .login .el-button { width:100%; margin-top:20px } .hint { font-size:12px } .workspace { display:grid; grid-template-columns:340px minmax(0,1fr); gap:24px; margin:24px 0 } .el-pagination { margin-top:20px } .el-alert { margin-bottom:16px } @media(max-width:850px) { .workspace { grid-template-columns:1fr } .portal { padding:20px } }</style>

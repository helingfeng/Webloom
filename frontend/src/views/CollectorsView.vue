<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listScripts } from '@/api/scripts'
import { listOpenApps } from '@/api/openPlatform'
import { listCollectors, saveCollector, getContract, debugCollector, removeCollector, apiError } from '@/api/collectors'
import type { Collector, CollectorDraft, CollectorContract } from '@/types/collector'
import type { Script } from '@/types/script'
import type { OpenApp } from '@/types/openPlatform'
import CollectorInputs from '@/components/CollectorInputs.vue'
import { formatDateTime } from '@/utils/format'
const router = useRouter()
const route = useRoute()
const items = ref<Collector[]>([]), scripts = ref<Script[]>([]), apps = ref<OpenApp[]>([])
const loading = ref(false), saving = ref(false), total = ref(0), page = ref(1)
const removingId = ref<number>()
const editingId = ref<number>(), editing = ref(false), selected = ref<Collector>()
const contract = ref<CollectorContract>(), detail = ref(false), tab = ref('docs'), appId = ref<number>(), inputs = ref<Record<string, unknown>>({})
const form = reactive<CollectorDraft>({ name: '', slug: '', script_id: 0, description: '', app_ids: [], enabled: true })
const baseUrl = ref(window.location.origin)
function shellQuote(value: string) { return "'" + value.replaceAll("'", "'\\''") + "'" }
const curl = computed(() => contract.value ? `curl -X POST ${shellQuote(baseUrl.value.replace(/\/$/, '') + contract.value.path)} \\\n  -H 'Authorization: Bearer <APP_KEY>.<APP_SECRET>' \\\n  -H 'Content-Type: application/json' \\\n  -H 'Idempotency-Key: <每次新采集使用新的唯一键>' \\\n  --data ${shellQuote(JSON.stringify(contract.value.example, null, 2))}` : '')
const python = computed(() => contract.value ? `import os, time, uuid, requests, json\nbase = ${JSON.stringify(baseUrl.value.replace(/\/$/, ''))}\nheaders = {"Authorization": "Bearer " + os.environ["FISHCODE_TOKEN"]}\nresponse = requests.post(base + ${JSON.stringify(contract.value.path)},\n    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},\n    json=${`json.loads(${JSON.stringify(JSON.stringify(contract.value.example))})`}, timeout=30)\nresponse.raise_for_status()\ntask = response.json()\ndeadline = time.monotonic() + 180\nwhile not task["finished"]:\n    if time.monotonic() >= deadline:\n        raise TimeoutError("稍后用 result_url 继续查询：" + task["result_url"])\n    time.sleep(2)\n    response = requests.get(base + task["result_url"], headers=headers, timeout=30)\n    response.raise_for_status()\n    task = response.json()\nif task["status"] != "success":\n    raise RuntimeError(task["error"])\nprint(task["outputs"])` : '')
async function fetchItems() {
  loading.value = true
  try { const r = await listCollectors((page.value - 1) * 20); items.value = r.data.items; total.value = r.data.total }
  catch (e) { ElMessage.error(apiError(e)) } finally { loading.value = false }
}
onMounted(async () => {
  await fetchItems()
  try { const [s, a] = await Promise.all([listScripts(), listOpenApps()]); scripts.value = s.data; apps.value = a.data.items
    const scriptId = Number(route.query.script_id)
    if (scriptId && scripts.value.some(s => s.id === scriptId)) { edit(); form.script_id = scriptId; chooseScript(scriptId) }
  }
  catch (e) { ElMessage.error(apiError(e)) }
})
function edit(item?: Collector) {
  editingId.value = item?.id
  Object.assign(form, item ? { ...item, app_ids: [...item.app_ids] } : { name: '', slug: '', script_id: 0, description: '', app_ids: [], enabled: true })
  editing.value = true
}
function chooseScript(id: number) { const s = scripts.value.find(s => s.id === id); if (s && !form.name) form.name = s.name }
async function save() {
  if (!form.name.trim() || !/^[a-z][a-z0-9-]{1,79}$/.test(form.slug) || !form.script_id || !form.app_ids.length) {
    ElMessage.warning('请填写名称、接口标识、采集脚本，并至少授权一个应用'); return
  }
  saving.value = true
  try { await saveCollector({ ...form }, editingId.value); editing.value = false; ElMessage.success(form.enabled ? '接口已发布' : '已保存为未发布'); await fetchItems() }
  catch (e) { ElMessage.error(apiError(e)) } finally { saving.value = false }
}
async function open(item: Collector) {
  selected.value = item; contract.value = undefined; inputs.value = {}; tab.value = 'docs'; appId.value = item.app_ids.find(id => apps.value.some(a => a.id === id && a.enabled)); detail.value = true
  try { contract.value = (await getContract(item.id)).data; inputs.value = { ...contract.value.example.inputs } }
  catch (e) { ElMessage.error(apiError(e)) }
}
async function run() {
  if (!selected.value || !appId.value) { ElMessage.warning('请选择授权应用'); return }
  saving.value = true
  try { const r = await debugCollector(selected.value.id, appId.value, inputs.value); detail.value = false; await router.push({ path: '/collector-tasks', query: { execution_id: r.data.execution_id } }) }
  catch (e) { ElMessage.error(apiError(e)) } finally { saving.value = false }
}
async function remove(item: Collector) {
  if (removingId.value !== undefined) return
  try {
    await ElMessageBox.confirm(
      `移除「${item.name}」后将从接口列表隐藏，停止新的外部调用。已提交的任务继续执行，历史结果保留；接口标识不会释放。`,
      '移除采集接口',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  removingId.value = item.id
  try {
    await removeCollector(item.id)
    if (selected.value?.id === item.id) detail.value = false
    if (items.value.length === 1 && page.value > 1) page.value--
    ElMessage.success('采集接口已移除，历史任务与结果已保留')
    await fetchItems()
  } catch (e) { ElMessage.error(apiError(e)) }
  finally { removingId.value = undefined }
}
async function copy(value: string) { try { await navigator.clipboard.writeText(value); ElMessage.success('已复制') } catch { ElMessage.error('复制失败，请手动复制') } }
</script>
<template>
  <div>
    <div class="header"><div><h2>采集接口</h2><p>把已验证的脚本发布成接口，让外部系统直接获取结构化数据。</p></div><div><el-button @click="router.push('/collection-portal')">调用体验页</el-button><el-button @click="fetchItems">刷新</el-button><el-button type="primary" @click="edit()">发布采集接口</el-button></div></div>
    <el-alert v-if="!apps.length" title="先创建开放应用获取调用凭证，再选择脚本发布接口。" type="info" :closable="false"><el-button link type="primary" @click="router.push('/open-apps')">创建应用</el-button></el-alert>
    <el-card v-loading="loading">
      <el-empty v-if="!items.length && !loading" description="还没有发布采集接口。选择一个脚本即可开始。"><el-button type="primary" @click="edit()">发布第一个接口</el-button></el-empty>
      <el-table v-else :data="items"><el-table-column label="接口" min-width="200"><template #default="{ row }"><strong>{{ row.name }}</strong><p class="hint">{{ row.description || '暂无说明' }}</p></template></el-table-column><el-table-column label="调用地址" min-width="280"><template #default="{ row }"><el-tag size="small">POST</el-tag> <code>/open/v1/collectors/{{ row.slug }}/runs</code></template></el-table-column><el-table-column label="授权应用" min-width="130"><template #default="{ row }">{{ row.app_ids.map((id: number) => apps.find(a => a.id === id)?.name ?? `#${id}`).join('、') }}</template></el-table-column><el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '已发布' : '未发布' }}</el-tag></template></el-table-column><el-table-column label="更新" width="165"><template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template></el-table-column><el-table-column label="操作" width="300" fixed="right"><template #default="{ row }"><el-button size="small" type="primary" plain @click="open(row)">接入 / 调试</el-button><el-button size="small" @click="edit(row)">编辑</el-button><el-button size="small" type="danger" plain :loading="removingId === row.id" :disabled="removingId !== undefined" @click="remove(row)">移除</el-button></template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="fetchItems" />
    </el-card>
    <el-dialog v-model="editing" :title="editingId ? '编辑采集接口' : '发布采集接口'" width="620px">
      <el-form label-position="top"><el-form-item label="采集脚本" required><el-select v-model="form.script_id" filterable placeholder="选择已验证的采集脚本" style="width:100%" @change="chooseScript"><el-option v-for="s in scripts" :key="s.id" :value="s.id" :label="`${s.name} (#${s.id})`" /></el-select></el-form-item><el-form-item label="接口名称" required><el-input v-model="form.name" maxlength="255" /></el-form-item><el-form-item label="接口标识" required><el-input v-model="form.slug" :disabled="!!editingId" placeholder="例如 product-search，发布后保持不变" /><div class="hint">2–80 位小写字母、数字或短横线，以字母开头。</div></el-form-item><el-form-item label="接口说明"><el-input v-model="form.description" type="textarea" placeholder="说明采集内容、适用页面、预计耗时及使用方式" /></el-form-item><el-form-item label="授权应用" required><el-select v-model="form.app_ids" multiple style="width:100%" placeholder="仅勾选的应用可调用"><el-option v-for="a in apps" :key="a.id" :value="a.id" :label="a.name + (a.enabled ? '' : '（已停用）')" /></el-select></el-form-item><el-form-item label="发布状态"><el-switch v-model="form.enabled" active-text="发布后可被授权应用调用" /></el-form-item></el-form><template #footer><el-button @click="editing = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">{{ form.enabled ? '保存并发布' : '保存' }}</el-button></template>
    </el-dialog>
    <el-drawer v-model="detail" title="接入与调试" size="min(800px, 95vw)">
      <template v-if="contract && selected"><h2>{{ contract.name }}</h2><p>{{ contract.description }}</p><el-tabs v-model="tab"><el-tab-pane name="docs" label="调用说明"><el-form label-position="top"><el-form-item label="外部访问地址"><el-input v-model="baseUrl" placeholder="填写调用方可访问的服务地址" /></el-form-item></el-form><p>凭证格式：<code>{{ contract.auth }}</code>，在开放应用中查看凭证。脚本更新会同步影响此接口。</p><h4>输入参数</h4><el-table :data="Object.entries(contract.input_schema.properties).map(([name, prop]) => ({ name, ...prop, required: contract!.input_schema.required.includes(name) }))" border><el-table-column prop="name" label="参数" /><el-table-column prop="type" label="类型" width="100" /><el-table-column label="必填" width="70"><template #default="{ row }">{{ row.required ? '是' : '否' }}</template></el-table-column><el-table-column prop="description" label="说明" /></el-table><h4>输出字段</h4><el-table :data="contract.outputs" border empty-text="脚本尚未声明输出字段，运行后可在任务结果中查看实际数据"><el-table-column prop="name" label="字段" /><el-table-column prop="description" label="说明" /></el-table><h4>cURL <el-button link type="primary" @click="copy(curl)">复制</el-button></h4><pre>{{ curl }}</pre><h4>Python <el-button link type="primary" @click="copy(python)">复制</el-button></h4><pre>{{ python }}</pre><el-alert title="返回 202 表示已受理，按 result_url 查询直到 finished=true；success 才表示采集成功。相同幂等键和参数不会重复创建任务。数据支持按字段分页读取和 CSV 下载。" type="info" :closable="false" /><pre>GET /open/v1/tasks/{execution_id}
GET /open/v1/tasks/{execution_id}/data?field=items&amp;skip=0&amp;limit=100
GET /open/v1/tasks/{execution_id}/data?field=items&amp;format=csv</pre></el-tab-pane><el-tab-pane name="debug" label="在线调试"><el-alert title="调试会创建真实采集任务，可在采集任务中查看结果。" :closable="false" type="info" /><el-form label-position="top"><el-form-item label="以授权应用调用"><el-select v-model="appId"><el-option v-for="a in apps.filter(a => selected!.app_ids.includes(a.id) && a.enabled)" :key="a.id" :value="a.id" :label="a.name" /></el-select></el-form-item></el-form><CollectorInputs v-model="inputs" :contract="contract" /><el-button type="primary" :disabled="!selected.enabled" :loading="saving" @click="run">发起采集并查看结果</el-button></el-tab-pane></el-tabs></template>
    </el-drawer>
  </div>
</template>
<style scoped>.header { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:20px; flex-wrap:wrap } h2 { margin:0 0 8px } p,.hint { color:#909399; font-size:13px } pre { background:#f6f8fa; padding:16px; white-space:pre-wrap; overflow-wrap:anywhere; } .el-pagination { margin-top:20px } .el-alert { margin-bottom:16px } </style>

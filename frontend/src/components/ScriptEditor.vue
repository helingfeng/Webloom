<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { ScriptCreate, VariableDefinition, OutputDefinition } from '@/types/script'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import ParameterValue from './ParameterValue.vue'
import RecordDialog from './RecordDialog.vue'
import CodeEditor from './CodeEditor.vue'
const props = defineProps<{ initialData?: ScriptCreate; running?: boolean; saving?: boolean }>()
const emit = defineEmits<{
  save: [data: ScriptCreate]
  cancel: []
  run: [data: { script: ScriptCreate; mode: 'manual'; inputs: Record<string, unknown>; headless: boolean }]
}>()
const wsStore = useWorkspaceStore()
const empty = (): ScriptCreate => ({ workspace_id: 0, name: '', description: '', start_url: '', inputs: [], outputs: [], code: '', inherit_global: true, run_mode: 'manual', headless: true })
const form = ref<ScriptCreate>(empty())
const runInputs = ref<Record<string, unknown>>({})
const activeTab = ref('code')
const recordDialogRef = ref<InstanceType<typeof RecordDialog> | null>(null)
const types: { value: VariableDefinition['type']; label: string }[] = [
  { value: 'string', label: '字符串' }, { value: 'number', label: '数字' }, { value: 'boolean', label: '布尔值' },
  { value: 'secret', label: '密码 / 密钥' }, { value: 'header', label: '请求头 Header' }, { value: 'cookie', label: '登录 Cookie' }, { value: 'localStorage', label: '登录 localStorage' },
]
watch(() => props.initialData, (value, old) => {
  if (!value) return
  if ((old as { id?: number })?.id === undefined || (old as { id?: number })?.id !== (value as { id?: number }).id) {
    form.value = { ...empty(), ...JSON.parse(JSON.stringify(value)), run_mode: 'manual' }
    form.value.inputs?.forEach(input => {
      if (input.type === 'number' && typeof input.default === 'string') input.default = Number(input.default)
      if (input.type === 'boolean' && typeof input.default === 'string') input.default = input.default.toLowerCase() === 'true'
    })
    runInputs.value = {}
  }
}, { immediate: true })
const inputs = computed(() => form.value.inputs ?? [])
const outputs = computed(() => form.value.outputs ?? [])
function addInput() { (form.value.inputs ??= []).push({ name: '', type: 'string', required: true, description: '' }) }
function addOutput() { (form.value.outputs ??= []).push({ name: '', description: '' }) }
function hasDefault(row: VariableDefinition) { return row.default !== undefined && row.default !== null }
function toggleDefault(row: VariableDefinition, enabled: unknown) {
  row.default = enabled ? row.type === 'boolean' ? false : row.type === 'number' ? 0 : '' : undefined
}
function changeType(row: VariableDefinition) { row.default = undefined; delete runInputs.value[row.name] }
function payload(): ScriptCreate {
  return JSON.parse(JSON.stringify({ ...form.value, name: form.value.name.trim(), start_url: form.value.start_url?.trim(), run_mode: 'manual', inputs: inputs.value.map(i => ({ ...i, name: i.name.trim() })), outputs: outputs.value.map(o => ({ ...o, name: o.name.trim() })) }))
}
function valid() {
  if (!form.value.name.trim() || !form.value.workspace_id) { activeTab.value = 'basic'; ElMessage.warning('请填写脚本名称并选择项目空间'); return false }
  return true
}
function save() { if (valid()) emit('save', payload()) }
function run() {
  if (!valid()) return
  const values = Object.fromEntries(inputs.value.filter(i => runInputs.value[i.name] !== undefined).map(i => [i.name.trim(), runInputs.value[i.name]]))
  emit('run', { script: payload(), mode: 'manual', inputs: values, headless: form.value.headless ?? true })
}
function applyRecorded(data: { code: string; start_url: string }) { form.value.code = data.code; if (data.start_url) form.value.start_url = data.start_url; activeTab.value = 'code' }
function defaultHint(input: VariableDefinition) {
  if (!hasDefault(input)) return '未指定；必填参数需提供值'
  return ['secret', 'header', 'cookie', 'localStorage'].includes(input.type) ? '已配置默认值，留空使用默认值' : `默认：${String(input.default)}`
}
</script>
<template>
  <div>
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="脚本信息" name="basic">
        <el-form label-width="120px">
          <el-form-item label="脚本名称" required><el-input v-model="form.name" maxlength="255" placeholder="描述此脚本采集的内容" /></el-form-item>
          <el-form-item label="所属空间" required><el-select v-model="form.workspace_id"><el-option v-for="ws in wsStore.workspaces" :key="ws.id" :label="ws.name" :value="ws.id" /></el-select></el-form-item>
          <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
          <el-form-item label="默认页面 URL"><el-input v-model="form.start_url" placeholder="https://example.com，可留空由代码自行导航" /><div class="hint">提供名为 url 的运行参数时，START_URL 与域名登录态匹配都以该参数为准；否则使用此默认地址。</div></el-form-item>
          <el-form-item label="继承全局配置"><el-switch v-model="form.inherit_global" /><div class="hint">加载匹配目标域名的请求头、Cookie、localStorage 和 GLOBAL_VARS。输入参数中的同名浏览器配置优先。</div></el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="输入参数" name="inputs">
        <el-button type="primary" size="small" @click="addInput">添加参数</el-button>
        <p class="hint">参数名与 INPUTS 的键一致，不可重复。Header / Cookie / localStorage 参数按名称注入浏览器。默认值在前端、MCP 和外部接口中统一生效。</p>
        <el-table :data="inputs">
          <el-table-column label="参数名" min-width="150"><template #default="{ row }"><el-input v-model="row.name" placeholder="url / max_pages" /></template></el-table-column>
          <el-table-column label="类型" width="170"><template #default="{ row }"><el-select v-model="row.type" @change="changeType(row)"><el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" /></el-select></template></el-table-column>
          <el-table-column label="说明" min-width="170"><template #default="{ row }"><el-input v-model="row.description" placeholder="面向调用方的参数说明" /></template></el-table-column>
          <el-table-column label="默认值" min-width="230"><template #default="{ row }"><el-checkbox :model-value="hasDefault(row)" @change="(v: unknown) => toggleDefault(row, v)">设置默认值</el-checkbox><ParameterValue v-if="hasDefault(row)" v-model="row.default" :definition="row" placeholder="默认值" /></template></el-table-column>
          <el-table-column label="必填" width="80"><template #default="{ row }"><el-checkbox v-model="row.required" /></template></el-table-column>
          <el-table-column label="操作" width="80"><template #default="{ $index }"><el-button size="small" type="danger" @click="form.inputs?.splice($index, 1)">删除</el-button></template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="输出字段" name="outputs">
        <el-button type="primary" size="small" @click="addOutput">添加输出字段</el-button>
        <p class="hint">字段名应对应 OUTPUTS 的键，用于生成接口文档；数据可为列表、对象或标量。</p>
        <el-table :data="outputs"><el-table-column label="字段名"><template #default="{ row }"><el-input v-model="row.name" placeholder="items" /></template></el-table-column><el-table-column label="说明"><template #default="{ row }"><el-input v-model="row.description" placeholder="例如商品名称、价格与链接列表" /></template></el-table-column><el-table-column label="操作" width="80"><template #default="{ $index }"><el-button type="danger" size="small" @click="form.outputs?.splice($index, 1)">删除</el-button></template></el-table-column></el-table>
      </el-tab-pane>
      <el-tab-pane label="脚本代码" name="code">
        <div class="toolbar"><el-button size="small" @click="recordDialogRef?.open(form.start_url || '')">录制操作</el-button><span class="hint">代码在 async main() 内执行，可使用 page、INPUTS、OUTPUTS、START_URL、GLOBAL_VARS、DATA_VIEWS 和 expect。将结果写入 OUTPUTS。</span></div>
        <CodeEditor v-model="form.code" />
      </el-tab-pane>
      <el-tab-pane label="调试运行" name="run">
        <el-alert title="运行前自动保存当前脚本；参数留空时使用默认值。调试参数不会作为默认值保存。" type="info" :closable="false" />
        <el-form label-position="top" class="run-form">
          <el-form-item label="浏览器显示方式"><el-switch v-model="form.headless" active-text="后台运行" inactive-text="显示浏览器窗口" /></el-form-item>
          <el-form-item v-for="input in inputs" :key="input.name" :label="input.name" :required="input.required && !hasDefault(input)"><ParameterValue v-model="runInputs[input.name]" :definition="input" :placeholder="defaultHint(input)" /><div class="hint">{{ input.description }}</div></el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
    <div class="actions"><el-button type="primary" :loading="saving" :disabled="running" @click="save">保存脚本</el-button><el-button type="success" :loading="running" :disabled="saving" @click="run">保存并运行</el-button><el-button @click="emit('cancel')">返回列表</el-button></div>
    <RecordDialog ref="recordDialogRef" @apply="applyRecorded" />
  </div>
</template>
<style scoped>.hint { color:#909399;font-size:12px;line-height:1.8;width:100%; } .toolbar { display:flex;align-items:center;gap:16px;margin-bottom:12px; } .actions { margin-top:20px; } .run-form { max-width:640px;margin-top:20px; }</style>

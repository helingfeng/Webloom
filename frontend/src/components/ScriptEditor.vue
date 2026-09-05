<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ScriptCreate, VariableDefinition, OutputDefinition } from '@/types/script'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import RecordDialog from './RecordDialog.vue'
import CodeEditor from './CodeEditor.vue'

const props = defineProps<{
  initialData?: ScriptCreate
  running?: boolean
}>()

const emit = defineEmits<{
  save: [data: ScriptCreate]
  cancel: []
  run: [data: { mode: 'manual' | 'mock'; inputs: Record<string, any>; headless?: boolean }]
}>()

const wsStore = useWorkspaceStore()

const form = ref<ScriptCreate>({
  workspace_id: 0,
  name: '',
  description: '',
  start_url: '',
  inputs: [],
  outputs: [],
  code: '',
  inherit_global: true,
  run_mode: 'manual',
  headless: true,
})

watch(
  () => props.initialData,
  (val, oldVal) => {
    if (!val) return
    // 仅在加载了另一个脚本实体时重置表单（如新建保存后跳转编辑页），
    // 不做深度监听——否则保存后 store 刷新会覆盖用户当前编辑内容
    const oldId = (oldVal as any)?.id
    if (oldId === undefined || oldId !== (val as any).id) {
      form.value = JSON.parse(JSON.stringify(val))
      // 老数据可能缺失运行配置字段，回退默认值保证控件可用
      if (!form.value.run_mode) form.value.run_mode = 'manual'
      if (form.value.headless === undefined) form.value.headless = true
    }
  },
  { immediate: true }
)

const activeTab = ref('basic')
const runInputs = ref<Record<string, any>>({})
const recordDialogRef = ref<InstanceType<typeof RecordDialog> | null>(null)

const inputTypeOptions = [
  { label: '字符串', value: 'string' },
  { label: '数字', value: 'number' },
  { label: '布尔值', value: 'boolean' },
  { label: '密码/密钥', value: 'secret' },
  { label: '请求头 Header', value: 'header' },
  { label: 'Cookie', value: 'cookie' },
  { label: 'LocalStorage', value: 'localStorage' },
]

const inputs = computed<VariableDefinition[]>({
  get: () => form.value.inputs || [],
  set: (val) => { form.value.inputs = val },
})

const outputs = computed<OutputDefinition[]>({
  get: () => form.value.outputs || [],
  set: (val) => { form.value.outputs = val },
})

const generatedInputs = computed(() => {
  const result: Record<string, any> = {}
  inputs.value.forEach((input) => {
    result[input.name] = runInputs.value[input.name] ?? input.default ?? ''
  })
  return result
})

function addInput() {
  form.value.inputs = form.value.inputs || []
  form.value.inputs.push({
    name: '',
    type: 'string',
    description: '',
    required: true,
  })
}

function removeInput(index: number) {
  form.value.inputs?.splice(index, 1)
}

function addOutput() {
  form.value.outputs = form.value.outputs || []
  form.value.outputs.push({
    name: '',
    description: '',
  })
}

function removeOutput(index: number) {
  form.value.outputs?.splice(index, 1)
}

function handleSave() {
  emit('save', form.value)
}

function handleRun() {
  emit('run', {
    mode: form.value.run_mode || 'manual',
    inputs: form.value.run_mode === 'manual' ? generatedInputs.value : {},
    headless: form.value.headless,
  })
}

function applyRecorded(data: { code: string; start_url: string }) {
  form.value.code = data.code
  if (data.start_url) {
    form.value.start_url = data.start_url
  }
  activeTab.value = 'code'
}
</script>

<template>
  <div>
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="基本信息" name="basic">
        <el-form :model="form" label-width="100px">
          <el-form-item label="脚本名称" required>
            <el-input v-model="form.name" placeholder="请输入脚本名称" />
          </el-form-item>
          <el-form-item label="所属空间" required>
            <el-select
              v-model="form.workspace_id"
              placeholder="选择项目空间"
              style="max-width: 320px"
            >
              <el-option
                v-for="ws in wsStore.workspaces"
                :key="ws.id"
                :label="ws.name"
                :value="ws.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" rows="2" placeholder="请输入描述" />
          </el-form-item>
          <el-form-item label="起始 URL">
            <el-input v-model="form.start_url" placeholder="例如：https://example.com/login" />
          </el-form-item>
          <el-form-item label="继承全局变量">
            <el-switch v-model="form.inherit_global" />
            <span class="inherit-hint">
              开启后执行时自动携带全局变量中启用的公共 Header（GLOBAL_HEADERS）、注入 GLOBAL_VARS，并在访问起始 URL 前自动写入 GLOBAL_LOCAL_STORAGE 登录态
            </span>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="输入变量" name="inputs">
        <el-button type="primary" size="small" @click="addInput">
          <el-icon><Plus /></el-icon> 添加变量
        </el-button>
        <span class="code-hint browser-input-hint">
          类型为 Header / Cookie / LocalStorage 的变量按变量名注入浏览器，运行时覆盖全局变量中的同名项（Cookie 的域取脚本起始 URL）
        </span>
        <el-table :data="inputs" style="width: 100%; margin-top: 15px">
          <el-table-column label="变量名" width="150">
            <template #default="{ row }">
              <el-input v-model="row.name" placeholder="username" />
            </template>
          </el-table-column>
          <el-table-column label="类型" width="150">
            <template #default="{ row }">
              <el-select v-model="row.type" style="width: 100%">
                <el-option
                  v-for="opt in inputTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="描述">
            <template #default="{ row }">
              <el-input v-model="row.description" placeholder="描述" />
            </template>
          </el-table-column>
          <el-table-column label="默认值">
            <template #default="{ row }">
              <el-input v-model="row.default" placeholder="默认值" />
            </template>
          </el-table-column>
          <el-table-column label="必填" width="80">
            <template #default="{ row }">
              <el-checkbox v-model="row.required" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button type="danger" size="small" @click="removeInput($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="输出结果" name="outputs">
        <el-button type="primary" size="small" @click="addOutput">
          <el-icon><Plus /></el-icon> 添加输出
        </el-button>
        <el-table :data="outputs" style="width: 100%; margin-top: 15px">
          <el-table-column label="输出名">
            <template #default="{ row }">
              <el-input v-model="row.name" placeholder="cookies" />
            </template>
          </el-table-column>
          <el-table-column label="描述">
            <template #default="{ row }">
              <el-input v-model="row.description" placeholder="描述" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button type="danger" size="small" @click="removeOutput($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="脚本代码" name="code">
        <div class="code-toolbar">
          <el-button type="danger" size="small" @click="recordDialogRef?.open(form.start_url || '')">
            录制脚本
          </el-button>
          <span class="code-hint">
            可用对象：INPUTS（输入变量）、OUTPUTS（输出结果）、GLOBAL_HEADERS（全局 Header）、GLOBAL_VARS（全局变量）、GLOBAL_LOCAL_STORAGE（全局 localStorage）、DATA_VIEWS（数据视图，如 DATA_VIEWS["users-list"] 取行列表，每行为 {列名: 值}）、DATA_VIEWS_ONE（单行便捷访问，如 DATA_VIEWS_ONE["users-list"] 取首行对象，空结果为 None）、START_URL（起始 URL）、page / context / browser（Playwright 对象）；断言可直接用 expect（已导入）与 assert
          </span>
        </div>
        <CodeEditor v-model="form.code" />
      </el-tab-pane>

      <el-tab-pane label="运行配置" name="run">
        <el-form :model="form" label-width="100px">
          <el-form-item label="运行模式">
            <el-radio-group v-model="form.run_mode">
              <el-radio value="manual">手动输入</el-radio>
              <el-radio value="mock">自动 Mock</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="无窗口模式">
            <el-switch v-model="form.headless" />
            <span class="inherit-hint">
              开启后浏览器在后台运行（默认）；关闭可弹出浏览器窗口，便于观察实际操作过程；保存脚本后作为该脚本的运行配置
            </span>
          </el-form-item>
          <template v-if="form.run_mode === 'manual'">
            <el-form-item
              v-for="input in inputs"
              :key="input.name"
              :label="input.name"
            >
              <el-input
                v-if="input.type === 'secret'"
                v-model="runInputs[input.name]"
                type="password"
                :placeholder="input.description"
              />
              <el-input
                v-else-if="input.type === 'boolean'"
                v-model="runInputs[input.name]"
                placeholder="true/false"
              />
              <el-input
                v-else
                v-model="runInputs[input.name]"
                :placeholder="
                  ['header', 'cookie', 'localStorage'].includes(input.type)
                    ? `${input.description || '注入值'}（覆盖全局同名项）`
                    : input.description
                "
              />
            </el-form-item>
          </template>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <div class="form-actions">
      <el-button type="primary" @click="handleSave">保存脚本</el-button>
      <el-button type="success" :loading="running" @click="handleRun">运行脚本</el-button>
      <el-button @click="emit('cancel')">取消</el-button>
    </div>

    <RecordDialog ref="recordDialogRef" @apply="applyRecorded" />
  </div>
</template>

<style scoped>
.code-toolbar {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 15px;
}

.code-hint {
  color: #666;
  font-size: 13px;
}

.inherit-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 10px;
}

.browser-input-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 10px;
}

.form-actions {
  margin-top: 20px;
}
</style>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { VueFlow, useVueFlow, Handle, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useScriptStore } from '@/stores/scriptStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { FlowCreate, FlowNode, FlowEdge } from '@/types/flow'

const props = defineProps<{
  initialData?: FlowCreate
  running?: boolean
}>()

const emit = defineEmits<{
  save: [data: FlowCreate]
  cancel: []
  run: [data: { mode: 'manual' | 'mock'; global_inputs: Record<string, any> }]
}>()

const scriptStore = useScriptStore()
const wsStore = useWorkspaceStore()
const { onConnect, onNodeClick, updateNode, removeNodes, screenToFlowCoordinate } = useVueFlow()

const nodes = ref<FlowNode[]>([])
const edges = ref<FlowEdge[]>([])
const formRef = ref<FormInstance>()
const form = ref({ name: '', description: '' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入流程名称', trigger: 'blur' }],
}
const workspaceId = ref<number | null>(null)
const runMode = ref<'manual' | 'mock'>('manual')
const globalInputsJson = ref('')

const configDialogVisible = ref(false)
const selectedNode = ref<FlowNode | null>(null)
const selectedNodeInputMapping = ref<Record<string, string>>({})

watch(
  () => props.initialData,
  (val) => {
    if (val) {
      form.value.name = val.name || ''
      form.value.description = val.description || ''
      workspaceId.value = val.workspace_id ?? wsStore.currentWorkspaceId ?? null
      runMode.value = val.run_mode ?? 'manual'
      const gi = val.global_inputs
      globalInputsJson.value = gi && Object.keys(gi).length ? JSON.stringify(gi, null, 2) : ''
      nodes.value = val.nodes?.length ? val.nodes.map(cleanNode) : [
        { id: 'start', type: 'start', position: { x: 50, y: 150 }, data: { label: '开始' } },
        { id: 'end', type: 'end', position: { x: 600, y: 150 }, data: { label: '结束' } },
      ]
      edges.value = val.edges?.length ? val.edges.map(cleanEdge) : []
    }
  },
  { immediate: true, deep: true }
)

// 保存/加载时只保留业务字段，剥离 Vue Flow 运行时状态（handleBounds、
// computedPosition、sourceNode 等）。历史数据中 start 节点存过
// "handleBounds": {"source": null}，Vue Flow 加载后会认为节点无连接点，
// 导致连线消失且无法再连接。
function cleanNode(node: FlowNode): FlowNode {
  return {
    id: node.id,
    type: node.type,
    position: { x: node.position.x, y: node.position.y },
    data: node.data ? JSON.parse(JSON.stringify(node.data)) : {},
  }
}

function cleanEdge(edge: FlowEdge): FlowEdge {
  return { id: edge.id, source: edge.source, target: edge.target }
}

onMounted(() => {
  scriptStore.fetchScripts()
})

onConnect((connection) => {
  // v-model:edges 双向绑定，直接 push 即可，无需再调 addEdges（会重复）
  edges.value.push({
    id: `e-${connection.source}-${connection.target}-${Date.now()}`,
    source: connection.source as string,
    target: connection.target as string,
  })
})

onNodeClick(({ node }) => {
  if (node.type === 'script') {
    selectedNode.value = node as FlowNode
    selectedNodeInputMapping.value = { ...(node.data?.input_mapping || {}) }
    configDialogVisible.value = true
  }
})

function onDragStart(event: DragEvent, script: any) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/json', JSON.stringify(script))
    event.dataTransfer.effectAllowed = 'move'
  }
}

function onDrop(event: DragEvent) {
  const data = event.dataTransfer?.getData('application/json')
  if (!data) return
  const script = JSON.parse(data)
  // 屏幕坐标转画布坐标，保证落点与鼠标位置一致
  const position = screenToFlowCoordinate({
    x: event.clientX,
    y: event.clientY,
  })
  const nodeId = `script-${Date.now()}`
  const newNode: FlowNode = {
    id: nodeId,
    type: 'script',
    position,
    data: {
      script_id: script.id,
      label: script.name,
      input_mapping: {},
    },
  }
  nodes.value.push(newNode)
}

function saveNodeConfig() {
  if (!selectedNode.value) return
  selectedNode.value.data.input_mapping = { ...selectedNodeInputMapping.value }
  updateNode(selectedNode.value.id, { data: selectedNode.value.data })
  configDialogVisible.value = false
}

function removeSelectedNode() {
  if (!selectedNode.value) return
  nodes.value = nodes.value.filter((n) => n.id !== selectedNode.value?.id)
  removeNodes([selectedNode.value.id])
  configDialogVisible.value = false
}

function getScriptName(scriptId?: number) {
  const script = scriptStore.scripts.find((s) => s.id === scriptId)
  return script?.name || `脚本 #${scriptId}`
}

function collectGlobalInputs(): Record<string, any> | null {
  if (runMode.value !== 'manual' || !globalInputsJson.value.trim()) return {}
  try {
    return JSON.parse(globalInputsJson.value)
  } catch {
    ElMessage.warning('全局输入不是合法 JSON，请修正后再保存/运行')
    return null
  }
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const globalInputs = collectGlobalInputs()
  if (globalInputs === null) return
  emit('save', {
    workspace_id: workspaceId.value ?? 0,
    name: form.value.name,
    description: form.value.description,
    run_mode: runMode.value,
    global_inputs: globalInputs,
    nodes: nodes.value.map(cleanNode),
    edges: edges.value.map(cleanEdge),
  })
}

function handleRun() {
  const globalInputs = collectGlobalInputs()
  if (globalInputs === null) return
  emit('run', {
    mode: runMode.value,
    global_inputs: globalInputs,
  })
}
</script>

<template>
  <div>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="流程名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入流程名称" />
      </el-form-item>
      <el-form-item label="所属空间">
        <el-select v-model="workspaceId" placeholder="选择项目空间" style="max-width: 320px">
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
    </el-form>

    <div class="flow-layout">
      <div class="script-panel">
        <h4>可用脚本</h4>
        <p class="panel-hint">拖拽脚本到右侧画布</p>
        <div
          v-for="script in scriptStore.scripts"
          :key="script.id"
          class="script-item"
          draggable="true"
          @dragstart="onDragStart($event, script)"
        >
          {{ script.name }}
        </div>
      </div>

      <div class="flow-canvas" @drop="onDrop" @dragover.prevent>
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" fit-view-on-init>
          <Background pattern-color="#aaa" :gap="16" />
          <Controls />

          <template #node-start="slotProps">
            <div class="node-start">{{ slotProps.data.label }}
              <Handle type="source" :position="Position.Right" />
            </div>
          </template>

          <template #node-script="slotProps">
            <div class="node-script">
              <Handle type="target" :position="Position.Left" />
              <div class="node-title">{{ slotProps.data.label }}</div>
              <div class="node-subtitle">{{ getScriptName(slotProps.data.script_id) }}</div>
              <Handle type="source" :position="Position.Right" />
            </div>
          </template>

          <template #node-end="slotProps">
            <div class="node-end">{{ slotProps.data.label }}
              <Handle type="target" :position="Position.Left" />
            </div>
          </template>
        </VueFlow>
      </div>
    </div>

    <el-card class="run-config">
      <template #header>
        <span>运行配置</span>
      </template>
      <el-form label-width="100px">
        <el-form-item label="运行模式">
          <el-radio-group v-model="runMode">
            <el-radio label="manual">手动输入全局变量</el-radio>
            <el-radio label="mock">自动 Mock</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="runMode === 'manual'" label="全局输入">
          <el-input
            v-model="globalInputsJson"
            type="textarea"
            rows="3"
            placeholder='{"username":"admin","password":"123456"}'
          />
        </el-form-item>
      </el-form>
    </el-card>

    <div class="form-actions">
      <el-button type="primary" @click="handleSave">保存流程</el-button>
      <el-button type="success" :loading="running" @click="handleRun">运行流程</el-button>
      <el-button @click="emit('cancel')">取消</el-button>
    </div>

    <el-dialog v-model="configDialogVisible" title="节点配置" width="500px">
      <div v-if="selectedNode">
        <p><strong>节点：</strong>{{ selectedNode.data.label }}</p>
        <p><strong>脚本：</strong>{{ getScriptName(selectedNode.data.script_id) }}</p>

        <h4 style="margin-top: 20px">输入变量映射</h4>
        <p class="hint">
          留空表示使用脚本默认值或 Mock。可使用
          <span v-pre>{{global.xxx}}</span>
          引用全局输入，
          <span v-pre>{{node_xxx.xxx}}</span>
          引用上游节点输出。
        </p>
        <el-form label-width="140px">
          <template
            v-for="script in scriptStore.scripts.filter(s => s.id === selectedNode?.data.script_id)"
            :key="script.id"
          >
            <el-form-item
              v-for="input in script.inputs"
              :key="input.name"
              :label="`${input.name}：`"
            >
              <el-input
                v-model="selectedNodeInputMapping[input.name]"
                :placeholder="input.description"
              />
            </el-form-item>
          </template>
        </el-form>
      </div>
      <template #footer>
        <el-button type="danger" @click="removeSelectedNode">删除节点</el-button>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveNodeConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.flow-layout {
  display: flex;
  height: 500px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  margin-bottom: 20px;
}

.script-panel {
  width: 220px;
  background-color: #f5f7fa;
  padding: 15px;
  border-right: 1px solid #dcdfe6;
  overflow-y: auto;
}

.script-panel h4 {
  margin: 0 0 10px 0;
}

.panel-hint {
  color: #909399;
  font-size: 12px;
  margin-bottom: 15px;
}

.script-item {
  background-color: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 10px;
  cursor: move;
  font-size: 13px;
}

.script-item:hover {
  border-color: #409eff;
  color: #409eff;
}

.flow-canvas {
  flex: 1;
  position: relative;
}

.node-start, .node-end {
  width: 80px;
  height: 40px;
  line-height: 40px;
  text-align: center;
  border-radius: 20px;
  color: #fff;
  font-size: 14px;
}

.node-start {
  background-color: #67c23a;
}

.node-end {
  background-color: #f56c6c;
}

/* 连接点样式：小圆点悬浮在节点左右两侧 */
.node-start :deep(.vue-flow__handle),
.node-script :deep(.vue-flow__handle),
.node-end :deep(.vue-flow__handle) {
  width: 10px;
  height: 10px;
  background-color: #409eff;
  border: 2px solid #fff;
}

.node-script {
  width: 160px;
  background-color: #fff;
  border: 2px solid #409eff;
  border-radius: 4px;
  padding: 10px;
  text-align: center;
}

.node-title {
  font-weight: bold;
  color: #303133;
}

.node-subtitle {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.run-config {
  margin-bottom: 20px;
}

.form-actions {
  margin-top: 20px;
}

.hint {
  color: #909399;
  font-size: 12px;
  margin-bottom: 15px;
}
</style>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTestCaseStore } from '@/stores/testCaseStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { formatDateTime } from '@/utils/format'
import { buildRequirementMindmap } from '@/utils/markdownCases'
import type { CaseStatus, MindmapNode, TestCase } from '@/types/testCase'
import { CASE_STATUS_OPTIONS, statusLabel } from '@/types/testCase'
import MindMapDialog from '@/components/MindMapDialog.vue'
import TestCaseImportDialog from '@/components/TestCaseImportDialog.vue'

const caseStore = useTestCaseStore()
const wsStore = useWorkspaceStore()

// ---------- 左侧树：维度与过滤 ----------
type NodeType = 'all' | 'workspace' | 'requirement' | 'module'
interface TreeNodeData {
  key: string
  type: NodeType
  id?: number
  label: string
  children?: TreeNodeData[]
}

const dimension = ref<'workspace' | 'requirement'>('workspace')
const filter = ref<{ type: NodeType; id: number | null }>({ type: 'all', id: null })
const currentNodeKey = ref('all')
const statusFilter = ref<CaseStatus | ''>('')

function caseCountOfRequirement(reqId: number): number {
  return caseStore.cases.filter((c) => c.requirement_id === reqId).length
}

function caseCountOfModule(modId: number): number {
  return caseStore.cases.filter((c) => c.module_id === modId).length
}

function moduleChildren(reqId: number): TreeNodeData[] {
  return caseStore.modules
    .filter((m) => m.requirement_id === reqId)
    .map((m) => ({
      key: `mod:${m.id}`,
      type: 'module' as NodeType,
      id: m.id,
      label: `${m.name}（${caseCountOfModule(m.id)}）`,
    }))
}

const treeData = computed<TreeNodeData[]>(() => {
  const allNode: TreeNodeData = {
    key: 'all',
    type: 'all',
    label: `全部用例（${caseStore.cases.length}）`,
  }
  if (dimension.value === 'workspace') {
    allNode.children = wsStore.workspaces.map((ws) => {
      const reqs = caseStore.requirements.filter((r) => r.workspace_id === ws.id)
      const count = reqs.reduce((n, r) => n + caseCountOfRequirement(r.id), 0)
      return {
        key: `ws:${ws.id}`,
        type: 'workspace' as NodeType,
        id: ws.id,
        label: `${ws.name}（${count}）`,
        children: reqs.map((r) => ({
          key: `req:${r.id}`,
          type: 'requirement' as NodeType,
          id: r.id,
          label: `${r.name}（${caseCountOfRequirement(r.id)}）`,
          children: moduleChildren(r.id),
        })),
      }
    })
  } else {
    allNode.children = caseStore.requirements.map((r) => {
      const wsName = wsStore.workspaces.find((w) => w.id === r.workspace_id)?.name ?? '未知空间'
      return {
        key: `req:${r.id}`,
        type: 'requirement' as NodeType,
        id: r.id,
        label: `${r.name}（${wsName}，${caseCountOfRequirement(r.id)}）`,
        children: moduleChildren(r.id),
      }
    })
  }
  return [allNode]
})

function handleDimensionChange() {
  filter.value = { type: 'all', id: null }
  currentNodeKey.value = 'all'
}

function handleNodeClick(data: TreeNodeData) {
  filter.value = { type: data.type, id: data.id ?? null }
  currentNodeKey.value = data.key
}

const filteredCases = computed(() => {
  let list = caseStore.cases
  const f = filter.value
  if (f.type === 'workspace') {
    const reqIds = new Set(
      caseStore.requirements.filter((r) => r.workspace_id === f.id).map((r) => r.id),
    )
    list = list.filter((c) => reqIds.has(c.requirement_id))
  } else if (f.type === 'requirement') {
    list = list.filter((c) => c.requirement_id === f.id)
  } else if (f.type === 'module') {
    list = list.filter((c) => c.module_id === f.id)
  }
  if (statusFilter.value) list = list.filter((c) => c.status === statusFilter.value)
  return list
})

function moduleName(id: number | null): string {
  if (id === null) return '—'
  return caseStore.modules.find((m) => m.id === id)?.name ?? '—'
}

function requirementName(id: number): string {
  return caseStore.requirements.find((r) => r.id === id)?.name ?? '—'
}

function errorDetail(error: any, fallback: string): string {
  return error?.response?.data?.detail || fallback
}

// ---------- 需求对话框 ----------
const reqDialogVisible = ref(false)
const editingReqId = ref<number | null>(null)
const reqForm = reactive({ workspace_id: null as number | null, name: '', description: '' })

function openCreateRequirement(node?: TreeNodeData) {
  editingReqId.value = null
  reqForm.workspace_id =
    node?.type === 'workspace' ? node.id! : (wsStore.currentWorkspaceId ?? wsStore.workspaces[0]?.id ?? null)
  reqForm.name = ''
  reqForm.description = ''
  reqDialogVisible.value = true
}

function openEditRequirement(node: TreeNodeData) {
  const req = caseStore.requirements.find((r) => r.id === node.id)
  if (!req) return
  editingReqId.value = req.id
  reqForm.workspace_id = req.workspace_id
  reqForm.name = req.name
  reqForm.description = req.description
  reqDialogVisible.value = true
}

async function handleSaveRequirement() {
  if (!reqForm.workspace_id) {
    ElMessage.warning('请选择项目空间')
    return
  }
  if (!reqForm.name.trim()) {
    ElMessage.warning('请输入需求名称')
    return
  }
  try {
    const data = {
      workspace_id: reqForm.workspace_id,
      name: reqForm.name.trim(),
      description: reqForm.description,
    }
    if (editingReqId.value) {
      await caseStore.updateRequirement(editingReqId.value, data)
      ElMessage.success('更新成功')
    } else {
      await caseStore.createRequirement(data)
      ElMessage.success('创建成功')
    }
    reqDialogVisible.value = false
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存失败'))
  }
}

async function handleDeleteRequirement(node: TreeNodeData) {
  try {
    await ElMessageBox.confirm('确定删除该需求吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await caseStore.deleteRequirement(node.id!)
    ElMessage.success('删除成功')
    handleDimensionChange()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorDetail(error, '删除失败'))
  }
}

// ---------- 模块对话框 ----------
const modDialogVisible = ref(false)
const editingModId = ref<number | null>(null)
const modForm = reactive({ requirement_id: null as number | null, name: '' })

function openCreateModule(node?: TreeNodeData) {
  editingModId.value = null
  modForm.requirement_id =
    node?.type === 'requirement'
      ? node.id!
      : (caseStore.requirements[0]?.id ?? null)
  modForm.name = ''
  modDialogVisible.value = true
}

function openEditModule(node: TreeNodeData) {
  const mod = caseStore.modules.find((m) => m.id === node.id)
  if (!mod) return
  editingModId.value = mod.id
  modForm.requirement_id = mod.requirement_id
  modForm.name = mod.name
  modDialogVisible.value = true
}

async function handleSaveModule() {
  if (!modForm.requirement_id) {
    ElMessage.warning('请选择需求')
    return
  }
  if (!modForm.name.trim()) {
    ElMessage.warning('请输入模块名称')
    return
  }
  try {
    const data = { requirement_id: modForm.requirement_id, name: modForm.name.trim() }
    if (editingModId.value) {
      await caseStore.updateModule(editingModId.value, data)
      ElMessage.success('更新成功')
    } else {
      await caseStore.createModule(data)
      ElMessage.success('创建成功')
    }
    modDialogVisible.value = false
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存失败'))
  }
}

async function handleDeleteModule(node: TreeNodeData) {
  try {
    await ElMessageBox.confirm('确定删除该模块吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await caseStore.deleteModule(node.id!)
    ElMessage.success('删除成功')
    handleDimensionChange()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorDetail(error, '删除失败'))
  }
}

function openEditNode(data: TreeNodeData) {
  if (data.type === 'requirement') openEditRequirement(data)
  else if (data.type === 'module') openEditModule(data)
}

function handleDeleteNode(data: TreeNodeData) {
  if (data.type === 'requirement') handleDeleteRequirement(data)
  else if (data.type === 'module') handleDeleteModule(data)
}

// ---------- 用例对话框 ----------
const caseDialogVisible = ref(false)
const editingCaseId = ref<number | null>(null)
const caseForm = reactive({
  requirement_id: null as number | null,
  module_id: null as number | null,
  title: '',
  precondition: '',
  stepsText: '',
  expected_result: '',
  status: 'pending' as CaseStatus,
})

const caseFormModuleOptions = computed(() =>
  caseStore.modules.filter((m) => m.requirement_id === caseForm.requirement_id),
)

const requirementOptions = computed(() =>
  caseStore.requirements.map((r) => {
    const wsName = wsStore.workspaces.find((w) => w.id === r.workspace_id)?.name ?? ''
    return { id: r.id, label: wsName ? `${r.name}（${wsName}）` : r.name }
  }),
)

function openCreateCase() {
  editingCaseId.value = null
  caseForm.requirement_id =
    filter.value.type === 'requirement'
      ? filter.value.id
      : filter.value.type === 'module'
        ? (caseStore.modules.find((m) => m.id === filter.value.id)?.requirement_id ?? null)
        : (caseStore.requirements[0]?.id ?? null)
  caseForm.module_id = filter.value.type === 'module' ? filter.value.id : null
  caseForm.title = ''
  caseForm.precondition = ''
  caseForm.stepsText = ''
  caseForm.expected_result = ''
  caseForm.status = 'pending'
  caseDialogVisible.value = true
}

function openEditCase(row: TestCase) {
  editingCaseId.value = row.id
  caseForm.requirement_id = row.requirement_id
  caseForm.module_id = row.module_id
  caseForm.title = row.title
  caseForm.precondition = row.precondition
  caseForm.stepsText = row.steps.join('\n')
  caseForm.expected_result = row.expected_result
  caseForm.status = row.status
  caseDialogVisible.value = true
}

function handleCaseFormRequirementChange() {
  caseForm.module_id = null
}

async function handleSaveCase() {
  if (!caseForm.requirement_id) {
    ElMessage.warning('请选择需求')
    return
  }
  if (!caseForm.title.trim()) {
    ElMessage.warning('请输入用例标题')
    return
  }
  try {
    const data = {
      requirement_id: caseForm.requirement_id,
      module_id: caseForm.module_id,
      title: caseForm.title.trim(),
      precondition: caseForm.precondition,
      steps: caseForm.stepsText.split('\n').map((s) => s.trim()).filter(Boolean),
      expected_result: caseForm.expected_result,
      status: caseForm.status,
    }
    if (editingCaseId.value) {
      await caseStore.updateCase(editingCaseId.value, data)
      ElMessage.success('更新成功')
    } else {
      await caseStore.createCase(data)
      ElMessage.success('创建成功')
    }
    caseDialogVisible.value = false
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存失败'))
  }
}

async function handleDeleteCase(row: TestCase) {
  try {
    await ElMessageBox.confirm(`确定删除用例「${row.title}」吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await caseStore.deleteCase(row.id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorDetail(error, '删除失败'))
  }
}

// ---------- 状态维护 ----------
async function handleStatusChange(row: TestCase, status: CaseStatus) {
  try {
    await caseStore.updateCaseStatus(row.id, status)
    ElMessage.success('状态已更新')
  } catch (error) {
    ElMessage.error(errorDetail(error, '状态更新失败'))
  }
}

const selectedCases = ref<TestCase[]>([])
const batchTarget = ref<CaseStatus>('completed')

async function handleBatchStatus() {
  if (!selectedCases.value.length) {
    ElMessage.warning('请先勾选用例')
    return
  }
  const label = statusLabel(batchTarget.value)
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${selectedCases.value.length} 个用例状态设为「${label}」吗？`,
      '批量更新状态',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
    await caseStore.batchUpdateStatus(
      selectedCases.value.map((c) => c.id),
      batchTarget.value,
    )
    ElMessage.success(`已更新 ${selectedCases.value.length} 个用例`)
    selectedCases.value = []
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorDetail(error, '批量更新失败'))
  }
}

async function handleBatchDelete() {
  if (!selectedCases.value.length) {
    ElMessage.warning('请先勾选用例')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedCases.value.length} 个用例吗？删除后不可恢复`,
      '批量删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
    await caseStore.batchDeleteCases(selectedCases.value.map((c) => c.id))
    ElMessage.success(`已删除 ${selectedCases.value.length} 个用例`)
    selectedCases.value = []
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorDetail(error, '批量删除失败'))
  }
}

// ---------- 思维导图 ----------
const mapVisible = ref(false)
const mapData = ref<MindmapNode | null>(null)

function caseNode(c: TestCase): MindmapNode {
  return { content: `[${statusLabel(c.status)}] ${c.title}`, children: [] }
}

function openMindmap() {
  const f = filter.value
  if (f.type === 'module') {
    const mod = caseStore.modules.find((m) => m.id === f.id)
    if (!mod) return
    mapData.value = {
      content: mod.name,
      children: caseStore.cases.filter((c) => c.module_id === f.id).map(caseNode),
    }
  } else if (f.type === 'requirement') {
    const req = caseStore.requirements.find((r) => r.id === f.id)
    if (!req) return
    mapData.value = buildRequirementMindmap(
      req,
      caseStore.modules.filter((m) => m.requirement_id === req.id),
      caseStore.cases.filter((c) => c.requirement_id === req.id),
    )
  } else if (f.type === 'workspace') {
    const ws = wsStore.workspaces.find((w) => w.id === f.id)
    if (!ws) return
    mapData.value = {
      content: ws.name,
      children: caseStore.requirements
        .filter((r) => r.workspace_id === ws.id)
        .map((r) => {
          const node = buildRequirementMindmap(
            r,
            caseStore.modules.filter((m) => m.requirement_id === r.id),
            caseStore.cases.filter((c) => c.requirement_id === r.id),
          )
          return { content: node.content, children: node.children }
        }),
    }
  } else {
    mapData.value = {
      content: '全部用例',
      children: wsStore.workspaces.map((ws) => ({
        content: ws.name,
        children: caseStore.requirements
          .filter((r) => r.workspace_id === ws.id)
          .map((r) => {
            const node = buildRequirementMindmap(
              r,
              caseStore.modules.filter((m) => m.requirement_id === r.id),
              caseStore.cases.filter((c) => c.requirement_id === r.id),
            )
            return { content: node.content, children: node.children }
          }),
      })),
    }
  }
  mapVisible.value = true
}

// ---------- 导入 ----------
const importVisible = ref(false)

onMounted(() => {
  wsStore.fetchWorkspaces()
  caseStore.fetchAll()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h2>测试用例管理</h2>
      <div class="header-actions">
        <el-button @click="openCreateRequirement()">
          <el-icon><Folder /></el-icon> 新建需求
        </el-button>
        <el-button @click="openCreateModule()">
          <el-icon><Files /></el-icon> 新建模块
        </el-button>
        <el-button @click="importVisible = true">
          <el-icon><Upload /></el-icon> 导入 MD
        </el-button>
        <el-button type="primary" @click="openCreateCase">
          <el-icon><Plus /></el-icon> 新建用例
        </el-button>
      </div>
    </div>

    <div class="tc-layout">
      <el-card class="tc-tree-card" v-loading="caseStore.loading">
        <el-radio-group
          v-model="dimension"
          size="small"
          @change="handleDimensionChange"
          style="margin-bottom: 12px"
        >
          <el-radio-button value="workspace">按项目空间</el-radio-button>
          <el-radio-button value="requirement">按需求</el-radio-button>
        </el-radio-group>
        <el-tree
          :data="treeData"
          node-key="key"
          :current-node-key="currentNodeKey"
          highlight-current
          default-expand-all
          :expand-on-click-node="false"
          @node-click="handleNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span>{{ data.label }}</span>
              <span
                v-if="data.type === 'requirement' || data.type === 'module'"
                class="tree-node-actions"
              >
                <el-button link size="small" type="primary" @click.stop="openEditNode(data)">
                  编辑
                </el-button>
                <el-button link size="small" type="danger" @click.stop="handleDeleteNode(data)">
                  删除
                </el-button>
              </span>
            </span>
          </template>
        </el-tree>
      </el-card>

      <el-card class="tc-table-card">
        <div class="toolbar">
          <el-select
            v-model="statusFilter"
            placeholder="状态筛选"
            clearable
            size="default"
            style="width: 130px"
          >
            <el-option
              v-for="opt in CASE_STATUS_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <div class="toolbar-right">
            <span v-if="selectedCases.length" class="batch-tip">
              已选 {{ selectedCases.length }} 项
            </span>
            <el-select v-model="batchTarget" size="default" style="width: 110px">
              <el-option
                v-for="opt in CASE_STATUS_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <el-button :disabled="!selectedCases.length" @click="handleBatchStatus">
              批量更新状态
            </el-button>
            <el-button
              type="danger"
              plain
              :disabled="!selectedCases.length"
              @click="handleBatchDelete"
            >
              批量删除
            </el-button>
            <el-button :disabled="!filteredCases.length" @click="openMindmap">
              <el-icon><Share /></el-icon> 思维导图
            </el-button>
          </div>
        </div>

        <el-table
          :data="filteredCases"
          style="width: 100%"
          @selection-change="(rows: TestCase[]) => (selectedCases = rows)"
        >
          <el-table-column type="selection" width="45" />
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="case-detail">
                <p v-if="row.precondition"><b>前置条件：</b>{{ row.precondition }}</p>
                <p v-if="row.steps.length">
                  <b>步骤：</b>
                </p>
                <ol v-if="row.steps.length">
                  <li v-for="(step, i) in row.steps" :key="i">{{ step }}</li>
                </ol>
                <p v-if="row.expected_result"><b>预期结果：</b>{{ row.expected_result }}</p>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="所属需求" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ requirementName(row.requirement_id) }}</template>
          </el-table-column>
          <el-table-column label="模块" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ moduleName(row.module_id) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-select
                :model-value="row.status"
                size="small"
                @change="(v: CaseStatus) => handleStatusChange(row, v)"
              >
                <el-option
                  v-for="opt in CASE_STATUS_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditCase(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="handleDeleteCase(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 需求对话框 -->
    <el-dialog
      v-model="reqDialogVisible"
      :title="editingReqId ? '编辑需求' : '新建需求'"
      width="460px"
    >
      <el-form label-width="80px">
        <el-form-item label="项目空间" required>
          <el-select v-model="reqForm.workspace_id" placeholder="选择项目空间" style="width: 100%">
            <el-option v-for="ws in wsStore.workspaces" :key="ws.id" :label="ws.name" :value="ws.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="reqForm.name" placeholder="需求名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="reqForm.description" type="textarea" :rows="2" placeholder="需求描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reqDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveRequirement">保存</el-button>
      </template>
    </el-dialog>

    <!-- 模块对话框 -->
    <el-dialog
      v-model="modDialogVisible"
      :title="editingModId ? '编辑模块' : '新建模块'"
      width="460px"
    >
      <el-form label-width="80px">
        <el-form-item label="所属需求" required>
          <el-select
            v-model="modForm.requirement_id"
            placeholder="选择需求"
            style="width: 100%"
          >
            <el-option
              v-for="opt in requirementOptions"
              :key="opt.id"
              :label="opt.label"
              :value="opt.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="modForm.name" placeholder="模块名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveModule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 用例对话框 -->
    <el-dialog
      v-model="caseDialogVisible"
      :title="editingCaseId ? '编辑测试用例' : '新建测试用例'"
      width="640px"
    >
      <el-form label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="caseForm.title" placeholder="用例标题" />
        </el-form-item>
        <el-form-item label="所属需求" required>
          <el-select
            v-model="caseForm.requirement_id"
            placeholder="选择需求"
            style="width: 100%"
            @change="handleCaseFormRequirementChange"
          >
            <el-option
              v-for="opt in requirementOptions"
              :key="opt.id"
              :label="opt.label"
              :value="opt.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="所属模块">
          <el-select
            v-model="caseForm.module_id"
            placeholder="无模块（直属需求）"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="m in caseFormModuleOptions"
              :key="m.id"
              :label="m.name"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="前置条件">
          <el-input v-model="caseForm.precondition" type="textarea" :rows="2" placeholder="前置条件" />
        </el-form-item>
        <el-form-item label="步骤">
          <el-input
            v-model="caseForm.stepsText"
            type="textarea"
            :rows="4"
            placeholder="每行一个步骤"
          />
        </el-form-item>
        <el-form-item label="预期结果">
          <el-input
            v-model="caseForm.expected_result"
            type="textarea"
            :rows="2"
            placeholder="预期结果"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="caseForm.status" style="width: 160px">
            <el-option
              v-for="opt in CASE_STATUS_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="caseDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveCase">保存</el-button>
      </template>
    </el-dialog>

    <MindMapDialog v-model:visible="mapVisible" :data="mapData" title="测试用例思维导图" />
    <TestCaseImportDialog v-model:visible="importVisible" />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.tc-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.tc-tree-card {
  width: 300px;
  flex-shrink: 0;
}

.tc-table-card {
  flex: 1;
  min-width: 0;
}

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding-right: 4px;
}

.tree-node-actions {
  display: none;
}

:deep(.el-tree-node__content):hover .tree-node-actions {
  display: inline-flex;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.batch-tip {
  color: var(--el-color-primary);
  font-size: 13px;
}

.case-detail {
  padding: 8px 48px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.case-detail p {
  margin: 4px 0;
}

.case-detail ol {
  margin: 4px 0 4px 20px;
  padding: 0;
}
</style>

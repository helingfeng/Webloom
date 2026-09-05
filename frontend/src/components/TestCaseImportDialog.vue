<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useTestCaseStore } from '@/stores/testCaseStore'
import {
  buildImportMindmap,
  countParsedCases,
  parseMarkdownCases,
  type ParsedCases,
} from '@/utils/markdownCases'
import type { MindmapNode } from '@/types/testCase'
import MindMapDialog from './MindMapDialog.vue'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'imported'): void
}>()

const wsStore = useWorkspaceStore()
const caseStore = useTestCaseStore()

const mdText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const mapVisible = ref(false)

const form = reactive({
  workspace_id: null as number | null,
  mode: 'new' as 'new' | 'existing',
  requirement_name: '',
  requirement_id: null as number | null,
})

const parsed = ref<ParsedCases | null>(null)
const caseCount = computed(() => (parsed.value ? countParsedCases(parsed.value) : 0))
const mapData = computed<MindmapNode | null>(() =>
  parsed.value ? buildImportMindmap(parsed.value) : null,
)

const workspaceRequirements = computed(() =>
  caseStore.requirements.filter((r) => r.workspace_id === form.workspace_id),
)

watch(
  () => props.visible,
  async (v) => {
    if (v) {
      if (!wsStore.workspaces.length) await wsStore.fetchWorkspaces()
      if (!caseStore.requirements.length) await caseStore.fetchAll()
      form.workspace_id = wsStore.currentWorkspaceId ?? wsStore.workspaces[0]?.id ?? null
      form.mode = 'new'
      form.requirement_name = ''
      form.requirement_id = null
      mdText.value = ''
      parsed.value = null
    }
  },
)

function pickFile() {
  fileInputRef.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    mdText.value = String(reader.result ?? '')
    handleParse()
  }
  reader.readAsText(file)
  input.value = ''
}

function handleParse() {
  if (!mdText.value.trim()) {
    ElMessage.warning('请先粘贴或选择 Markdown 内容')
    return
  }
  parsed.value = parseMarkdownCases(mdText.value)
  const count = countParsedCases(parsed.value)
  if (count === 0) {
    ElMessage.warning('未解析到任何测试用例，请检查格式（### 标题为用例）')
    return
  }
  ElMessage.success(`解析成功：${parsed.value.modules.length} 个模块、${count} 个用例`)
}

async function handleImport() {
  if (!parsed.value || caseCount.value === 0) {
    ElMessage.warning('请先解析 Markdown 内容')
    return
  }
  if (!form.workspace_id) {
    ElMessage.warning('请选择项目空间')
    return
  }
  if (form.mode === 'new' && !form.requirement_name.trim()) {
    ElMessage.warning('请输入需求名称')
    return
  }
  if (form.mode === 'existing' && !form.requirement_id) {
    ElMessage.warning('请选择需求')
    return
  }
  importing.value = true
  try {
    const result = await caseStore.importCases({
      workspace_id: form.workspace_id,
      requirement_id: form.mode === 'existing' ? form.requirement_id : null,
      requirement_name:
        form.mode === 'new'
          ? form.requirement_name.trim() || parsed.value.requirementName
          : '',
      modules: parsed.value.modules,
      cases: parsed.value.looseCases,
    })
    ElMessage.success(
      `导入成功：需求「${result.requirement_name}」，${result.module_count} 个新模块、${result.case_count} 个用例`,
    )
    emit('update:visible', false)
    emit('imported')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

function handleClose() {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="导入测试用例（Markdown）"
    width="720px"
    @update:model-value="handleClose"
  >
    <el-form label-width="90px">
      <el-form-item label="项目空间" required>
        <el-select v-model="form.workspace_id" placeholder="选择项目空间" style="width: 100%">
          <el-option v-for="ws in wsStore.workspaces" :key="ws.id" :label="ws.name" :value="ws.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="目标需求" required>
        <el-radio-group v-model="form.mode">
          <el-radio value="new">新建需求</el-radio>
          <el-radio value="existing">导入到已有需求</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.mode === 'new'" label="需求名称" required>
        <el-input
          v-model="form.requirement_name"
          :placeholder="parsed?.requirementName ? `默认使用：${parsed.requirementName}` : '未填写时使用 Markdown 中的一级标题'"
        />
      </el-form-item>
      <el-form-item v-else label="选择需求" required>
        <el-select v-model="form.requirement_id" placeholder="选择已有需求" style="width: 100%">
          <el-option
            v-for="r in workspaceRequirements"
            :key="r.id"
            :label="r.name"
            :value="r.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="MD 内容" required>
        <el-input
          v-model="mdText"
          type="textarea"
          :rows="10"
          placeholder="# 需求名&#10;## 模块名&#10;### 用例标题&#10;- 步骤1&#10;- 步骤2&#10;预期结果：..."
          @blur="mdText.trim() && handleParse()"
        />
        <div class="md-actions">
          <el-button size="small" @click="pickFile">选择 .md 文件</el-button>
          <el-button size="small" type="primary" plain @click="handleParse">解析预览</el-button>
          <el-button size="small" :disabled="!parsed" @click="mapVisible = true">
            思维导图预览
          </el-button>
          <input
            ref="fileInputRef"
            type="file"
            accept=".md,.markdown,.txt"
            style="display: none"
            @change="handleFileChange"
          />
        </div>
      </el-form-item>
      <el-form-item v-if="parsed">
        <el-alert
          type="success"
          :closable="false"
          show-icon
          :title="`解析结果：${parsed.modules.length} 个模块、${caseCount} 个用例（重复导入将追加用例，同名模块自动复用）`"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="importing" :disabled="!parsed" @click="handleImport">
        确认导入
      </el-button>
    </template>

    <MindMapDialog v-model:visible="mapVisible" :data="mapData" title="导入预览" />
  </el-dialog>
</template>

<style scoped>
.md-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>

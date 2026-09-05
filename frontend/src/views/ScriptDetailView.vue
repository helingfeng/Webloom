<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScriptStore } from '@/stores/scriptStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import ScriptEditor from '@/components/ScriptEditor.vue'
import ExecutionPanel from '@/components/ExecutionPanel.vue'
import type { ScriptCreate } from '@/types/script'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const scriptStore = useScriptStore()
const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()

const isNew = computed(() => route.path.endsWith('/new'))
const scriptId = computed(() => Number(route.params.id))
const loading = ref(false)
const running = ref(false)
const showExecutionPanel = ref(false)

onMounted(async () => {
  if (!isNew.value && scriptId.value) {
    loading.value = true
    try {
      await scriptStore.fetchScript(scriptId.value)
    } finally {
      loading.value = false
    }
  }
})

const initialData = computed<ScriptCreate>(() => {
  if (isNew.value || !scriptStore.currentScript) {
    return {
      workspace_id: wsStore.currentWorkspaceId ?? 0,
      name: '',
      description: '',
      start_url: '',
      inputs: [],
      outputs: [],
      code: '',
      run_mode: 'manual',
      headless: true,
    }
  }
  return scriptStore.currentScript
})

async function handleSave(data: ScriptCreate) {
  try {
    if (isNew.value) {
      const created = await scriptStore.createScript(data)
      ElMessage.success('创建成功')
      router.replace(`/scripts/${created.id}`)
    } else {
      await scriptStore.updateScript(scriptId.value, data)
      ElMessage.success('保存成功')
    }
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleRun(runData: {
  mode: 'manual' | 'mock'
  inputs: Record<string, any>
  headless?: boolean
}) {
  if (isNew.value) {
    ElMessage.warning('请先保存脚本')
    return
  }
  running.value = true
  try {
    const result = await scriptStore.runScript(scriptId.value, {
      mode: runData.mode,
      inputs: runData.inputs,
      headless: runData.headless ?? true,
    })
    showExecutionPanel.value = true
    if (result.execution_id) {
      await executionStore.fetchExecution(result.execution_id)
    }
  } catch (error) {
    ElMessage.error('执行失败')
    console.error(error)
  } finally {
    running.value = false
  }
}

function handleCancel() {
  router.push('/scripts')
}
</script>

<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>{{ isNew ? '新建脚本' : '编辑脚本' }}</h2>
    </div>

    <ScriptEditor
      :initial-data="initialData"
      :running="running"
      @save="handleSave"
      @cancel="handleCancel"
      @run="handleRun"
    />

    <ExecutionPanel
      v-model:visible="showExecutionPanel"
      :execution="executionStore.currentExecution"
    />
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
</style>

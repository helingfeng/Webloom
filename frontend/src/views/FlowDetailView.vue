<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFlowStore } from '@/stores/flowStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import FlowEditor from '@/components/FlowEditor.vue'
import ExecutionPanel from '@/components/ExecutionPanel.vue'
import type { FlowCreate } from '@/types/flow'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const flowStore = useFlowStore()
const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()

const isNew = computed(() => route.path.endsWith('/new'))
const flowId = computed(() => Number(route.params.id))
const loading = ref(false)
const running = ref(false)
const showExecutionPanel = ref(false)

onMounted(async () => {
  if (!isNew.value && flowId.value) {
    loading.value = true
    try {
      await flowStore.fetchFlow(flowId.value)
    } finally {
      loading.value = false
    }
  }
})

const initialData = computed<FlowCreate>(() => {
  if (isNew.value || !flowStore.currentFlow) {
    return {
      workspace_id: wsStore.currentWorkspaceId ?? 0,
      name: '',
      description: '',
      nodes: [],
      edges: [],
    }
  }
  return flowStore.currentFlow
})

async function handleSave(data: FlowCreate) {
  try {
    if (isNew.value) {
      const created = await flowStore.createFlow(data)
      ElMessage.success('创建成功')
      router.replace(`/flows/${created.id}`)
    } else {
      await flowStore.updateFlow(flowId.value, data)
      ElMessage.success('保存成功')
    }
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleRun(runData: { mode: 'manual' | 'mock'; global_inputs: Record<string, any> }) {
  if (isNew.value) {
    ElMessage.warning('请先保存流程')
    return
  }
  running.value = true
  try {
    const result = await flowStore.runFlow(flowId.value, runData)
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
  router.push('/flows')
}
</script>

<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>{{ isNew ? '新建流程' : '编辑流程' }}</h2>
    </div>

    <FlowEditor
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

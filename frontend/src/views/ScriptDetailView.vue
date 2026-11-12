<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useScriptStore } from '@/stores/scriptStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { apiError } from '@/api/collectors'
import type { ScriptCreate } from '@/types/script'
import ScriptEditor from '@/components/ScriptEditor.vue'
import ExecutionPanel from '@/components/ExecutionPanel.vue'
const route = useRoute(), router = useRouter()
const scripts = useScriptStore(), executions = useExecutionStore(), workspaces = useWorkspaceStore()
const isNew = computed(() => route.path.endsWith('/new'))
const scriptId = computed(() => Number(route.params.id))
const loading = ref(false), saving = ref(false), running = ref(false), showPanel = ref(false)
watch(() => route.fullPath, async () => {
  if (isNew.value || !scriptId.value) return
  loading.value = true
  try { await scripts.fetchScript(scriptId.value) } catch(e) { ElMessage.error(apiError(e)) }
  finally { loading.value = false }
}, { immediate: true })
const initialData = computed<ScriptCreate>(() => !isNew.value && scripts.currentScript?.id === scriptId.value ? scripts.currentScript : {
  workspace_id: workspaces.currentWorkspaceId ?? 0, name: '', description: '', start_url: '', code: '', inputs: [], outputs: [], inherit_global: true, run_mode: 'manual', headless: true,
})
async function persist(data: ScriptCreate): Promise<number> {
  if (isNew.value) {
    const created = await scripts.createScript(data)
    await router.replace(`/scripts/${created.id}`)
    return created.id
  }
  const id = scriptId.value
  await scripts.updateScript(id, data)
  return id
}
async function save(data: ScriptCreate) {
  saving.value = true
  try { await persist(data); ElMessage.success('已保存') } catch(e) { ElMessage.error(apiError(e)) }
  finally { saving.value = false }
}
async function run(data: { script: ScriptCreate; mode: 'manual'; inputs: Record<string, unknown>; headless: boolean }) {
  running.value = true
  try {
    const id = await persist(data.script)
    const task = await scripts.runScript(id, { mode: 'manual', inputs: data.inputs, headless: data.headless })
    await executions.fetchExecution(task.execution_id)
    showPanel.value = true
  } catch(e) { ElMessage.error(apiError(e)) } finally { running.value = false }
}
</script>
<template>
  <div v-loading="loading"><h2>{{ isNew ? '新建采集脚本' : '编辑采集脚本' }}</h2><ScriptEditor :initial-data="initialData" :saving="saving" :running="running" @save="save" @run="run" @cancel="router.push('/scripts')" /><ExecutionPanel v-model:visible="showPanel" :execution="executions.currentExecution" /></div>
</template>

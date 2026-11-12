<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CollectorTask } from '@/types/collector'
const props = defineProps<{ task: CollectorTask }>()
const field = ref('')
const page = ref(1)
const outputs = computed(() => props.task.outputs ?? {})
watch(() => props.task.execution_id, () => { field.value = ''; page.value = 1 })
watch(outputs, value => { if (!field.value || !(field.value in value)) field.value = Object.keys(value).find(k => Array.isArray(value[k])) ?? Object.keys(value)[0] ?? '' }, { immediate: true })
watch(field, () => { page.value = 1 })
const rows = computed<Record<string, unknown>[]>(() => {
  if (!field.value) return []
  const v = outputs.value[field.value]
  return (Array.isArray(v) ? v : [v]).map(r => r !== null && typeof r === 'object' && !Array.isArray(r) ? r as Record<string, unknown> : { value: r })
})
const visibleRows = computed(() => rows.value.slice((page.value - 1) * 20, page.value * 20))
const columns = computed(() => [...new Set(visibleRows.value.flatMap(r => Object.keys(r)))])
const display = (v: unknown) => typeof v === 'object' ? JSON.stringify(v) : String(v ?? '')
function download(format: 'json' | 'csv') {
  const cell = (v: unknown) => {
    let text = display(v)
    if (/^[\s]*[=+@\-\t\r\n]/.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  const keys = [...new Set(rows.value.flatMap(r => Object.keys(r)))]
  const data = format === 'json' ? JSON.stringify(outputs.value, null, 2) : '\uFEFF' + [keys.map(cell).join(','), ...rows.value.map(r => keys.map(k => cell(r[k])).join(','))].join('\r\n')
  const url = URL.createObjectURL(new Blob([data], { type: format === 'json' ? 'application/json' : 'text/csv;charset=utf-8' }))
  const a = document.createElement('a'); a.href = url; a.download = `collection-${props.task.execution_id}.${format}`; a.click(); URL.revokeObjectURL(url)
}
</script>
<template>
  <div class="status"><el-tag :type="task.status === 'success' ? 'success' : task.status === 'failed' ? 'danger' : 'warning'">{{ { pending: '排队中', running: '采集中', success: '采集完成', failed: '采集失败' }[task.status] }}</el-tag><span>任务 #{{ task.execution_id }}</span></div>
  <el-alert v-if="task.error" :title="task.error" type="error" :closable="false" show-icon />
  <el-alert v-if="!task.finished" title="任务正在处理，结果将自动更新。可以关闭面板，稍后从任务列表继续查看。" type="info" :closable="false" />
  <el-tabs v-if="task.finished">
    <el-tab-pane label="数据表格">
      <div class="toolbar"><el-select v-model="field" style="width: 200px" placeholder="选择输出字段"><el-option v-for="key in Object.keys(outputs)" :key="key" :label="key" :value="key" /></el-select><span>共 {{ rows.length }} 条</span><el-button :disabled="!rows.length" @click="download('csv')">导出此字段 CSV</el-button><el-button @click="download('json')">导出完整 JSON</el-button></div>
      <el-table :data="visibleRows" border max-height="420" empty-text="没有采集数据"><el-table-column v-for="key in columns" :key="key" :label="key" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ display(row[key]) }}</template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :total="rows.length" :page-size="20" layout="total, prev, pager, next" />
    </el-tab-pane>
    <el-tab-pane label="完整 JSON"><pre>{{ JSON.stringify(outputs, null, 2) }}</pre></el-tab-pane>
  </el-tabs>
  <el-collapse v-if="task.logs"><el-collapse-item title="执行日志" name="logs"><pre>{{ task.logs }}</pre></el-collapse-item></el-collapse>
</template>
<style scoped>.toolbar,.status { display:flex; align-items:center; gap:12px; margin:16px 0; flex-wrap:wrap } pre { white-space:pre-wrap; overflow-wrap:anywhere; background:#f6f8fa; padding:16px; max-height:440px; overflow:auto; } .el-pagination { margin-top:16px; }</style>

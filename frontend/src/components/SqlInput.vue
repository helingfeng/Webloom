<script setup lang="ts">
// SQL 输入封装：Monaco 编辑器（语法高亮 + 后端校验 + 格式化 + 关键字补全）。
// 对外接口保持不变：v-model、rows、placeholder、Ctrl/Cmd+Enter 触发 execute。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { validateSql, formatSql } from '@/api/code'
import { ElMessage } from 'element-plus'

// Monaco worker 全局只注册一次（CodeEditor 与 SqlInput 共用同一标记）
if (!(self as any).__atpMonacoEnv) {
  ;(self as any).__atpMonacoEnv = true
  ;(self as any).MonacoEnvironment = {
    getWorker: () => new editorWorker(),
  }
}

// SQL 关键字补全：全局只注册一次（组件在工作台与数据视图两处使用）
if (!(self as any).__atpSqlCompletion) {
  ;(self as any).__atpSqlCompletion = true
  const SQL_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN',
    'IS', 'NULL', 'AS', 'ON', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN',
    'OUTER JOIN', 'CROSS JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT',
    'OFFSET', 'UNION', 'UNION ALL', 'DISTINCT', 'INSERT INTO', 'VALUES',
    'UPDATE', 'SET', 'DELETE FROM', 'CREATE TABLE', 'ALTER TABLE', 'DROP TABLE',
    'CREATE INDEX', 'CREATE VIEW', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'EXISTS', 'ASC', 'DESC',
    'SHOW TABLES', 'DESCRIBE', 'EXPLAIN', 'WITH', 'TABLE', 'INTERVAL', 'IF',
  ]
  monaco.languages.registerCompletionItemProvider('sql', {
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range = new monaco.Range(
        position.lineNumber,
        word.startColumn,
        position.lineNumber,
        word.endColumn
      )
      return {
        suggestions: SQL_KEYWORDS.map((k) => ({
          label: k,
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: k,
          range,
        })),
      }
    },
  })
}

const props = defineProps<{
  modelValue: string
  placeholder?: string
  rows?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  execute: []
}>()

const containerRef = ref<HTMLDivElement>()
// 编辑器实例不能放进响应式 ref：Monaco 内部被 Vue 深度 Proxy 包裹会导致卡顿
let editor: monaco.editor.IStandaloneCodeEditor | undefined
const formatting = ref(false)

const containerHeight = computed(() => `${(props.rows ?? 12) * 21 + 14}px`)

let suppressChange = false
let validateTimer: ReturnType<typeof setTimeout> | undefined
let requestSeq = 0

function scheduleValidate() {
  clearTimeout(validateTimer)
  validateTimer = setTimeout(doValidate, 800)
}

async function doValidate() {
  if (!editor) return
  const code = editor.getValue()
  const model = editor.getModel()
  if (!model) return
  if (!code.trim()) {
    monaco.editor.setModelMarkers(model, 'sql-check', [])
    return
  }
  const seq = ++requestSeq
  try {
    const res = await validateSql(code)
    if (seq !== requestSeq || !editor || !editor.getModel()) return // 已被更新的请求取代
    const markers = res.data.errors.map((err) => {
      const lineCount = model.getLineCount()
      const line = Math.min(Math.max(err.line, 1), lineCount)
      const col = Math.max(err.column, 1)
      const lineLen = model.getLineMaxColumn(line)
      return {
        severity: monaco.MarkerSeverity.Error,
        message: err.message,
        startLineNumber: line,
        startColumn: Math.min(col, lineLen),
        endLineNumber: line,
        endColumn: lineLen,
      }
    })
    monaco.editor.setModelMarkers(model, 'sql-check', markers)
  } catch {
    // 网络错误时不清除已有标记
  }
}

async function handleFormat() {
  if (!editor || formatting.value) return
  const code = editor.getValue()
  if (!code.trim()) return
  formatting.value = true
  try {
    const res = await formatSql(code)
    if (res.data.changed) {
      setValue(res.data.code)
      ElMessage.success('格式化完成')
    } else {
      ElMessage.info('SQL 已是规范格式')
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '格式化失败')
  } finally {
    formatting.value = false
  }
}

function setValue(value: string) {
  if (!editor || editor.getValue() === value) return
  suppressChange = true
  editor.setValue(value)
  suppressChange = false
}

onMounted(() => {
  editor = monaco.editor.create(containerRef.value!, {
    value: props.modelValue,
    language: 'sql',
    theme: 'vs',
    placeholder: props.placeholder,
    tabSize: 2,
    insertSpaces: true,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    fontSize: 13,
  })

  editor.onDidChangeModelContent(() => {
    if (suppressChange || !editor) return
    emit('update:modelValue', editor.getValue())
    scheduleValidate()
  })

  // Ctrl/Cmd+Enter 执行；Ctrl/Cmd+Shift+F 格式化
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => emit('execute'))
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, handleFormat)

  if (props.modelValue.trim()) scheduleValidate()
})

watch(
  () => props.modelValue,
  (val) => setValue(val)
)

onBeforeUnmount(() => {
  clearTimeout(validateTimer)
  editor?.dispose()
  editor = undefined
})
</script>

<template>
  <div>
    <div ref="containerRef" class="sql-container" :style="{ height: containerHeight }" />
    <div class="format-bar">
      <el-button size="small" :loading="formatting" @click="handleFormat">
        格式化 SQL
      </el-button>
      <span class="format-hint">Ctrl/⌘+Enter 执行；Ctrl/⌘+Shift+F 格式化；语法错误会在编辑停止后自动检测</span>
    </div>
  </div>
</template>

<style scoped>
.sql-container {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.format-bar {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.format-hint {
  color: #909399;
  font-size: 12px;
}
</style>

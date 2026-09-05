<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { validateCode as apiValidateCode, formatCode as apiFormatCode } from '@/api/code'
import { ElMessage } from 'element-plus'

// Monaco 需要 worker 执行语言服务；Python 走 basic-languages 仅需 editor worker
if (!(self as any).__atpMonacoEnv) {
  ;(self as any).__atpMonacoEnv = true
  ;(self as any).MonacoEnvironment = {
    getWorker: () => new editorWorker(),
  }
}

// Python 关键字 + 脚本模板内置变量补全：全局只注册一次
if (!(self as any).__atpPythonCompletion) {
  ;(self as any).__atpPythonCompletion = true
  const PYTHON_KEYWORDS = [
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break',
    'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'finally',
    'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal',
    'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
  ]
  const TEMPLATE_VARS = [
    'INPUTS', 'OUTPUTS', 'GLOBAL_VARS', 'GLOBAL_HEADERS', 'GLOBAL_LOCAL_STORAGE',
    'DATA_VIEWS', 'DATA_VIEWS_ONE', 'page', 'context', 'browser',
  ]
  monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range = new monaco.Range(
        position.lineNumber,
        word.startColumn,
        position.lineNumber,
        word.endColumn
      )
      return {
        suggestions: [
          ...PYTHON_KEYWORDS.map((k) => ({
            label: k,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: k,
            range,
          })),
          ...TEMPLATE_VARS.map((v) => ({
            label: v,
            kind: monaco.languages.CompletionItemKind.Variable,
            insertText: v,
            detail: '脚本模板内置变量',
            range,
          })),
        ],
      }
    },
  })
}

const props = withDefaults(defineProps<{ modelValue?: string; height?: string }>(), {
  modelValue: '',
  height: '480px',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const containerRef = ref<HTMLDivElement>()
// 编辑器实例不能放进响应式 ref：Monaco 内部有大量嵌套属性，
// 被 Vue 深度 Proxy 包裹会导致访问即卡顿/卡死
let editor: monaco.editor.IStandaloneCodeEditor | undefined
const formatting = ref(false)

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
    monaco.editor.setModelMarkers(model, 'python-check', [])
    return
  }
  const seq = ++requestSeq
  try {
    const res = await apiValidateCode(code)
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
    monaco.editor.setModelMarkers(model, 'python-check', markers)
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
    const res = await apiFormatCode(code)
    if (res.data.changed) {
      setValue(res.data.code)
      ElMessage.success('格式化完成')
    } else {
      ElMessage.info('代码已是规范格式')
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
    language: 'python',
    theme: 'vs',
    tabSize: 4,
    insertSpaces: true,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false,
    fontSize: 13,
  })

  editor.onDidChangeModelContent(() => {
    if (suppressChange || !editor) return
    emit('update:modelValue', editor.getValue())
    scheduleValidate()
  })

  // Ctrl/Cmd+Shift+F 快捷格式化
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

defineExpose({ format: handleFormat, formatting })
</script>

<template>
  <div>
    <div ref="containerRef" class="code-container" :style="{ height }" />
    <div class="format-bar">
      <el-button size="small" :loading="formatting" @click="handleFormat">
        格式化代码
      </el-button>
      <span class="format-hint">也可用 Ctrl/⌘+Shift+F；语法错误会在编辑停止后自动检测</span>
    </div>
  </div>
</template>

<style scoped>
.code-container {
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

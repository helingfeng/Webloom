<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useExecutionStore } from '@/stores/executionStore'
import { formatDateTime } from '@/utils/format'
import type { Execution } from '@/types/execution'

const props = defineProps<{
  visible: boolean
  execution: Execution | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const executionStore = useExecutionStore()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const liveLogs = ref('')
const ws = ref<WebSocket | null>(null)
const logBlockRef = ref<HTMLPreElement | null>(null)
let pollTimer: number | null = null

// 实时画面：轮询后端帧图接口（子进程 screencast 持续覆写帧文件）
const liveFrameUrl = ref('')
const frameVisible = ref(false)
let frameTimer: number | null = null
let frameLoading = false
let frameExecId = 0

const statusType = computed(() => {
  if (!props.execution) return ''
  const map: Record<string, string> = {
    success: 'success',
    failed: 'danger',
    running: 'primary',
    pending: 'info',
  }
  return map[props.execution.status] || 'info'
})

const formattedOutputs = computed(() => {
  if (!props.execution?.outputs) return ''
  return JSON.stringify(props.execution.outputs, null, 2)
})

const displayLogs = computed(() => {
  if (liveLogs.value) {
    return liveLogs.value
  }
  return props.execution?.logs || '暂无日志'
})

const isRunning = computed(() => {
  return props.execution?.status === 'running' || props.execution?.status === 'pending'
})

function getWsUrl(executionId: number): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/ws/executions/${executionId}`
}

function connectWebSocket(executionId: number) {
  closeWebSocket()
  liveLogs.value = ''
  const socket = new WebSocket(getWsUrl(executionId))
  ws.value = socket

  socket.onmessage = (event) => {
    liveLogs.value += event.data
    scrollToBottom()
  }

  socket.onerror = () => {
    liveLogs.value += '\n[WebSocket 连接错误]'
  }

  socket.onclose = () => {
    ws.value = null
  }
}

function closeWebSocket() {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = logBlockRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

function startPolling(executionId: number) {
  stopPolling()
  pollTimer = window.setInterval(() => {
    executionStore.fetchExecution(executionId)
  }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startFramePolling(executionId: number) {
  stopFramePolling()
  frameExecId = executionId
  frameVisible.value = true
  fetchFrame()
  frameTimer = window.setInterval(fetchFrame, 400)
}

function stopFramePolling() {
  if (frameTimer) {
    clearInterval(frameTimer)
    frameTimer = null
  }
  frameVisible.value = false
  if (liveFrameUrl.value) {
    URL.revokeObjectURL(liveFrameUrl.value)
  }
  liveFrameUrl.value = ''
  frameLoading = false
}

function fetchFrame() {
  if (frameLoading || !frameExecId) return
  frameLoading = true
  const url = `/api/executions/${frameExecId}/frame?t=${Date.now()}`
  fetch(url)
    .then(async (res) => {
      if (res.ok) {
        const blob = await res.blob()
        if (liveFrameUrl.value) {
          URL.revokeObjectURL(liveFrameUrl.value)
        }
        liveFrameUrl.value = URL.createObjectURL(blob)
      }
    })
    .catch(() => {})
    .finally(() => {
      frameLoading = false
    })
}

watch(
  () => props.execution?.id,
  (id) => {
    if (id) {
      connectWebSocket(id)
    } else {
      closeWebSocket()
    }
  },
  { immediate: true }
)

watch(
  [() => isRunning.value, () => props.execution?.id, () => props.visible],
  ([running, id, visible]) => {
    if (running && id && visible) {
      startPolling(id as number)
      startFramePolling(id as number)
    } else {
      stopPolling()
      stopFramePolling()
    }
  },
  { immediate: true }
)

watch(
  () => props.execution?.status,
  (newStatus, oldStatus) => {
    if (oldStatus === 'running' && (newStatus === 'success' || newStatus === 'failed')) {
      liveLogs.value = ''
    }
  }
)

watch(dialogVisible, (visible) => {
  if (visible) {
    const id = props.execution?.id
    if (id && !ws.value) {
      connectWebSocket(id)
    }
  } else {
    closeWebSocket()
    stopPolling()
  }
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="执行结果"
    width="70%"
    destroy-on-close
  >
    <div v-if="execution" class="execution-panel">
      <div class="execution-meta">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="执行 ID">{{ execution.id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType">
              <el-icon v-if="isRunning" class="is-loading"><Loading /></el-icon>
              {{ execution.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="模式">{{ execution.mode }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(execution.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(execution.finished_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <el-divider />

      <div v-if="frameVisible" class="execution-section">
        <h4>
          实时画面
          <el-tag size="small" type="danger" effect="dark" class="live-tag">LIVE</el-tag>
        </h4>
        <div class="frame-wrap">
          <img v-if="liveFrameUrl" :src="liveFrameUrl" class="frame-block" alt="浏览器实时画面" />
          <div v-else class="frame-placeholder">正在连接浏览器画面...</div>
        </div>
      </div>

      <div class="execution-section">
        <h4>输入参数</h4>
        <pre class="json-block">{{ JSON.stringify(execution.inputs, null, 2) }}</pre>
      </div>

      <div class="execution-section">
        <h4>输出结果</h4>
        <pre class="json-block">{{ formattedOutputs }}</pre>
      </div>

      <div class="execution-section">
        <h4>执行日志</h4>
        <pre ref="logBlockRef" class="log-block">{{ displayLogs }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.execution-meta {
  margin-bottom: 20px;
}

.execution-section {
  margin-bottom: 20px;
}

.execution-section h4 {
  margin: 0 0 10px 0;
  color: #333;
}

.json-block, .log-block {
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 12px;
  margin: 0;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

.log-block {
  background-color: #1e1e1e;
  color: #d4d4d4;
}

.live-tag {
  margin-left: 8px;
  vertical-align: middle;
}

.frame-wrap {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background-color: #1e1e1e;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.frame-block {
  display: block;
  width: 100%;
  max-height: 480px;
  object-fit: contain;
}

.frame-placeholder {
  color: #909399;
  font-size: 13px;
  padding: 60px 0;
}

.is-loading {
  animation: rotating 2s linear infinite;
  margin-right: 5px;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

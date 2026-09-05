<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as recordingsApi from '@/api/recordings'
import type { RecordingSession } from '@/types/recording'

const emit = defineEmits<{
  apply: [data: { code: string; start_url: string }]
}>()

const dialogVisible = ref(false)
const phase = ref<'input' | 'recording' | 'done'>('input')
const startUrl = ref('')
const recordingId = ref<number | null>(null)
const recordedCode = ref('')
const detectedStartUrl = ref('')
const starting = ref(false)
const appliedGlobals = ref<RecordingSession['applied_globals'] | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

function open(initialUrl: string) {
  dialogVisible.value = true
  phase.value = 'input'
  startUrl.value = initialUrl || ''
  recordedCode.value = ''
  detectedStartUrl.value = ''
  recordingId.value = null
  appliedGlobals.value = null
  stopPolling()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function startRecording() {
  starting.value = true
  try {
    const res = await recordingsApi.startRecording(startUrl.value.trim())
    recordingId.value = res.data.recording_id
    appliedGlobals.value = res.data.applied_globals || null
    phase.value = 'recording'
    startPolling()
  } catch (error) {
    ElMessage.error('启动录制失败')
    console.error(error)
  } finally {
    starting.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    if (!recordingId.value) return
    try {
      const res = await recordingsApi.getRecording(recordingId.value)
      const data = res.data
      if (data.status === 'completed') {
        stopPolling()
        recordedCode.value = data.code
        detectedStartUrl.value = data.detected_start_url
        phase.value = 'done'
      } else if (data.status === 'failed') {
        stopPolling()
        phase.value = 'input'
        ElMessage.error(data.error || '录制失败')
      }
    } catch (error) {
      console.error(error)
    }
  }, 2000)
}

async function stopRecording() {
  if (!recordingId.value) return
  stopPolling()
  try {
    await recordingsApi.stopRecording(recordingId.value)
  } catch (error) {
    console.error(error)
  }
  phase.value = 'input'
  recordingId.value = null
}

function applyCode() {
  if (!recordedCode.value) return
  emit('apply', {
    code: recordedCode.value,
    start_url: detectedStartUrl.value || startUrl.value.trim(),
  })
  dialogVisible.value = false
}

function handleClose() {
  stopPolling()
  dialogVisible.value = false
}

onBeforeUnmount(stopPolling)

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="录制脚本"
    width="60%"
    :close-on-click-modal="phase !== 'recording'"
    @close="handleClose"
  >
    <template v-if="phase === 'input'">
      <p class="record-hint">
        点击开始后将弹出浏览器窗口和 Playwright Inspector，在浏览器中的真实操作会被录制为
        Playwright 代码。操作完成后直接关闭浏览器窗口，录制的代码会自动回填到脚本编辑器。
      </p>
      <el-form label-width="90px">
        <el-form-item label="起始 URL">
          <el-input
            v-model="startUrl"
            placeholder="可选，例如：https://example.com/login（留空则从空白页开始）"
            @keyup.enter="startRecording"
          />
        </el-form-item>
      </el-form>
      <div class="record-actions">
        <el-button type="primary" :loading="starting" @click="startRecording">
          开始录制
        </el-button>
      </div>
    </template>

    <template v-else-if="phase === 'recording'">
      <div class="recording-status">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>录制中：请在弹出的浏览器窗口中操作，完成后关闭浏览器窗口</span>
      </div>
      <el-descriptions
        v-if="appliedGlobals"
        title="已携带的全局变量配置（按起始 URL 域名匹配）"
        :column="1"
        border
        size="small"
        class="applied-globals"
      >
        <el-descriptions-item label="公共 Header">
          {{ appliedGlobals.headers && Object.keys(appliedGlobals.headers).length ? Object.keys(appliedGlobals.headers).join('、') : '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="Cookie">
          {{ appliedGlobals.cookies && appliedGlobals.cookies.length ? appliedGlobals.cookies.map((c) => c.name).join('、') : '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="LocalStorage">
          {{ appliedGlobals.localStorage && Object.keys(appliedGlobals.localStorage).length ? Object.keys(appliedGlobals.localStorage).join('、') : '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="变量（GLOBAL_VARS）">
          {{ appliedGlobals.vars && Object.keys(appliedGlobals.vars).length ? Object.keys(appliedGlobals.vars).join('、') : '无' }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="record-actions">
        <el-button type="danger" @click="stopRecording">中止录制</el-button>
      </div>
    </template>

    <template v-else>
      <p class="record-hint">
        录制完成！以下为提取的代码片段（已去除包装代码，可直接在本平台运行）。
        <template v-if="detectedStartUrl">
          检测到起始 URL：<el-link type="primary" :underline="false">{{ detectedStartUrl }}</el-link>
        </template>
      </p>
      <el-input
        :model-value="recordedCode"
        type="textarea"
        :rows="14"
        readonly
        class="recorded-code"
      />
      <div class="record-actions">
        <el-button type="success" @click="applyCode">填入脚本编辑器</el-button>
        <el-button @click="phase = 'input'">重新录制</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.record-hint {
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
  margin: 0 0 15px 0;
}

.record-actions {
  margin-top: 15px;
}

.recording-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 0;
  color: #e6a23c;
}

.applied-globals {
  margin-top: 10px;
}

.recorded-code :deep(.el-textarea__inner) {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
}
</style>

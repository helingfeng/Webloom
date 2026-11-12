<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useScriptStore } from '@/stores/scriptStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { listCollectors } from '@/api/collectors'
import { ElMessage } from 'element-plus'
import { apiError } from '@/api/collectors'

const router = useRouter()
const scriptStore = useScriptStore()
const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()
const collectorTotal = ref<number | null>(null)

watch(
  () => wsStore.currentWorkspaceId,
  (id) => {
    scriptStore.fetchScripts(id ?? undefined)
    executionStore.fetchExecutions(1, id ?? undefined)
  },
  { immediate: true }
)
onMounted(async () => {
  try { collectorTotal.value = (await listCollectors()).data.total }
  catch (e) { ElMessage.error(apiError(e)) }
})

function navigateTo(path: string) { router.push(path) }
</script>

<template>
  <div>
    <h1>小鱼</h1>
    <p class="subtitle">
      通过 MCP 创作采集脚本，发布对外接口，查看采集任务与结果数据。
      <el-tag v-if="wsStore.currentWorkspace" size="small" style="margin-left: 8px">
        {{ wsStore.currentWorkspace.name }}
      </el-tag>
    </p>
    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/scripts')">
          <div class="stat-icon"><el-icon><Document /></el-icon></div>
          <div class="stat-number">{{ scriptStore.scripts.length }}</div>
          <div class="stat-label">当前空间采集脚本</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/collectors')">
          <div class="stat-icon"><el-icon><Connection /></el-icon></div>
          <div class="stat-number">{{ collectorTotal ?? '—' }}</div>
          <div class="stat-label">全部采集接口</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/executions')">
          <div class="stat-icon"><el-icon><List /></el-icon></div>
          <div class="stat-number">{{ executionStore.total }}</div>
          <div class="stat-label">当前范围执行记录</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card class="quick-actions">
      <template #header><span>快速入口</span></template>
      <el-button type="primary" @click="navigateTo('/mcp')">MCP 创作接入</el-button>
      <el-button @click="navigateTo('/scripts/new')">新建采集脚本</el-button>
      <el-button type="success" @click="navigateTo('/collectors')">发布采集接口</el-button>
      <el-button @click="navigateTo('/collector-tasks')">查看采集数据</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.subtitle { color: #666; margin-bottom: 30px; }
.stats-row { margin-bottom: 30px; }
.stat-card { text-align: center; cursor: pointer; transition: transform 0.2s; }
.stat-card:hover { transform: translateY(-5px); }
.stat-icon { font-size: 40px; color: #409eff; margin-bottom: 10px; }
.stat-number { font-size: 32px; font-weight: bold; color: #333; }
.stat-label { color: #666; margin-top: 5px; }
.quick-actions .el-button { margin: 0 15px 8px 0; }
</style>

<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useScriptStore } from '@/stores/scriptStore'
import { useFlowStore } from '@/stores/flowStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'

const router = useRouter()
const scriptStore = useScriptStore()
const flowStore = useFlowStore()
const executionStore = useExecutionStore()
const wsStore = useWorkspaceStore()

watch(
  () => wsStore.currentWorkspaceId,
  (id) => {
    scriptStore.fetchScripts(id ?? undefined)
    flowStore.fetchFlows(id ?? undefined)
    executionStore.fetchExecutions(1, id ?? undefined)
  },
  { immediate: true }
)

function navigateTo(path: string) {
  router.push(path)
}
</script>

<template>
  <div>
    <h1>小鱼</h1>
    <p class="subtitle">
      本地自动化测试与数据采集平台：基于 Playwright 的脚本编写与流程编排，配套数据源管理与 SQL 取数
      <el-tag v-if="wsStore.currentWorkspace" size="small" style="margin-left: 8px">
        {{ wsStore.currentWorkspace.name }}
      </el-tag>
    </p>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/scripts')">
          <div class="stat-icon"><el-icon><Document /></el-icon></div>
          <div class="stat-number">{{ scriptStore.scripts.length }}</div>
          <div class="stat-label">测试脚本</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/flows')">
          <div class="stat-icon"><el-icon><Share /></el-icon></div>
          <div class="stat-number">{{ flowStore.flows.length }}</div>
          <div class="stat-label">测试流程</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="stat-card" @click="navigateTo('/executions')">
          <div class="stat-icon"><el-icon><List /></el-icon></div>
          <div class="stat-number">{{ executionStore.executions.length }}</div>
          <div class="stat-label">执行记录</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="quick-actions">
      <template #header>
        <span>快速入口</span>
      </template>
      <el-button type="primary" @click="navigateTo('/scripts/new')">
        <el-icon><Plus /></el-icon> 新建脚本
      </el-button>
      <el-button type="success" @click="navigateTo('/flows/new')">
        <el-icon><Share /></el-icon> 新建流程
      </el-button>
      <el-button @click="navigateTo('/executions')">
        <el-icon><List /></el-icon> 查看执行记录
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.subtitle {
  color: #666;
  margin-bottom: 30px;
}

.stats-row {
  margin-bottom: 30px;
}

.stat-card {
  text-align: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-5px);
}

.stat-icon {
  font-size: 40px;
  color: #409eff;
  margin-bottom: 10px;
}

.stat-number {
  font-size: 32px;
  font-weight: bold;
  color: #333;
}

.stat-label {
  color: #666;
  margin-top: 5px;
}

.quick-actions .el-button {
  margin-right: 15px;
}
</style>

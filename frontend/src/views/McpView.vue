<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getMcpStatus, getBrowserSetting, updateBrowserSetting } from '@/api/mcp'
import type { BrowserSetting, McpStatus } from '@/types/mcp'
import { ElMessage } from 'element-plus'

const status = ref<McpStatus | null>(null)
const loading = ref(false)
const browserSetting = ref<BrowserSetting | null>(null)
const savingBrowser = ref(false)

const configJson = computed(() =>
  status.value ? JSON.stringify(status.value.client_config.mcp_servers_json, null, 2) : ''
)

onMounted(() => {
  fetchData()
})

async function fetchData() {
  loading.value = true
  try {
    const [statusRes, browserRes] = await Promise.all([getMcpStatus(), getBrowserSetting()])
    status.value = statusRes.data
    browserSetting.value = browserRes.data
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '获取 MCP 服务状态失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

async function toggleBrowser() {
  if (!browserSetting.value || savingBrowser.value) return false
  savingBrowser.value = true
  try {
    const { data } = await updateBrowserSetting(!browserSetting.value.cloakbrowser_enabled)
    browserSetting.value = data
    if (status.value) status.value.browser = data
    ElMessage.success(`已切换为 ${data.engine === 'cloakbrowser' ? 'CloakBrowser' : '标准 Playwright'}，下次启动浏览器时生效`)
    return false // 服务端返回成功后才更新显示值
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '保存浏览器设置失败')
    return false
  } finally {
    savingBrowser.value = false
  }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

</script>

<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>MCP 服务</h2>
      <el-button @click="fetchData">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="AgentHarness 连接 MCP 后即可探索网页、编写并保存采集脚本、运行验证。编写规范已内置在 MCP，无需单独安装 Skills。"
    />

    <el-alert v-if="status?.browser" :type="status.browser.ready ? 'info' : 'warning'" :closable="false" show-icon style="margin-bottom: 20px" :title="`浏览器引擎：${status.browser.engine} · ${status.browser.message}`" />

    <el-card v-if="browserSetting" style="margin-bottom: 20px">
      <template #header><span>采集浏览器</span></template>
      <div class="browser-toggle">
        <span>启用 CloakBrowser</span>
        <el-switch
          :model-value="browserSetting.cloakbrowser_enabled"
          :loading="savingBrowser"
          :disabled="!browserSetting.cloakbrowser_enabled && (!browserSetting.cloakbrowser_installed || !browserSetting.license_configured)"
          :before-change="toggleBrowser"
          aria-label="启用 CloakBrowser"
        />
      </div>
      <p class="hint-text">开启使用 CloakBrowser，关闭使用标准 Playwright。设置自动保存，适用于 MCP 探索、脚本试跑、正式采集和操作录制，无需重启服务。</p>
      <p class="hint-text">已打开的页面和正在运行的任务继续使用原引擎。许可证保存在服务器本机配置中，并发额度以授权计划为准。</p>
      <p v-if="status?.collection_policy" class="hint-text">
        低负载策略：同域主动访问间隔 {{ status.collection_policy.min_interval_seconds }} 秒，单次任务最多
        {{ status.collection_policy.max_requests }} 次导航/API/主动翻页操作；站点拒绝或限流后至少冷却
        {{ status.collection_policy.cooldown_seconds }} 秒，并遵守站点返回的更长等待时间。验证码需要人工处理。
      </p>
      <el-alert
        v-if="!browserSetting.cloakbrowser_installed || !browserSetting.license_configured"
        type="warning"
        :closable="false"
        title="启用前请先在服务器安装 CloakBrowser，并配置 CLOAKBROWSER_LICENSE_KEY。"
      />
    </el-card>

    <el-card v-if="status" style="margin-bottom: 20px">
      <template #header><span>服务状态</span></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="服务名">{{ status.server_name }}</el-descriptions-item>
        <el-descriptions-item label="传输协议">
          <el-tag size="small">{{ status.transport }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="端点（直连，推荐）">
          <code class="endpoint">{{ status.endpoint.direct }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="端点（前端代理）">
          <code class="endpoint">{{ status.endpoint.proxied }}</code>
          <span class="hint">仅前端开发态可用</span>
        </el-descriptions-item>
        <el-descriptions-item label="工具数量">
          <el-tag size="small" type="success">{{ status.tool_count }} 个</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="status" style="margin-bottom: 20px">
      <template #header>
        <div class="card-header">
          <span>客户端配置</span>
          <el-button size="small" @click="copyText(configJson)">复制 JSON</el-button>
        </div>
      </template>
      <h4 class="section-title">mcpServers 配置（Claude Code / Cursor 等）</h4>
      <pre class="code-block">{{ configJson }}</pre>
      <h4 class="section-title">Claude Code 命令行</h4>
      <pre class="code-block">{{ status.client_config.claude_cli_command }}</pre>
      <h4 class="section-title">Trae CLI 命令行</h4>
      <pre class="code-block">{{ status.client_config.trae_cli_command }}</pre>
    </el-card>

    <el-card v-if="status" style="margin-bottom: 20px">
      <template #header><span>MCP 工具</span></template>
      <el-table :data="status.tools" style="width: 100%">
        <el-table-column type="expand">
          <template #default="{ row }">
            <pre class="schema-block">{{ JSON.stringify(row.input_schema, null, 2) }}</pre>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="工具名" width="180" />
        <el-table-column prop="description" label="说明" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card>
      <template #header><span>脚本创作闭环</span></template>
      <el-steps :active="4" finish-status="success" simple>
        <el-step title="list_workspaces 选择空间" />
        <el-step title="inspect_page 探索页面" />
        <el-step title="create_script 保存脚本" />
        <el-step title="run_script 执行" />
        <el-step title="get_execution 读取结果" />
      </el-steps>
      <p class="hint-text">MCP 工具说明包含 Playwright 代码约定、登录态注入方式和采集稳定性建议。</p>
    </el-card>
  </div>
</template>

<style scoped>
.browser-toggle {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.endpoint {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  background-color: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
}

.hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.section-title {
  margin: 0 0 8px 0;
  color: #333;
  font-size: 13px;
}

.code-block,
.schema-block {
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 12px;
  margin: 0 0 12px 0;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}

.schema-block {
  margin: 8px 24px;
  max-height: 300px;
  overflow-y: auto;
}

.hint-text {
  margin: 0 0 12px 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}

</style>

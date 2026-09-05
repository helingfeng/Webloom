<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getMcpStatus, listAgentSkills, getAgentSkill, getSkillsInstallInfo } from '@/api/mcp'
import type {
  AgentSkillDetail,
  AgentSkillSummary,
  McpStatus,
  SkillInstallInfo,
} from '@/types/mcp'
import { ElMessage } from 'element-plus'

const status = ref<McpStatus | null>(null)
const skills = ref<AgentSkillSummary[]>([])
const installInfo = ref<SkillInstallInfo | null>(null)
const loading = ref(false)

const skillDialogVisible = ref(false)
const currentSkill = ref<AgentSkillDetail | null>(null)
const skillLoading = ref(false)

const configJson = computed(() =>
  status.value ? JSON.stringify(status.value.client_config.mcp_servers_json, null, 2) : ''
)

onMounted(() => {
  fetchData()
})

async function fetchData() {
  loading.value = true
  try {
    const [statusRes, skillsRes, installRes] = await Promise.all([
      getMcpStatus(),
      listAgentSkills(),
      getSkillsInstallInfo(),
    ])
    status.value = statusRes.data
    skills.value = skillsRes.data
    installInfo.value = installRes.data
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '获取 MCP 服务状态失败')
    console.error(error)
  } finally {
    loading.value = false
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

async function viewSkill(name: string) {
  skillDialogVisible.value = true
  skillLoading.value = true
  try {
    const res = await getAgentSkill(name)
    currentSkill.value = res.data
  } catch (error: any) {
    ElMessage.error('获取 Skill 内容失败')
    console.error(error)
  } finally {
    skillLoading.value = false
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
      title="脚本管理已封装为 MCP（Model Context Protocol）服务，AI 客户端（Claude Code / Cursor 等）可通过下方端点连接，使用配套 Skills 即可完成脚本的查询、编写、运行与维护。"
    />

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
      <template #header><span>Agent Skills</span></template>
      <el-table :data="skills" style="width: 100%">
        <el-table-column prop="name" label="名称" width="200" />
        <el-table-column prop="description" label="说明" show-overflow-tooltip />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" @click="viewSkill(row.name)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无 Skills</template>
      </el-table>

      <template v-if="installInfo">
        <h4 class="section-title" style="margin-top: 16px">安装到客户端</h4>
        <p class="hint-text">
          Skills 源目录：<code class="endpoint">{{ installInfo.source_dir }}</code
          >，格式为 <code class="endpoint">&lt;name&gt;/SKILL.md</code>，Claude Code 与 Trae CLI
          通用；将各 skill 目录复制到客户端对应 skills 目录即可被自动发现（或 /名称 手动调用）。
        </p>
        <el-table :data="installInfo.clients" style="width: 100%">
          <el-table-column prop="client" label="客户端" width="140" />
          <el-table-column label="安装目录" width="320">
            <template #default="{ row }">
              <div>用户级：<code class="endpoint">{{ row.user_dir }}</code></div>
              <div>项目级：<code class="endpoint">{{ row.project_dir }}</code></div>
            </template>
          </el-table-column>
          <el-table-column label="一键安装（用户级）">
            <template #default="{ row }">
              <div class="install-row">
                <pre class="code-block install-cmd">{{ row.command }}</pre>
                <el-button size="small" @click="copyText(row.command)">复制</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-dialog
      v-model="skillDialogVisible"
      :title="currentSkill?.name || 'Skill 内容'"
      width="720px"
      top="6vh"
    >
      <div v-loading="skillLoading">
        <pre v-if="currentSkill" class="skill-content">{{ currentSkill.content }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
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

.install-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.install-cmd {
  flex: 1;
  margin: 0;
}

.skill-content {
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 16px;
  margin: 0;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 65vh;
  overflow-y: auto;
}
</style>

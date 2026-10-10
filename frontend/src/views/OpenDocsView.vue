<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const activeTab = ref('auth')

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

const SIGN_CODE = `import hashlib
import hmac
import json
import time
import urllib.request

BASE_URL = "http://<平台地址>"        # 平台部署地址
APP_KEY = "fkxxxxxxxxxxxxxxxx"
APP_SECRET = "你的 App Secret"


def call_open_api(method: str, path: str, body: dict | None = None,
                  query: str = "") -> dict:
    """调用小鱼开放接口。

    注意：签名只覆盖 path（不含 query）；query 通过参数单独拼接。
    """
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    ts = str(int(time.time()))
    canonical = f"{method}\\n{path}\\n{ts}\\n{hashlib.sha256(raw).hexdigest()}"
    sign = hmac.new(APP_SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    url = BASE_URL + path + (f"?{query}" if query else "")
    req = urllib.request.Request(
        url,
        data=raw if raw else None,
        method=method,
        headers={
            "X-App-Key": APP_KEY,
            "X-Timestamp": ts,
            "X-Sign": sign,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


# 1) 传入链接发起采集（异步，立即返回 execution_id）
result = call_open_api(
    "POST",
    "/open/api/v1/collect/trigger",
    body={"url": "https://example.com/post/123", "script_id": 9},
)
execution_id = result["execution_id"]

# 2) 轮询采集结果（建议 3-5 秒一次，直到 finished=true）
#    query 不参与签名，通过 query 参数传入
result = call_open_api(
    "GET", "/open/api/v1/collect/result",
    query=f"execution_id={execution_id}",
)
print(result["status"], result["outputs"])`

const TRIGGER_EXAMPLE = `POST /open/api/v1/collect/trigger

{
  "url": "https://club.autohome.com.cn/bbs/thread/xxx.html",
  "script_id": 9,
  "inputs": { "keyword": "可选的附加输入" },
  "headless": true
}

200 响应：
{
  "execution_id": 56,
  "status": "pending",
  "next": "GET /open/api/v1/collect/result?execution_id=56"
}`

const RESULT_EXAMPLE = `GET /open/api/v1/collect/result?execution_id=56

200 响应（执行中）：
{
  "execution_id": 56,
  "script_id": 9,
  "status": "running",
  "finished": false,
  "outputs": {},
  "started_at": "2026-10-10 15:30:00",
  "finished_at": null
}

200 响应（完成）：
{
  "execution_id": 56,
  "script_id": 9,
  "status": "success",
  "finished": true,
  "outputs": {
    "title": "帖子标题",
    "read_count": 103,
    "content_chars": 652
  },
  "started_at": "2026-10-10 15:30:00",
  "finished_at": "2026-10-10 15:30:08"
}`

const TASKS_EXAMPLE = `GET /open/api/v1/collect/tasks?script_id=9&limit=10

200 响应：
{
  "items": [
    { "execution_id": 56, "script_id": 9, "status": "success",
      "finished": true, "started_at": "...", "finished_at": "..." }
  ],
  "total": 1
}`

const PROXY_EXAMPLE = `# 管理端「开放接口」页配置一条代理规则：
#   方法：GET
#   外部路径：/v1/executions/{execution_id}
#   内部目标：/api/executions/{execution_id}
#
# 外部即可这样调用（同样需要签名）：
GET /open/v1/executions/56

# 平台会把请求转发到内部 GET /api/executions/56 并透传响应，
# 路径中的 {execution_id} 会自动替换；query 参数原样透传。`
</script>

<template>
  <div>
    <div class="page-header">
      <h2>开放接口接入文档</h2>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="所有开放接口均为 Server-to-Server 调用（/open 前缀），需先在「开放应用」创建凭证，并按下方签名算法携带认证头。"
    />

    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="签名认证" name="auth">
          <h3>认证头</h3>
          <el-table :data="[
            { name: 'X-App-Key', desc: '开放应用的 App Key' },
            { name: 'X-Timestamp', desc: 'Unix 秒级时间戳，与服务器偏差超过 300 秒拒绝' },
            { name: 'X-Sign', desc: 'HMAC-SHA256 签名（小写 hex）' },
          ]" style="margin-bottom: 16px">
            <el-table-column prop="name" label="Header" width="160" />
            <el-table-column prop="desc" label="说明" />
          </el-table>

          <h3>签名算法</h3>
          <pre class="code-block">canonical = "{METHOD}\n{path}\n{timestamp}\n{sha256_hex(body)}"
X-Sign    = HMAC_SHA256(app_secret, canonical).hexdigest()

# METHOD：HTTP 方法大写（GET/POST/...）
# path：完整请求路径，含 /open 前缀，不含 query（如 /open/api/v1/collect/trigger）
# query：不参与签名，直接拼在 URL 上（如 ?execution_id=56）
# timestamp：与 X-Timestamp 相同的 Unix 秒
# sha256_hex(body)：请求体字节的 SHA-256 小写 hex（GET/无请求体时为空串的哈希）</pre>

          <h3>完整调用示例（Python）</h3>
          <div class="code-wrap">
            <el-button class="copy-btn" size="small" @click="copyText(SIGN_CODE)">复制</el-button>
            <pre class="code-block">{{ SIGN_CODE }}</pre>
          </div>
        </el-tab-pane>

        <el-tab-pane label="发起采集" name="trigger">
          <p>传入目标链接与采集脚本 ID，异步发起执行，立即返回 <code>execution_id</code>。脚本会以 <code>inputs.url = 链接</code> 执行（脚本需定义 url 输入变量）。</p>
          <div class="code-wrap">
            <el-button class="copy-btn" size="small" @click="copyText(TRIGGER_EXAMPLE)">复制</el-button>
            <pre class="code-block">{{ TRIGGER_EXAMPLE }}</pre>
          </div>
        </el-tab-pane>

        <el-tab-pane label="查询结果" name="result">
          <p>按 <code>execution_id</code> 查询采集结果。只能查询本应用触发的执行。建议 3-5 秒轮询一次直到 <code>finished=true</code>（脚本超时 120 秒，排队时间另计）。</p>
          <div class="code-wrap">
            <el-button class="copy-btn" size="small" @click="copyText(RESULT_EXAMPLE)">复制</el-button>
            <pre class="code-block">{{ RESULT_EXAMPLE }}</pre>
          </div>
        </el-tab-pane>

        <el-tab-pane label="任务列表" name="tasks">
          <p>查看本应用最近触发的采集任务（最多 50 条，新→旧），可按 <code>script_id</code> 过滤。</p>
          <div class="code-wrap">
            <el-button class="copy-btn" size="small" @click="copyText(TASKS_EXAMPLE)">复制</el-button>
            <pre class="code-block">{{ TASKS_EXAMPLE }}</pre>
          </div>
        </el-tab-pane>

        <el-tab-pane label="代理接口" name="proxy">
          <p>在「开放接口」页可以把平台内部 <code>/api/**</code> 接口封装成开放接口（服务端转发，外部不接触平台内部端口）。</p>
          <div class="code-wrap">
            <el-button class="copy-btn" size="small" @click="copyText(PROXY_EXAMPLE)">复制</el-button>
            <pre class="code-block">{{ PROXY_EXAMPLE }}</pre>
          </div>
        </el-tab-pane>

        <el-tab-pane label="错误码" name="errors">
          <el-table :data="[
            { code: 400, desc: '请求参数错误（缺 url / script_id 非法等）' },
            { code: 401, desc: '认证失败：缺少认证头 / 时间戳超限 / 签名错误 / 应用不存在或已停用' },
            { code: 404, desc: '脚本或接口不存在；查询他人应用的执行' },
            { code: 502, desc: '代理转发时平台内部服务异常' },
            { code: 503, desc: '执行队列不可用（Redis / worker 未启动）' },
          ]">
            <el-table-column prop="code" label="状态码" width="100" />
            <el-table-column prop="desc" label="说明" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.code-wrap {
  position: relative;
}

.copy-btn {
  position: absolute;
  right: 8px;
  top: 8px;
  z-index: 1;
}

.code-block {
  background: #282c34;
  color: #abb2bf;
  border-radius: 6px;
  padding: 16px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre;
}

h3 {
  margin: 16px 0 8px;
}

p {
  margin: 8px 0 12px;
  color: #606266;
}

code {
  background: #f0f2f5;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 13px;
}
</style>

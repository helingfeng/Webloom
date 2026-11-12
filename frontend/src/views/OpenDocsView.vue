<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const activeTab = ref('start')
const endpoints = [
  { method: 'GET', path: '/open/v1/collectors', description: '查看本应用可调用的接口与参数契约', params: 'skip=0，limit=20（1–100）' },
  { method: 'GET', path: '/open/v1/collectors/{slug}', description: '查看指定接口的输入 schema、输出定义和请求示例', params: 'slug 为发布时设置的接口标识' },
  { method: 'POST', path: '/open/v1/collectors/{slug}/runs', description: '提交采集任务，返回结果查询地址', params: 'JSON：inputs、wait_seconds（0–20，默认 0）' },
  { method: 'GET', path: '/open/v1/tasks', description: '分页查询本应用提交的任务', params: 'skip=0，limit=20（1–100）；可选 collector_id、status' },
  { method: 'GET', path: '/open/v1/tasks/{execution_id}', description: '查询状态、失败原因和完整 outputs', params: 'wait_seconds=0（0–20）' },
  { method: 'GET', path: '/open/v1/tasks/{execution_id}/data', description: '按输出字段分页读取或导出数据', params: 'field、skip=0、limit=100（1–1000）、format=json 或 csv' },
]
const statuses = [
  { status: 'pending', finished: 'false', meaning: '任务已提交，等待 worker 执行' },
  { status: 'running', finished: 'false', meaning: '正在采集，继续查询结果' },
  { status: 'success', finished: 'true', meaning: '采集完成，可读取 outputs 或导出数据' },
  { status: 'failed', finished: 'true', meaning: '采集失败，查看 error；重新执行需使用新的幂等键' },
]
const errors = [
  { code: 400, meaning: '参数缺失、类型错误、传入未声明参数等', action: '按该接口 input_schema 修改 inputs' },
  { code: 401, meaning: '凭证无效、应用停用或密钥已重置', action: '检查完整调用凭证，联系发布者确认应用状态' },
  { code: 404, meaning: '接口未发布、未授权，或任务不存在 / 不属于本应用', action: '确认 slug、execution_id 和应用授权' },
  { code: 409, meaning: '幂等键用于不同请求，或采集尚未成功就请求 CSV', action: '新请求使用新键；导出前等待 status=success' },
  { code: 422, meaning: '请求结构或分页、等待时间等参数超出范围', action: '读取 detail 中的字段位置和错误说明' },
  { code: 503, meaning: '执行队列暂不可用', action: '稍后重试，并在任务列表检查失败留痕；失败任务重新执行需换新键' },
]

const CURL_EXAMPLE = `# 修改为实际服务地址、完整调用凭证和已发布的接口标识
BASE_URL='http://127.0.0.1:8000'
FISHCODE_TOKEN='<APP_KEY>.<APP_SECRET>'
COLLECTOR_SLUG='page-summary-demo'
REQUEST_KEY='collection-001'

# 1. 查看接口参数与请求示例
curl "$BASE_URL/open/v1/collectors/$COLLECTOR_SLUG" \\
  -H "Authorization: Bearer $FISHCODE_TOKEN"

# 2. 提交采集：inputs 必须按上一步返回的 input_schema 填写
curl -i -X POST "$BASE_URL/open/v1/collectors/$COLLECTOR_SLUG/runs" \\
  -H "Authorization: Bearer $FISHCODE_TOKEN" \\
  -H 'Content-Type: application/json' \\
  -H "Idempotency-Key: $REQUEST_KEY" \\
  --data '{"inputs":{"url":"https://example.com"},"wait_seconds":0}'

# 3. 将执行 ID 替换为提交响应中的 execution_id
curl "$BASE_URL/open/v1/tasks/99?wait_seconds=20" \\
  -H "Authorization: Bearer $FISHCODE_TOKEN"`

const PYTHON_EXAMPLE = `# 使用 Python 标准库；先设置 FISHCODE_TOKEN 环境变量
import json
import os
import time
import uuid
import urllib.request

base = os.environ.get("FISHCODE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
token = os.environ["FISHCODE_TOKEN"]  # App Key.App Secret
slug = "page-summary-demo"          # 替换为已发布的接口标识


def call(method, path, body=None, request_key=None):
    headers = {"Authorization": "Bearer " + token}
    raw = None
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if request_key:
        headers["Idempotency-Key"] = request_key
    request = urllib.request.Request(base + path, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


# 同一次提交遇到网络超时，保留 request_key 和请求参数后重试；新采集生成新键
request_key = str(uuid.uuid4())
task = call("POST", f"/open/v1/collectors/{slug}/runs",
            {"inputs": {"url": "https://example.com"}, "wait_seconds": 0},
            request_key=request_key)
deadline = time.monotonic() + 180
while not task["finished"]:
    if time.monotonic() >= deadline:
        raise TimeoutError("任务仍在处理，请稍后继续查询：" + task["result_url"])
    time.sleep(2)
    task = call("GET", task["result_url"] + "?wait_seconds=20")

if task["status"] != "success":
    raise RuntimeError(task["error"])
print(json.dumps(task["outputs"], ensure_ascii=False, indent=2))`

const RESPONSE_EXAMPLE = `# 提交后未完成：HTTP 202；查询结果时返回 HTTP 200
# 提交设置 wait_seconds 且等待期间已完成：HTTP 200
{
  "execution_id": 99,
  "status": "pending",
  "finished": false,
  "error": null,
  "outputs": {},
  "result_url": "/open/v1/tasks/99",
  "data_url": "/open/v1/tasks/99/data"
}

# 采集完成：关键字段示例
{
  "execution_id": 99,
  "status": "success",
  "finished": true,
  "error": null,
  "outputs": {
    "items": [
      {"text": "示例链接 A", "url": "https://example.com/a"},
      {"text": "示例链接 B", "url": "https://example.com/b"}
    ]
  },
  "result_url": "/open/v1/tasks/99",
  "data_url": "/open/v1/tasks/99/data"
}`

const DATA_EXAMPLE = `# 所有请求均携带 Authorization: Bearer <APP_KEY>.<APP_SECRET>
GET /open/v1/tasks/99/data?field=items&skip=0&limit=100

{
  "status": "success",
  "finished": true,
  "error": null,
  "field": "items",
  "fields": ["items"],
  "columns": ["text", "url"],
  "items": [{"text": "示例链接 A", "url": "https://example.com/a"}],
  "total": 1,
  "skip": 0,
  "limit": 100
}

# CSV 下载当前分页，完整数据需要逐页读取
GET /open/v1/tasks/99/data?field=items&skip=0&limit=1000&format=csv

# 查询自己的失败任务
GET /open/v1/tasks?status=failed&skip=0&limit=20`

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}
</script>

<template>
  <div class="docs">
    <div class="page-header">
      <div>
        <h2>开放接口接入文档</h2>
        <p>获取凭证，调用已发布的采集接口，再查询和下载采集结果。</p>
      </div>
      <router-link to="/collection-portal"><el-button type="primary">打开调用体验页</el-button></router-link>
    </div>

    <el-alert
      title="使用 Authorization: Bearer <APP_KEY>.<APP_SECRET> 调用 /open/v1 接口。每个接口的实际输入、输出和专属示例，请在「采集接口 → 接入 / 调试」查看。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="快速接入" name="start">
          <ol>
            <li>发布者在 <router-link to="/open-apps">开放应用</router-link> 创建应用，并在凭证详情复制完整调用凭证。</li>
            <li>在 <router-link to="/collectors">采集接口</router-link> 选择脚本、填写接口标识并授权该应用，保存发布。</li>
            <li>调用方查看接口参数，提交 <code>inputs</code>；根据返回的 <code>result_url</code> 查询到 <code>finished=true</code>。</li>
            <li>确认 <code>status=success</code> 后读取 <code>outputs</code>，或通过 <code>data_url</code> 分页取数、导出 CSV。</li>
          </ol>
          <p>无需编程时可使用调用体验页。它只展示当前应用获授权的接口和自己提交的任务；凭证仅保留在页面内存中。</p>
          <h3>cURL 示例 <el-button link type="primary" @click="copyText(CURL_EXAMPLE)">复制</el-button></h3>
          <pre>{{ CURL_EXAMPLE }}</pre>
          <p>示例使用网页标题与链接接口的 <code>url</code> 参数。其他接口请按实际 schema 填写，不需要传入内部脚本 ID。</p>
          <h3>Python：提交并等待结果 <el-button link type="primary" @click="copyText(PYTHON_EXAMPLE)">复制</el-button></h3>
          <pre>{{ PYTHON_EXAMPLE }}</pre>
          <p>服务地址应是调用方可访问的地址。对外接入使用 HTTPS；应用停用或重新生成密钥后，旧凭证立即失效。</p>
        </el-tab-pane>

        <el-tab-pane label="接口与参数" name="endpoints">
          <el-table :data="endpoints" border>
            <el-table-column prop="method" label="方法" width="85" />
            <el-table-column prop="path" label="地址" min-width="300" />
            <el-table-column prop="description" label="用途" min-width="220" />
            <el-table-column prop="params" label="参数" min-width="260" />
          </el-table>
          <h3>输入参数</h3>
          <p><code>inputs</code> 中的参数名、类型、必填项和默认值以接口返回的 <code>input_schema</code> 为准。支持字符串、数字、布尔值；未声明参数、错误类型、缺少必填值会被拒绝。显式传入的值覆盖默认值。</p>
          <p><code>slug</code> 是发布者设置的稳定接口标识；<code>execution_id</code> 是提交后返回的执行 ID；<code>collector_id</code> 是接口目录返回的接口 ID，用于筛选任务。</p>
          <h3>幂等提交与网络重试</h3>
          <p>提交时可携带 <code>Idempotency-Key</code>（最长 128 字符）。同一应用以相同键、相同接口和相同参数重试，会返回同一任务。相同键用于不同接口或参数返回 409。每次新采集使用新键；已失败的任务重新执行也需要新键。</p>
          <p><code>wait_seconds</code> 控制单次请求最多等待多久，不是脚本执行超时。等待结束后仍未完成，继续使用同一结果地址查询即可。</p>
          <p>应用只能查看自己提交的任务。接口停用、移除或撤销授权会阻止新提交，原应用仍可查询历史任务；停用整个应用会阻止其全部访问。</p>
        </el-tab-pane>

        <el-tab-pane label="结果与数据导出" name="results">
          <el-alert title="HTTP 202 表示已受理，HTTP 200 表示请求成功。只有任务 status=success 才表示采集成功；finished=true 也可能是 failed。" type="info" :closable="false" />
          <el-table :data="statuses" border>
            <el-table-column prop="status" label="status" width="120" />
            <el-table-column prop="finished" label="finished" width="100" />
            <el-table-column prop="meaning" label="含义" />
          </el-table>
          <h3>任务响应 <el-button link type="primary" @click="copyText(RESPONSE_EXAMPLE)">复制</el-button></h3>
          <pre>{{ RESPONSE_EXAMPLE }}</pre>
          <p>未完成的提交响应还包含 <code>Location</code> 结果地址和 <code>Retry-After: 2</code>。任务失败时读取 <code>error</code>；发布者可在 <router-link to="/collector-tasks">采集任务与数据</router-link> 查看完整执行日志。</p>
          <h3>分页取数与 CSV <el-button link type="primary" @click="copyText(DATA_EXAMPLE)">复制</el-button></h3>
          <pre>{{ DATA_EXAMPLE }}</pre>
          <p><code>field</code> 是 outputs 中要读取的字段；未指定时优先选择列表字段。列表元素为对象时按属性生成表格，标量包装为 <code>{value: ...}</code>。通过返回的 <code>fields</code> 切换输出字段。</p>
          <p><code>skip</code> 从 0 开始，每次增加本页条数，直到达到 <code>total</code>。CSV 仅导出当前分页，要求任务已成功；获取全部数据时遍历分页或读取任务的完整 outputs。界面中的 CSV 导出所选字段的全部行，JSON 导出完整 outputs。</p>
          <p>清空调用日志不会删除这些任务和结果。执行记录及其数据仍需由发布者按实际保留策略管理。</p>
        </el-tab-pane>

        <el-tab-pane label="错误处理" name="errors">
          <el-table :data="errors" border>
            <el-table-column prop="code" label="HTTP 状态" width="110" />
            <el-table-column prop="meaning" label="原因" min-width="230" />
            <el-table-column prop="action" label="处理建议" min-width="280" />
          </el-table>
          <p>接口请求失败返回 JSON <code>detail</code>，例如 <code>{"detail":"缺少必填参数: url"}</code>。422 的 detail 为字段错误列表。后台任务失败则通过结果中的 <code>status=failed</code> 和 <code>error</code> 表达。</p>
          <p>遇到提交请求超时，使用原幂等键和原参数重试，避免重复采集。遇到等待结果超时，保留 execution_id 或 result_url，稍后继续查询；客户端超时不会取消后台任务。</p>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 20px; }
h2 { margin: 0 0 8px; }
h3 { margin: 24px 0 12px; }
p, li { color: #606266; line-height: 1.8; }
li { margin-bottom: 8px; }
.el-alert { margin-bottom: 20px; }
pre { background: #f6f8fa; padding: 18px; border-radius: 6px; font-size: 13px; line-height: 1.7; overflow-x: auto; }
code { background: #f0f2f5; padding: 2px 5px; border-radius: 3px; }
</style>

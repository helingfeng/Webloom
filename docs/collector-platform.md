# 采集接口发布与外部调用

主路径为：MCP 创作并验证脚本 → 发布采集接口 → 授权外部应用 → 调用与查询数据。

## 发布

1. 脚本列表点击「发布接口」，或进入「开放平台 → 采集接口」。选择脚本并填写名称、稳定标识（如 `product-search`）、说明和授权应用。
2. 保存发布后，接口地址为 `POST /open/v1/collectors/product-search/runs`。调用方只需知道接口标识和参数。
3. 「接入 / 调试」自动展示当前脚本的参数与输出定义，并生成 cURL 和 Python 轮询示例；在线调试产生真实任务。
4. 「采集任务与数据」按接口、应用和状态筛选任务，查看结果表格、完整 JSON、失败原因和执行日志，导出 CSV 或 JSON。

脚本输入定义是接口的参数契约；接口拒绝未声明参数、错误类型和缺失必填值。默认值在执行时合并，显式输入优先；数字和布尔值必须使用 JSON 原生类型，未填写的可选参数应省略，而不是传空字符串。采集可变 URL 的脚本应使用 `await page.goto(INPUTS.get("url", START_URL), wait_until="domcontentloaded")`，而不是只访问固定的 START_URL。

接口发布后 slug 不可修改，可停用、修改说明与授权应用或更换绑定脚本。接口列表支持「移除」：移除后不再显示，也不再接受新调用；已提交的任务继续执行，历史任务和结果保留。标识仍被保留，重新发布请使用新标识。未移除接口绑定的脚本不能直接删除，需先更换脚本或移除接口。脚本更新会影响后续新提交的采集任务；已入队任务使用提交时的代码与运行配置快照。目前不提供独立发布版本。

## 调用

应用详情可查看 App Key 和 App Secret。使用 `Authorization: Bearer <App Key>.<App Secret>`，也兼容现有 HMAC 请求签名。Bearer 凭证通过 HTTPS 传输，建议存放在调用方服务端。应用停用或重新生成密钥后，旧凭证立即失效。

```bash
curl -X POST 'http://127.0.0.1:8000/open/v1/collectors/product-search/runs' \
  -H 'Authorization: Bearer <APP_KEY>.<APP_SECRET>' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: a-unique-id-for-this-collection' \
  --data '{"inputs":{"url":"https://example.com"},"wait_seconds":0}'
```

202 表示已受理，响应给出 `execution_id`、`result_url`、`data_url`。查询 result_url 到 `finished=true`；`status=success` 才表示采集完成，`failed` 时读取 `error`。GET 结果或 POST 提交均可设置 `wait_seconds`（0–20 秒），适用于短任务和减少轮询。HTTP 提交成功不等于后台采集成功。

同一应用用相同 `Idempotency-Key` 重试相同接口及参数，返回同一任务，不重复入队；键用于不同参数或不同接口返回 409。新的采集请求使用新键。幂等记录和任务持久保存，不随日志清空而删除。队列提交失败返回 503，失败记录仍可在任务列表看到；要重新执行已失败的任务，需要新的幂等键。

- `GET /open/v1/collectors`：本应用可调用的已发布接口，含参数 schema 和示例，skip/limit 分页。
- `GET /open/v1/collectors/{slug}`：单个接口的调用契约。
- `GET /open/v1/tasks`：本应用任务，skip/limit、collector_id、status 过滤，返回准确 total。
- `GET /open/v1/tasks/{execution_id}`：任务状态和完整 outputs；不返回内部输入、完整执行日志或脚本代码。
- `GET /open/v1/tasks/{execution_id}/data?field=items&skip=0&limit=100`：按输出字段读取表格，返回字段列表、列名、行数据和准确 total。标量包装为 `{value: ...}`。
- 相同 data 地址加 `format=csv` 下载当前分页，数据 limit 上限 1000。全部数据可遍历分页，或者读取完整 outputs。管理界面 CSV 导出所选输出字段全部数据，JSON 导出完整 outputs。

错误使用 HTTP 状态码和 JSON `detail`：400 参数错误、401 凭证无效、404 资源不存在或无权访问、409 幂等键冲突/接口契约冲突、422 请求结构不合法、503 队列不可用。

## 调用体验页

`/collection-portal` 是独立于管理导航的调用页，只请求 `/open/v1/*`。调用方输入凭证后能查看获授权接口、通过类型化参数表单发起任务、查询自己的任务和下载数据。凭证只存在页面内存，刷新或退出后清除；不通过 URL 或本地存储保存凭证。

本地访问 `http://127.0.0.1:5173/collection-portal`，Vite 已配置 /open 代理。外部部署时需配置真实可达的域名、HTTPS 和前端静态托管；网关仅暴露 /open、调用体验页及所需静态资源，管理 /api、MCP 以及数据库留在内部网络。开发服务器默认仅监听本机；外部部署需要单独配置域名、HTTPS 与网关。

## 权限与任务保留

应用只能查看自己提交的任务。接口停用或撤销授权会阻止新的提交，原应用仍可查看自己的历史任务；停用整个应用会阻止其全部外部访问。清空调用日志不删除这些任务和结果，执行记录及其数据由发布者按实际保留策略管理。

新版接入统一使用本指南中的 `/open/v1/collectors` 与 `/open/v1/tasks`。平台保留的兼容功能不在此指南中作为新接入方案。开发实现与内部模块约定见 [AGENTS.md](../AGENTS.md)。

## MCP 发布闭环

AgentHarness 可以使用 `list_open_apps` 获取应用 ID（不含密钥）、`list_published_collectors` 检查已有接口、`publish_collector` 将已验证脚本发布或更新接口。完整工具调用规范内置 MCP instructions，不需要额外 Skills。只有用户要求对外提供接口时才发布，单纯创作脚本不会自动开放。

本机示例「网页标题与链接」的接口标识为 `page-summary-demo`，授权给「采集接口示例应用」。可在应用详情复制凭证，通过调用体验页提交网页 URL；新部署环境请替换为自己已发布的接口标识和实际输入参数。

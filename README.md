# 小鱼（fishCode）

以 MCP 为主入口的网页数据采集平台：AgentHarness 根据提示词探索网页、编写和验证 Playwright Python 脚本，保存后可发布成对外采集接口。脚本创作规范内置 MCP，无需额外 Skills。

## 使用流程

1. AgentHarness 连接 `http://127.0.0.1:8000/mcp`，完成页面探索、脚本试跑和保存。
2. 在脚本列表点击「发布接口」，选择授权应用并设置稳定的接口标识。
3. 外部系统使用 Bearer 凭证调用接口，查询任务结果并分页读取数据。
4. 在平台查看采集状态、失败原因、执行日志和结果表格，导出 CSV 或 JSON。

| 页面 | 用途 |
|---|---|
| `/mcp` | MCP 接入与工具列表 |
| `/scripts` | 脚本管理与运行 |
| `/collectors` | 发布接口、查看参数与调用示例、在线调试 |
| `/collector-tasks` | 采集任务、结果数据与日志 |
| `/open-apps` | 应用凭证与启停管理 |
| `/open-docs` | 开放接口接入文档 |
| `/collection-portal` | 独立调用体验页：输入凭证后调用获授权接口 |

完整的外部调用契约见 [采集接口接入指南](docs/collector-platform.md)。开发分层、执行引擎、数据源及原有管理功能见 [AGENTS.md](AGENTS.md)。

## 环境与安装

需要 Python 3.13、Node.js `^22.18.0` 或 `>=24.12.0`、MySQL 8。持久任务执行需要 Redis；API 与唯一 worker 使用相同的 `REDIS_URL`。

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
cp -n .env.example .env
```

编辑 `backend/.env`，配置 `DATABASE_URL` 和 `REDIS_URL`。Redis 使用密码时，URL 格式为 `redis://:<密码>@127.0.0.1:6379/0`；特殊字符需做 URL 编码。不要覆盖已有的本机配置或提交真实凭证。

先创建 MySQL 数据库：

```bash
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS fishcode DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

服务启动时自动建表和执行幂等补列迁移；建表参考为 `backend/mysql_ddl.sql`。MySQL DSN 驱动应使用 `mysql+aiomysql://`。

## 启动

### 完整平台

确保 MySQL 和配置中的 Redis 已启动，然后分别在三个终端运行：

```bash
# 后端 API 与 MCP
cd backend
./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# 唯一执行 worker：修改后端执行代码后手动重启
cd backend
./venv/bin/python -m app.worker
```

```bash
# 前端
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5173`。前端代理 `/api`（含 WebSocket）、`/open`、`/mcp`、`/storage` 到后端。检查 `GET http://127.0.0.1:8000/api/health`，队列应显示 `available=true`、`worker_alive=true`。

### 仅 MCP 创作

只探索、试跑和保存脚本时，可使用最小入口，不需要前端、Redis 或 worker，仍需要 MySQL：

```bash
cd backend
./venv/bin/python -m uvicorn app.mcp_main:app --host 127.0.0.1 --port 8000
```

此入口与完整后端二选一使用同一端口。AgentHarness 配置：

```json
{"mcpServers":{"fishcode-scripts":{"url":"http://127.0.0.1:8000/mcp"}}}
```

创作链路为 `open_page` / `browse_page` → `preview_script` → `create_script` / `update_script` → `close_page`。探索会话最多 4 个，空闲 10 分钟回收；试跑使用独立浏览器，代码须包含完整导航与采集步骤。启动单个 MCP 进程，避免会话分散。

用户要求发布接口时，Agent 可用 `list_open_apps`、`list_published_collectors`、`publish_collector` 完成发布，不经 MCP 回传应用密钥。`run_script` 和已发布接口的持久任务仍需 Redis 与 worker；使用 DATA_VIEWS 的脚本也通过持久任务验证。

## 开发检查

```bash
# backend 目录；浏览器测试需已安装 Chromium
./venv/bin/python -m pytest tests/ -q

# frontend 目录
npm run build
npm run test:unit -- --run
```

新增模型或修改模型后，运行 `backend/scripts/gen_mysql_ddl.py` 更新 DDL。更多开发约定以 AGENTS.md 为准。

## 对外部署

对外提供 `/open` API、调用体验页及其静态资源，配置可访问的域名和 HTTPS；管理 `/api`、MCP、数据库与 Redis 留在内部网络。当前启动命令仅监听本机。页面访问权限、登录失效和验证码等限制需要按实际站点处理。

## 脚本参数与全局配置

脚本编辑器使用数字、布尔和密码控件；调试参数留空时使用默认值，运行前自动保存当前编辑内容。排队任务保存代码与运行配置快照，后续编辑不影响已提交任务。页面默认真实输入运行，Mock 仅保留旧 API 的显式兼容。

全局变量可按名称、域名和类型筛选。列表不返回明文；编辑默认保留原值，可主动读取、替换或清空。作用域支持域名、子域及完整网页 URL（保存为主机名并忽略端口），运行输入中的 url 优先于脚本默认 URL。覆盖顺序为运行输入 > 具体域 > 父域 > 通用配置；localStorage 在目标页面脚本执行前写入。

## CloakBrowser 引擎

探索、试跑、持久执行和操作录制共用浏览器适配层，采集脚本仍使用原有 Playwright API，无需改写。依赖固定为 CloakBrowser 0.7.2 与兼容的 Playwright 1.64.1。安装依赖后，在 backend/.env 配置：

```dotenv
BROWSER_ENGINE=cloakbrowser
CLOAKBROWSER_LICENSE_KEY=cb_your_key
CLOAKBROWSER_HUMANIZE=true
# 可选，使用自己已有的代理
# CLOAKBROWSER_PROXY_URL=http://user:password@proxy.example:8080
# CLOAKBROWSER_LOCALE=zh-CN
# CLOAKBROWSER_TIMEZONE=Asia/Shanghai
```

官方当前版本每次启动均需许可证；可通过官方 `cloakbrowser login` 获取/保存授权，或自行将密钥写入 .env。首次授权启动自动下载独立浏览器二进制（约 200 MB），建议先在 backend 目录运行 `./venv/bin/python -m cloakbrowser install` 预下载，避免第一次采集被下载耗时影响。安装命令也需要已配置的授权；.env 中的密钥可由平台设置读取，官方 CLI 则读取导出的环境变量或其登录缓存。

首次配置许可证等环境项后重启 API 与唯一 worker。在后台「MCP 服务 → 采集浏览器」可随时开启或关闭 CloakBrowser，自动保存到平台数据库，无需重启。新建探索页面、试跑、正式任务和录制启动时读取最新开关；已打开页面与运行中的任务继续使用原引擎。关闭时使用标准 Playwright。

数据库开关优先于 `BROWSER_ENGINE`，首次尚未保存时使用该环境默认值（缺省为 Playwright）。管理端 `GET/PUT /api/mcp/browser-settings` 读取/保存开关，PUT 请求体为 `{"cloakbrowser_enabled": true}`；不通过此接口读取或修改许可证。MCP 页面和 `/api/health` 显示所选引擎与配置条件；该状态不等于二进制已安装或许可证已通过远端校验。缺少 SDK/许可证时拒绝开启；实际启动失败显式报错，不自动降级。

免费授权当前允许单个并发浏览器；平台的 worker 并发、探索会话和试跑也共享同一授权额度，按自己的授权计划安排并发，单并发时探索后先关闭页面再试跑。CloakBrowser 可以减少部分自动化特征，但不保证绕过验证码、IP 限制或站点权限。[官方说明](https://github.com/CloakHQ/CloakBrowser)。

## 低负载采集流程

探索、录制、试跑和正式任务共用浏览器上下文初始化，Cookie、Header 与首屏 localStorage 的注入方式一致。在同一个任务中复用 context 和 page，避免重复登录、清空 Cookie 或逐条重新启动浏览器。任务之间不自动共享用户凭证快照，登录态以平台按域名配置为准。

内置 `page.goto/reload/go_back/go_forward` 具有主动访问保护：同一 hostname 跨 MCP、worker 和子进程共享访问间隔（默认 2 秒），单次执行最多 50 次主动操作，排队超过 30 秒就失败。等待默认使用 `domcontentloaded`，显式设置的 `wait_until` 保留；字段仍需等待选择器。不同子域独立计数。协调状态位于忽略跟踪的 `backend/storage/traffic/state.sqlite3`，只保存域名与时间，不依赖向脚本传递数据库/Redis 凭证。该机制只适用于共享该存储目录的单机进程。

主导航或已访问域的 XHR/fetch 返回 401/403/429/503 时停止采集；遵守 `Retry-After` 秒数或 HTTP 日期，并至少冷却 300 秒。明确的验证/拒绝页面标题同样停止，避免把验证页保存成结果。不会自动重跑脚本、跨站跳转 API 或解验证码；更换账号/代理不会解除域名冷却。标题检测是启发式，不能识别所有验证页面。

MCP 已内置这些创作约定，脚本可使用 `COLLECT`：

```python
await page.goto(START_URL)
await page.locator("article").first.wait_for()
OUTPUTS["items"] = await page.locator("article").all_inner_texts()

# 点击翻页/主动滚动会触发页面自身请求，显式遵守节流并检查响应。
# 在有最大页数、去重和无新增即停条件的循环中使用：
# await COLLECT.before_action(page)
# await page.get_by_role("button", name="下一页").click()
# await page.locator("目标字段").wait_for()
# await COLLECT.check(page)

# 已确认且获得授权的 JSON GET：复用当前上下文的 Cookie/Headers、节流与预算。
# data = await COLLECT.fetch_json("https://example.com/api/items", params={"page": 1})
# links = COLLECT.unique_urls(hrefs, page.url)
```

页面自身的资源加载、原生 `context.request`、`evaluate` 中的网络请求和自建浏览器不受主动操作节流；浏览器缓存和正常资源加载保持原生行为，不做全量路由拦截。使用上述入口、批量提取已有数据、限定分页范围并去重，减少重复请求。MCP 页面与健康接口展示当前策略；配置项见 `.env.example` 的 `COLLECTION_*`，修改后重启 API 与唯一 worker。

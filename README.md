<img src="frontend/public/brand-mark.svg" width="72" height="72" alt="采织 Webloom Logo" />

# 采织 Webloom

**让网页信息，织成可用数据。**

“采”是采集，“织”是将零散信息组织成可复用的数据。Webloom 取自 Web 与 Loom（织机），Logo 以三条交织的信息线汇成整齐的数据单元，表达从网页到结构化数据的过程。

以 MCP 为主入口的网页数据采集平台：AgentHarness 根据提示词探索网页、编写和验证 Playwright Python 脚本，保存后可发布成对外采集接口。脚本创作规范内置 MCP，无需额外 Skills。

## 开源说明与贡献

项目源码：[helingfeng/FishCode](https://github.com/helingfeng/FishCode)。欢迎交流使用经验、反馈问题，一起完善 Webloom。

- 问题反馈与功能建议：请提交 [Issue](https://github.com/helingfeng/FishCode/issues)，附上复现步骤、版本和已脱敏的错误信息。
- 代码与文档贡献：欢迎提交 [Pull Request](https://github.com/helingfeng/FishCode/pulls)，说明改动目的和验证结果；开发约定见 [AGENTS.md](AGENTS.md)。
- 提交内容请勿包含账号密码、Cookie、Token、授权密钥或真实业务数据；截图和示例使用演示数据。
- 开源许可证：当前仓库尚未添加 `LICENSE` 文件，许可证待明确。第三方组件的许可证和授权要求请查看其各自项目说明。

## 合法使用与责任声明

Webloom 是通用网页数据采集工具，仅用于合法、获得授权的数据采集、开发测试和研究。使用前请确认目标网站的访问规则、授权范围和数据使用条件，并遵守适用法律法规。源码公开不代表已获得任何目标网站或数据权利人的授权。

禁止使用本项目从事以下行为：

- 未经授权访问系统、绕过登录或访问控制，窃取或使用他人的账号、Cookie、Token 等凭证。
- 非法收集、买卖、泄露个人信息、商业秘密或其他受保护数据，侵犯隐私、知识产权及其他合法权益。
- 通过恶意高频请求、并发轰炸或其他方式干扰目标服务，或利用采集接口开展攻击、欺诈等违法活动。

请仅采集实现目的所必需的数据，妥善保护登录凭证和采集结果，合理设置访问频率、存储期限及对外接口权限。遇到验证码、访问拒绝、限流或明确禁止采集的提示时，应停止并核实授权，不得通过更换身份或凭证反复规避限制。

使用者应对自身的采集、调用、存储和分发行为负责。项目维护者不认可、不支持任何非法用途；本说明不构成对具体采集行为合法性的保证，也不替代适用法律或相关授权约定。

## 使用流程

1. AgentHarness 连接 `http://127.0.0.1:8000/mcp`，完成页面探索、脚本试跑和保存。
2. 在后台创建开放应用，再从脚本列表点击「发布接口」，选择授权应用并设置稳定的接口标识。
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

第一次使用可先完成下方[图文上手示例](#上手示例采集图书目录并发布接口)。只需要 AI 创作脚本时，完成示例的前两步即可；发布和外部调用按需使用。

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
{"mcpServers":{"webloom":{"url":"http://127.0.0.1:8000/mcp"}}}
```

创作链路为 `open_page` / `browse_page` → `preview_script` → `create_script` / `update_script` → `close_page`。探索会话最多 4 个，空闲 10 分钟回收；试跑使用独立浏览器，代码须包含完整导航与采集步骤。启动单个 MCP 进程，避免会话分散。

采集接口发布、开放应用与授权配置通过管理后台完成，MCP 仅提供脚本创作、验证、执行和全局变量管理。`run_script` 和已发布接口的持久任务仍需 Redis 与 worker；使用 DATA_VIEWS 的脚本也通过持久任务验证。

MCP 可直接管理全局变量与用户提供的登录态，无需额外 Skills：

- `list_global_variables(domain, type, enabled, skip, limit)` 返回 `{items,total}` 元数据与 `has_value`，不含明文；domain 支持目标 URL，筛选包含通用/父域配置，limit 上限 100。
- `create_global_variable(name, value, type, domain, ...)` 保存单个 Cookie、Header、localStorage 项或普通变量；先列表查重，同类型/名称/域名项通过更新替换。
- `update_global_variable(var_id, ...)` 部分更新；未传 value 保留，空字符串清空，`enabled=false` 停用但保留值。
- `delete_global_variable(var_id)` 删除配置，重复删除安全。

Cookie 用 `type="cookie"`，Authorization 用 `type="header"`，浏览器存储用 `type="localStorage"`；`variable` 仅注入 `GLOBAL_VARS`，不会自动登录。登录态应绑定具体 domain，避免留空对所有站点生效；凭证只放 value，不写脚本、默认值、备注或输出。所有 MCP 列表/写入结果均不含 value，不提供明文读取工具。保存后新探索会话、试跑与继承全局变量的任务自动注入；已有探索会话需关闭重开。该工具集保存明确提供的值，不自动提取浏览器 Cookie，也不清除站点冷却。

## 上手示例：采集图书目录并发布接口

先按上文启动完整平台。下面用 [Books to Scrape](https://books.toscrape.com/) 的图书列表演示；这是供网页采集练习的示例站点，价格和评分不代表真实商品信息。

以下图片是当前前端的真实界面截图，书名、价格、应用和任务均为隔离的演示数据，并非目标站点的实际采集结果。

### 1. 连接 MCP

打开「MCP 服务」，复制客户端配置到 AgentHarness，连接 `http://127.0.0.1:8000/mcp`。连接成功后，AI 即可调用页面探索、脚本试跑和保存工具，无需安装额外 Skills。页面也可查看浏览器引擎和采集节流策略。

![MCP 服务：查看接入配置、浏览器引擎和采集策略](docs/images/01-mcp-connection.png)

### 2. 用提示词创作并验证脚本

把下面这段提示词发送给已连接 MCP 的 AgentHarness：

```text
使用 Webloom MCP，为 https://books.toscrape.com/ 创建一个图书目录采集脚本。

先探索真实页面，再编写、试跑并保存到「演示空间」；空间不存在时创建。
只读取当前列表页，不逐条进入详情，最多 20 条。
提取 title（书名）、price（原始价格文本）、availability（库存状态）、url（详情链接）。
定义 url 字符串参数，默认上述地址；limit 数字参数，默认 20。
将列表写入 OUTPUTS["items"]，按详情链接去重，并声明 items 输出字段。
复用平台浏览器，遵守访问间隔和请求预算；遇到登录限制或验证页面时停止。
试跑通过后保存脚本，告诉我 script_id、输入参数和验证结果，不发布接口。
```

在「脚本管理」中打开保存的脚本，可以检查代码、输入参数和输出字段。在「调试运行」填写参数后点击「保存并运行」，查看执行状态与结果。需要登录的站点，可让 AI 使用全局变量工具保存你提供的 Cookie、Header 或 localStorage，并绑定目标域名。

![脚本编辑器：查看采集代码、参数定义并运行验证](docs/images/02-script-editor.png)

### 3. 在后台发布采集接口

1. 打开「开放平台 → 开放应用」，创建调用方应用，保存其 App Key 和 App Secret。
2. 在脚本列表点击「发布接口」，或打开「开放平台 → 采集接口 → 发布采集接口」。
3. 选择已验证的脚本，填写接口名称，将接口标识设为 `book-catalog`，选择刚创建的授权应用，点击「保存并发布」。接口标识发布后不可修改。
4. 点击接口的「接入 / 调试」查看参数契约、cURL/Python 示例，或在「在线调试」提交任务。接口参数来自绑定脚本的输入定义。

发布入口在管理后台，MCP 不提供发布平台相关工具。

![发布采集接口：选择脚本、设置稳定标识并授权调用应用](docs/images/03-publish-collector.png)

### 4. 从外部调用并查看结果

下面的 `book-catalog` 要先按上一步发布；将凭证占位符替换为开放应用中查看的值。

```bash
export WEBLOOM_TOKEN='<APP_KEY>.<APP_SECRET>'

curl --fail-with-body -X POST \
  'http://127.0.0.1:8000/open/v1/collectors/book-catalog/runs' \
  -H "Authorization: Bearer $WEBLOOM_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: book-demo-001' \
  --data '{"inputs":{"url":"https://books.toscrape.com/","limit":20},"wait_seconds":0}'
```

返回 `202` 表示任务已受理，重点关注以下字段（其他字段省略，ID 以实际响应为准）：

```json
{
  "execution_id": 1001,
  "status": "pending",
  "finished": false,
  "result_url": "/open/v1/tasks/1001",
  "data_url": "/open/v1/tasks/1001/data"
}
```

使用相同凭证查询返回的 `result_url`。`wait_seconds=20` 最多等待 20 秒；若仍未完成，稍后继续查询。只有 `finished=true` 且 `status=success` 才表示采集成功，失败时查看 `error`，不要反复重新提交。

```bash
# 将 1001 换为提交响应中的 execution_id
curl --fail-with-body \
  'http://127.0.0.1:8000/open/v1/tasks/1001?wait_seconds=20' \
  -H "Authorization: Bearer $WEBLOOM_TOKEN"

# 采集成功后，按输出字段读取数据；可通过 skip/limit 分页
curl --fail-with-body \
  'http://127.0.0.1:8000/open/v1/tasks/1001/data?field=items&skip=0&limit=100' \
  -H "Authorization: Bearer $WEBLOOM_TOKEN"

# 下载这一页的 CSV
curl --fail-with-body \
  'http://127.0.0.1:8000/open/v1/tasks/1001/data?field=items&format=csv&limit=100' \
  -H "Authorization: Bearer $WEBLOOM_TOKEN" \
  -o books.csv
```

同一请求重试时保留原 `Idempotency-Key`，新的采集请求改用新键；同一键配上不同参数会返回 `409`。本机示例地址仅用于本地调用，对外部署方式见下方说明。

在「采集任务与数据」中，可按应用、接口和状态筛选任务，点击「查看数据 / 日志」查看表格、完整 JSON 和执行日志。管理端可导出所选字段的全部 CSV 或完整结果 JSON。

![采集任务结果：查看数据表格、导出 CSV/JSON 并展开执行日志](docs/images/04-collection-results.png)

### 5. 给调用方使用独立体验页

打开 `http://127.0.0.1:5173/collection-portal`，输入应用凭证 `App Key.App Secret`，即可选择获授权接口、填写参数、提交任务并查看自己的结果。这个页面不显示管理导航，凭证仅保留在当前页面内存中。

![独立调用体验页：填写采集参数、查看历史任务和结果](docs/images/05-calling-portal.png)

### 更新文档图片

截图脚本使用当前前端、隔离的演示 API 响应和独立浏览器上下文，不连接真实业务 API，不创建平台记录，也不访问示例目标网站。只需安装后端依赖与 Chromium，并启动前端，然后在项目根目录运行：

```bash
backend/venv/bin/python backend/scripts/capture_readme.py
# 前端使用其他端口时：
# backend/venv/bin/python backend/scripts/capture_readme.py --base-url http://127.0.0.1:5174
```

图片保存到 `docs/images/`。更新前端界面或品牌后，可重新生成并检查这些图片。

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

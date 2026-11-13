# AGENTS.md

采织（Webloom）架构指引。以 MCP 为主入口的网页数据采集平台：创作、验证并保存 Playwright Python 脚本，发布采集接口，查看任务与结果数据；数据源与数据视图继续提供管理能力。

品牌口号：让网页信息，织成可用数据。Logo 唯一源文件为 `frontend/public/brand-mark.svg`，导航、首页、调用门户通过 `BrandIdentity.vue` 复用，浏览器 SVG favicon 同源；PNG 与 ICO 为该 SVG 的导出资源，修改时同步导出。主题色位于 `frontend/src/assets/brand.css`。

## 1. 项目概览

前后端分离的本地单用户平台：

- **backend/** — FastAPI + SQLAlchemy 2.0 (async) + MySQL。负责脚本/采集接口/任务/执行记录/全局变量/数据源/数据视图的 CRUD，通过子进程运行 Playwright Python 脚本并收集结果；内嵌 MCP 服务。
- **frontend/** — Vue 3 + TypeScript + Element Plus + Pinia+ Monaco（代码/SQL 编辑器）。开发时由 Vite 代理 `/api`、`/storage` 到后端（含 WebSocket）。

核心执行流：前端点击运行 → `POST /api/scripts/{id}/run` 立即返回 execution_id → 后台任务将用户代码嵌入 `SCRIPT_TEMPLATE`（`backend/app/engine/runner.py`）→ 子进程执行 → stdout 逐行经 WebSocket `/api/ws/executions/{id}` 推送到前端 → 前端同时每秒轮询 execution 状态直到结束。

### 分层约定

后端严格三层：`routers/`（HTTP 入口，无业务逻辑）→ `services/`（业务逻辑，操作模型）→ `models/`（SQLAlchemy）+ `schemas/`（Pydantic 出入参）。执行引擎在 `engine/`。新增模型必须在 `models/__init__.py` 追加 import 与 `__all__`。

前端分层：`api/`（Axios 封装）→ `stores/`（Pinia）→ `views/`（页面）+ `components/`（复用组件）+ `types/`（TS 接口，与后端 schema 一一对应）。

### 关键机制

- **脚本执行约定**：用户代码片段在模板内可使用 `INPUTS`、`OUTPUTS`、`GLOBAL_HEADERS`、`GLOBAL_VARS`、`GLOBAL_LOCAL_STORAGE`、`DATA_VIEWS` / `DATA_VIEWS_ONE` 与 `page/context/browser`。结果通过 stdout 中 `__ATP_OUTPUTS__{json}` 标记回传解析。参数经环境变量（`ATP_INPUTS` 等）传入子进程，且必须设置 `PYTHONUNBUFFERED=1`（否则日志会缓冲到结束才输出）。输入变量类型除 string/number/boolean/secret 外支持 `header`/`cookie`/`localStorage`（变量名即注入名，Cookie 域取起始 URL host），执行时与全局变量合并且**输入变量优先**（覆盖同名项，拆分逻辑在 `runner.py::_split_browser_inputs`）。
- **全局变量三种类型**：`header`（注入浏览器 `extra_http_headers`）、`localStorage`（通过 init script 在目标页面脚本执行前写入）、`variable`（注入 `GLOBAL_VARS`），另有 cookie 支持；按域名匹配（精确或子域名，未绑定域名的全局生效）。脚本通过 `Script.inherit_global`（默认 true）控制是否继承。
- **队列执行模式（Redis + arq worker）**：API 进程只创建 `pending` 状态 Execution 并经 `task_queue.enqueue_*` 入队（`_job_id = exec:{execution_id}` 幂等防重），实际执行在独立 worker 进程（`app/worker.py`）。Redis 不可用时 run 接口返回 503、该执行留痕 failed。worker `max_jobs` = `max_concurrent_executions`（默认 5）；`job_timeout` = `script_execution_timeout + 30`。恢复机制：worker 启动时把 `running` 执行标为 failed（worker 重启中断）并清理残留 job 键；心跳循环每 10s 兜底把超龄（>60s）`pending` 重新入队（Redis 重启丢队列后自愈，`_job_id` 去重不会重复执行）。worker 无 `--reload`，改后端代码需手动重启；**单机只跑一个 worker**（多个会误触发恢复逻辑）。
- **日志流（LogBus）**：worker 内 `services/log_bus.py::ExecutionLogBus` 每行分配递增 seq（1 seq = 1 行，行尾强制 `\n`），经 Redis pub/sub（channel `exec:logs:{id}`，内部 JSON 含 seq/eof 控制消息）实时分发 + 每 1s 增量 `CONCAT` 落库 `executions.logs`（Text 64KB 超限时自动停落库，实时流不受影响）。API 进程 `services/log_stream_service.py` 先订阅再从 DB 重放、seq 对齐去重补洞，EOF（终态落库后发布）触发收尾；Redis 不可用自动退化为 DB 轮询。对前端 WS 消息保持纯文本日志行。
- **MySQL 迁移**：无 Alembic。`database.py` 的 `init_db()` 在 `create_all` 后对已有表做幂等 `ALTER TABLE ... ADD COLUMN`（`_migrate` 内先 `inspect` 检查列是否存在）。新建表无需迁移，仅给已有表加列时写 ALTER 块。主库为 MySQL，`_migrate` 裸 SQL 必须双方言兼容：标识符统一反引号（`usage`/`key`/`database` 等为 MySQL 保留字），索引用 `inspector.get_indexes()` 判断后再 `CREATE INDEX`（MySQL 不支持 `IF NOT EXISTS`）。建表 DDL 由 `backend/scripts/gen_mysql_ddl.py` 从模型生成到 `backend/mysql_ddl.sql`（改模型后必须重新生成；模型列须带 `comment`，主键/ID 列用 `BigIntUnsigned`）。

### 开放平台

- **模型与凭证**：`models/open_platform.py` 两表——`open_apps`（App Key `fk*` 唯一 + Secret，Secret 明文存但**列表接口不回传**，仅创建/详情/重新生成返回）、`open_api_logs`（每次开放调用留痕，含认证失败；`execution_id` 关联采集触发）。
- **签名认证**（`open_app_service.authenticate_request`）：头 `X-App-Key` / `X-Timestamp` / `X-Sign`；`X-Sign = HMAC-SHA256(secret, "{METHOD}\n{完整路径含/open}\n{timestamp}\n{sha256_hex(body)}")` 小写 hex；时间窗 `open_api_sign_ttl_seconds`（±300s）；恒时比较；签名只覆盖 path **不含 query**。认证失败也落日志。
- **内置采集接口**（`/open/api/v1/collect/*`，固定开放）：`POST trigger`（传 `url` + `script_id`，url 强制合入 `inputs.url`，复用 `start_script_execution` 入队，QueueUnavailable → 503）；`GET result?execution_id=`（**归属校验**：只能查本应用触发的执行，从 `open_api_logs` 反查）；`GET tasks`（本应用最近触发任务，最多 50 条）。
- **管理端与前端**：`routers/open_platform.py` 导出 3 个 router（挂 `/api/open-apps`、`/api/open-logs`、`/open`）；前端菜单组「开放平台」包含采集接口、采集任务与数据、开放应用、调用日志、接入文档，AppLayout 的 menuItems 用 `children` + `el-sub-menu` 渲染分组。

### 数据源与数据视图

- **连接池**：`datasource_query_service.connection_manager` 按 `(datasource_id, database)` 缓存 `AsyncEngine`；`invalidate(ds_id)` 释放该数据源全部库的 engine（配置变更/超时/连接异常后调用）；应用退出 `dispose_all`。
- **多库切换**：`list_tables` / `get_table_schema` / `execute_query` / `execute_readonly_query` 均接受可选 `database`，缺省回退数据源默认库（`effective = database or ds.database`）。`list_databases` 过滤 4 个系统库。
- **SQL 执行安全**：`_preprocess` 剥离注释后校验单语句；`_classify` 按首 token 白名单分流查询/执行路径；查询路径 `fetchmany` 截断 `settings.sql_max_rows`（1000）行；无绑定参数时字面 `%` 必须转义为 `%%`（aiomysql pyformat）。`validate_readonly_sql` 是数据视图与 MCP 只读查询共用的双保险之一。
- **数据视图**：数据源 + 只读 SQL，保存后外部系统通过 `GET /api/data/{slug}` 无鉴权取 JSON（`public_router`，手动加 CORS 头）；停用视图对外表现为不存在。脚本引用 DATA_VIEWS / DATA_VIEWS_ONE 时预取启用视图注入 `DATA_VIEWS`（经 `ATP_DATA_VIEWS` 环境变量），单视图失败值为 `{"_error": ...}` 不影响脚本。预取用 `collect_view_data_cached`：视图 SQL 并行执行（`VIEW_CONCURRENCY=4`）+ worker 侧 TTL 缓存（`cache_ttl_seconds` 默认 30s，键含 `updated_at`，编辑即失效；并发共享同一次查询；失败不缓存）。管理端预览与公开取数不走缓存。
- **SQL 执行历史**：工作台执行（含失败）自动落 `query_history` 表，结果快照仅保留前 200 行样本；删除数据源时级联清理。落历史失败静默回滚，不影响执行响应。

### MCP 服务

- `backend/app/mcp/server.py`：官方 `mcp` 包的 FastMCP，以 streamable-http 子应用嵌入 FastAPI 进程（端点 `/mcp`），**直接 import services 层，不走 HTTP**；每个工具内 `async with AsyncSessionLocal() as db:` 自建会话；业务异常转 `ToolError`。挂载必须放在所有路由之后（`mount_mcp(app)`）。
- 工具集：采集闭环（`inspect_page` 探索页面并自动注入已配置登录态、`list_workspaces` / `create_workspace` / `list_scripts` / `get_script` 查找与准备、`create_script` / `update_script` 管理、`run_script` / `get_execution` 执行）。MCP 不回传明文凭证；数据源不通过 MCP 暴露。新增工具照 `@mcp.tool()` 样板，并同步更新顶部 `INSTRUCTIONS`。
- `GET /api/mcp/status` 返回真实工具列表与客户端接入命令（服务名 `webloom`，配置与命令均取自 `mcp.name`，避免改名后不同步）；脚本创作规范内置在 `backend/app/mcp/server.py` 的 MCP instructions 和工具描述中，AgentHarness 不需要额外 Skills。
- MCP 通过 `list_global_variables/create_global_variable/update_global_variable/delete_global_variable` 管理用户明确提供的登录态和普通配置；共用 global_variable_service 校验、域名规范化、查重和部分更新。列表支持 domain（包含通用/父域）、type、enabled 和 skip/limit，返回 `{items,total}`。统一 `GlobalVariableOut` 脱敏，无明文读取工具；凭证只写 value，登录态建议绑定具体域名。保存后新会话/执行加载，旧探索会话需重开，不自动抓取 Cookie 或解除冷却。修改时运行 `tests/test_mcp_global_variables.py`（含真实试跑注入测试）。

## 2. 构建与命令

### 基础设施（先于后端启动）

```bash
# 使用 backend/.env 中 REDIS_URL 对应的实例，已有 Redis 时无需重复启动。
# 本机当前使用 6379 的需认证实例，凭证仅保存在未跟踪的 backend/.env。
# 新环境需要独立实例时，可选择空闲端口并同步配置 REDIS_URL。
```

### 后端 API（端口 8000）

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000   # 开发
pip install -r requirements.txt
playwright install chromium                  # 首次需要
```

### 执行 worker（独立进程，必启动）

```bash
cd backend && ./venv/bin/python3 -m app.worker   # 无 --reload，改代码需手动重启；单机只能跑一个
```

入口 `worker.py::_supervise` 带断线守护：Redis 瞬断/重启导致 arq 主循环退出时自动重启（也可直接 `arq app.worker.WorkerSettings`，但无自动重启）。

不启动 worker 时任务会停留在队列（run 接口正常返回 pending），`/api/health` 的 `queue.worker_alive=false` 可诊断。

### 前端（端口 5173）

```bash
cd frontend
npm install
npm run dev        # 开发
npm run build      # 类型检查 + 构建
npm run type-check # 仅 vue-tsc 类型检查
npm run test:unit  # vitest
```

### 注意事项

- 临时执行脚本写入系统临时目录（`config.py` 的 `executions_dir` 指向 `tempfile.gettempdir()/atp_executions`）。**不要**改回 `backend/storage/`，否则 uvicorn `--reload` 会监听到运行文件导致服务自动重启、中断 WebSocket。运行文件带随机后缀（并发执行互不覆写）并在执行后即删（`runner.py` finally + `cleanup_execution_temp_files`），worker 启动时清扫超 24h 的孤儿文件。
- 端口被占用或进程挂死：`lsof -ti:8000 | xargs kill -9` 后重启。
- 验证后端是否正常：`curl http://127.0.0.1:8000/api/health`（响应含 `queue` 字段：available/depth/worker_alive）。
- 不要在 `--reload` 进程外另跑连同一 MySQL 的一次性 asyncio 脚本做验证后遗留连接，异常退出可能拖垮开发服务器。

## 3. 代码风格

- 后端 Python 3.13，全 async（`async def` + `AsyncSession`）；类型注解用新语法（`dict[str, str]`、`str | None`）。
- 前端 Vue 3 `<script setup lang="ts">` 组合式 API；组件间通过 props/emit 通信，跨页面状态用 Pinia store。
- 命名：后端文件 snake_case，前端组件 PascalCase；API 路径 kebab-case（如 `/api/global-variables`）。
- 前端时间统一用 `@/utils/format.ts` 的 `formatDateTime`（`Y-m-d H:i:s`）格式化。
- 模板字符串替换用唯一占位符（`__HEADLESS__`、`__USER_CODE__`）+ `.replace()`，**禁止**用 `str.format()`（用户代码中的 `{}` 会冲突）。
- 分页接口约定：查询参数 `skip/limit`，响应 `{items, total}`；ORM → 出参统一走现成 Pydantic schema（`model_validate(...).model_dump(mode="json")`）。
- 后端无 logging 惯例，用户可见错误用返回值（如 `QueryResult.error`）或 `HTTPException`/`ToolError` 传递文案。

## 4. 测试

- 后端：`backend/tests/` 使用独立 SQLite、假 Redis/队列验证服务与 HTTP 路由；MCP 创作测试还包含真实 Chromium 和子进程试跑。运行 `python -m pytest tests/ -q`，新增测试放此处。
- 前端：vitest 已配置（`vitest.config.ts`），运行 `npm run test:unit`。
- 手工端到端验证路径：创建脚本 → 运行 → 检查执行面板实时日志与最终状态 → `GET /api/executions` 查看记录；数据源改动后用 curl 验证 `/api/datasources/{id}/...` 系列接口与前端工作台。

## 5. 安全

- 脚本以子进程执行，环境变量仅传 `PATH`、`PYTHONPATH`、`ATP_*`、`PYTHONUNBUFFERED`，不暴露后端内部环境。
- 子进程执行超时由 `settings.script_execution_timeout`（默认 120s）控制，超时 kill。
- 敏感值（secret 输入、variable/localStorage 类型全局变量）在前端列表中打码显示。
- 数据源密码明文存平台库（本地单用户场景），但 `DatasourceOut` 不回传密码；对外接口不暴露密码。
- 数据视图仅允许只读语句白名单；外部取数 `GET /api/data/{slug}` 无鉴权，勿在视图 SQL 中暴露敏感数据。
- 用户代码可执行任意 Python，仅适用于本地单用户场景，勿暴露到公网。
- CORS 仅允许 `http://localhost:5173` / `http://127.0.0.1:5173`（公共取数接口单独手动加 `Access-Control-Allow-Origin: *`）。

## 6. 配置

- 后端配置集中在 `backend/app/config.py`（pydantic-settings），支持 `backend/.env` 覆盖（样例见 `.env.example`）。关键项：`headless`（浏览器是否无头）、`playwright_timeout`、`script_execution_timeout`、`sql_query_timeout`（30s）、`sql_max_rows`（1000）、`database_url`（MySQL DSN，默认 `mysql+aiomysql://root:helingfeng@127.0.0.1:3306/fishcode?charset=utf8mb4`，表级字符集 utf8mb4；注意 URL 驱动后缀必须是 `+aiomysql`，裸 `mysql://` 会去加载未安装的 MySQLdb）；执行队列：`redis_url`（默认 `redis://127.0.0.1:6379/0`，本机 `.env` 使用 6379 并配置认证）、`max_concurrent_executions`（默认 5）；数据采集：`cache_ttl_seconds`（30s）、`datasource_pool_size`/`datasource_max_overflow`（5/10）、`database_pool_size`/`database_max_overflow`（20/40，主库连接池仅 MySQL 方言生效）。
- 平台主库为 MySQL（`fishcode`）：建表 DDL 在 `backend/mysql_ddl.sql`；SQLite 存量数据经 `backend/scripts/migrate_sqlite_to_mysql.py` 一次性迁入（MySQL 侧已有数据的表自动跳过）。`backend/storage/app.db` 为历史 SQLite 存量，不再被服务读写。引擎已带 `pool_pre_ping`/`pool_recycle=3600` 防 MySQL 长连接被 `wait_timeout` 掐断。
- 前端 Vite 代理配置在 `frontend/vite.config.ts`：`/api` 代理需带 `ws: true`（WebSocket 日志推送依赖）。
- 数据库/存储均在 `backend/storage/`（历史 app.db、scripts/）；`app/skills/` 目录预留存放 Skill 模板 JSON。

## MCP 创作主路径（重构）

- 最小入口 `app.mcp_main:app` 仅提供 MCP；`app.main:app` 为可选完整管理应用。
- 连续探索逻辑在 `services/browser_authoring_service.py`，试跑在 `services/authoring_service.py`，工具只做协议适配。
- `open_page` → `browse_page` → `preview_script` → `create_script/update_script` → `close_page`；运行规范全部内置 MCP，不依赖额外 Skills。
- 试跑共用 runner 模板，无 Redis/worker，无持久执行记录；持久任务继续走队列。数据视图依赖仅持久任务支持。
- 修改创作链路运行 `tests/test_mcp_authoring.py`（含真实 Chromium 测试）；接入和运行边界见 `README.md`。

## 采集接口发布主路径

- `models/collector.py` 的 `collectors` / `collector_tasks` 保存发布配置、应用授权与持久任务归属，后者不依赖调用日志；新增表已同步 mysql_ddl.sql。
- `services/collector_service.py` 统一发布、参数契约、幂等提交、查询与数据分页；路由位于 `routers/collectors.py`，管理端 `/api/collectors`、`/api/collector-tasks`，外部 `/open/v1/collectors`、`/open/v1/tasks`，通过开放 router 注册。
- 外部支持 Bearer `AppKey.AppSecret` 与原 HMAC；幂等键由 `Idempotency-Key` 指定，归属与 Execution 在同一事务内提交后入队。Task 列表不加载 outputs/inputs。
- 前端 `/collectors` 发布与调试，`/collector-tasks` 数据查看，`/collection-portal` 为无管理导航的独立调用体验页（凭证仅存内存，所有请求走 /open）。Vite 已代理 /open。
- 新任务归属不随清空日志丢失；旧版入口保留兼容但不做任务迁移。脚本更新影响绑定接口的新任务；执行记录有提交快照，但当前没有独立的接口发布版本。更多边界见 docs/collector-platform.md。
- 采集接口发布、开放应用与授权配置仅通过管理后台提供；MCP 不暴露发布平台相关工具，仅保留脚本创作、验证、执行及全局变量管理。

## 已移除的功能

- 测试用例管理（含需求、模块、Markdown 导入与思维导图）及流程编排已删除，前后端路由、模型、服务与专用依赖均不再提供。
- 不执行 DROP TABLE：旧库的历史表与执行记录原样保留，新库不再创建这些表。历史执行详情仍可读取；空间删除仅检查当前脚本。
- worker 仅注册脚本任务；恢复时将非脚本 pending 执行标记为已停用并清理队列，禁止历史任务误执行成同 ID 的脚本。

- 采集接口支持 DELETE /api/collectors/{id} 移除：collectors.archived 归档，enabled=false；列表和新调用排除归档接口，历史任务仍关联原记录。移除后释放脚本删除限制，但保留唯一 slug，禁止复用旧调用地址。已有数据库的 archived 列由 init_db 幂等补齐。

- 接口代理模块已移除：不再提供 /api/open-apis 和 /open 通用转发，也不创建 open_apis 表；旧库中的历史规则保留但不会读取。开放服务仅提供明确注册的采集端点、应用和日志功能。

## 参数与全局配置一致性

- `engine/parameters.py` 统一输入定义规范化、默认值合并、必填与类型校验，REST、MCP 试跑、开放采集复用；未声明的输入拒绝，旧字符串数字/布尔默认值兼容规范化，运行实参要求原生类型。
- `effective_start_url` 使用非空 INPUTS.url 优先于脚本 start_url，runner 的 START_URL、Cookie 域和全局配置域名匹配统一使用该地址。Header 名大小写不敏感，输入覆盖同名全局 Header。
- 全局配置按通用、父域、具体域顺序合并；旧重复项同范围按 ID 后者覆盖，新建/修改拒绝同类型同名同域配置。域名规范化在 engine/domains.py，忽略端口，支持粘贴 URL。
- 全局变量列表与写入响应不含 value，仅 has_value；GET /api/global-variables/{id} 显式读取原值。PUT 支持部分更新，未传 value 保留，传空字符串清空。
- Execution.script_snapshot 保存提交时的脚本、输入定义与浏览器配置，worker 不再读取后续修改的代码；历史空快照任务兼容旧读取路径。该字段不经 ExecutionOut 或外部 API 返回。
- 页面「保存并运行」先持久化当前编辑内容，再提交真实输入；数字/布尔/敏感参数共用 ParameterValue，未指定值不传。自动 Mock 从页面移除，仅兼容旧 API 显式请求；默认 manual。

## 浏览器提供方

- app/engine/browser.py 统一 Playwright / CloakBrowser 启动和资源清理；探索、录制及 runner 模板全部走该层。用户脚本的 page/context/browser 与 expect 保持兼容。
- `browser_settings` 固定单行保存 CloakBrowser 开关，后台 MCP 服务页经 `GET/PUT /api/mcp/browser-settings` 管理；`browser_setting_service.get_browser_options` 在每次启动浏览器前读取数据库，API/MCP/worker 不缓存，无需重启。未保存时回退 BROWSER_ENGINE 默认值；已打开会话和运行中的任务不切换。许可证始终仅来自本机环境配置/官方缓存，不经管理接口回传。
- BROWSER_ENGINE 默认为 playwright；显式 cloakbrowser 时需 CLOAKBROWSER_LICENSE_KEY 或官方登录缓存，禁止自动注册/交互登录，失败不得静默降级。humanize、代理、locale、timezone 的 CLOAKBROWSER_* 配置仅用于 Cloak 引擎。
- 子进程不加载 app.config/.env；runner 仅额外传 ATP_BROWSER_OPTIONS 和 ATP_BROWSER_LICENSE_KEY，并明确加入 backend 的 PYTHONPATH。健康状态和 MCP 状态不回传密钥或代理内容。
- 固定 cloakbrowser==0.7.2、playwright==1.64.1（发行包要求 >=1.53,<1.65）；升级后须安装匹配的 Chromium，并验证内部 enableRecorder 协议。官方许可证和浏览器下载需用户已有授权，不自动注册邮箱或购买。

## 低负载采集运行时

- `engine/collection.py` 不加载 app.config/.env，`CollectionPolicy` 通过 `ATP_COLLECTION_POLICY` 显式传入子进程；`create_collection_context` 统一 Cookie/Header/首屏 localStorage 初始化，并给该 context 的页面绑定主动导航保护。探索、试跑、worker 和录制共用。
- 同一 hostname 的导航/API/主动翻页操作默认间隔 2 秒、单次预算 50；单机跨进程通过 `storage/traffic/state.sqlite3` 的 SQLite 短事务协调（非平台主库，不含凭证/完整 URL，已忽略跟踪）。等待不持锁，取消不会占用未来时隙，过期记录自动清理。
- 401/403/429/503 与明确验证标题停止采集并持久化冷却；尊重 Retry-After，更长等待不能被短冷却覆盖。第三方广告响应不触发业务熔断；不自动重试，不解验证码，不通过代理切换清除冷却。
- 内置 `COLLECT.fetch_json` 仅已授权 GET，共用 Cookie/Headers、预算与冷却，不自动跳转；翻页/滚动用 `before_action/check`，结果 URL 可用 `unique_urls` 去重。原生 request/evaluate 网络、自建 context 不自动治理，不得宣称覆盖所有请求；无全量路由拦截，保留 HTTP 缓存。
- 修改此链路运行 `tests/test_collection.py`、`tests/test_mcp_authoring.py`，含真实 Chromium；浏览器测试在 macOS 沙箱受限时需提升执行权限。

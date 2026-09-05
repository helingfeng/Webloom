# AGENTS.md

小鱼（fishCode）架构指引。本地运行的自动化测试与数据采集平台：编写 Playwright Python 脚本、可视化编排流程、执行并查看实时日志；配套数据源管理与数据视图（SQL 对外取数）。

## 1. 项目概览

前后端分离的本地单用户平台：

- **backend/** — FastAPI + SQLAlchemy 2.0 (async) + MySQL。负责脚本/流程/执行记录/全局变量/测试用例/数据源/数据视图的 CRUD，通过子进程运行 Playwright Python 脚本并收集结果；内嵌 MCP 服务。
- **frontend/** — Vue 3 + TypeScript + Element Plus + Pinia + Vue Flow（流程画布）+ Monaco（代码/SQL 编辑器）。开发时由 Vite 代理 `/api`、`/storage` 到后端（含 WebSocket）。

核心执行流：前端点击运行 → `POST /api/scripts/{id}/run` 立即返回 execution_id → 后台任务将用户代码嵌入 `SCRIPT_TEMPLATE`（`backend/app/engine/runner.py`）→ 子进程执行 → stdout 逐行经 WebSocket `/api/ws/executions/{id}` 推送到前端 → 前端同时每秒轮询 execution 状态直到结束。

### 分层约定

后端严格三层：`routers/`（HTTP 入口，无业务逻辑）→ `services/`（业务逻辑，操作模型）→ `models/`（SQLAlchemy）+ `schemas/`（Pydantic 出入参）。执行引擎在 `engine/`。新增模型必须在 `models/__init__.py` 追加 import 与 `__all__`。

前端分层：`api/`（Axios 封装）→ `stores/`（Pinia）→ `views/`（页面）+ `components/`（复用组件）+ `types/`（TS 接口，与后端 schema 一一对应）。

### 关键机制

- **脚本执行约定**：用户代码片段在模板内可使用 `INPUTS`、`OUTPUTS`、`GLOBAL_HEADERS`、`GLOBAL_VARS`、`GLOBAL_LOCAL_STORAGE`、`DATA_VIEWS` / `DATA_VIEWS_ONE` 与 `page/context/browser`。结果通过 stdout 中 `__ATP_OUTPUTS__{json}` 标记回传解析。参数经环境变量（`ATP_INPUTS` 等）传入子进程，且必须设置 `PYTHONUNBUFFERED=1`（否则日志会缓冲到结束才输出）。输入变量类型除 string/number/boolean/secret 外支持 `header`/`cookie`/`localStorage`（变量名即注入名，Cookie 域取起始 URL host），执行时与全局变量合并且**输入变量优先**（覆盖同名项，拆分逻辑在 `runner.py::_split_browser_inputs`）。
- **全局变量三种类型**：`header`（注入浏览器 `extra_http_headers`）、`localStorage`（执行前访问起始 URL 自动写入）、`variable`（注入 `GLOBAL_VARS`），另有 cookie 支持；按域名匹配（精确或子域名，未绑定域名的全局生效）。脚本通过 `Script.inherit_global`（默认 true）控制是否继承。
- **异步执行模式**：run 接口先创建 `running` 状态的 Execution 并立即响应，实际执行放在 `asyncio.create_task` 中并用独立的 `AsyncSessionLocal` 会话，避免阻塞请求。
- **流程执行**：`flow_service._run_flow_nodes` 按拓扑排序执行脚本节点，节点间通过 `{{global.xxx}}`、`{{node_xxx.xxx}}` 模板语法传递变量。
- **MySQL 迁移**：无 Alembic。`database.py` 的 `init_db()` 在 `create_all` 后对已有表做幂等 `ALTER TABLE ... ADD COLUMN`（`_migrate` 内先 `inspect` 检查列是否存在）。新建表无需迁移，仅给已有表加列时写 ALTER 块。主库为 MySQL，`_migrate` 裸 SQL 必须双方言兼容：标识符统一反引号（`usage`/`key`/`database` 等为 MySQL 保留字），索引用 `inspector.get_indexes()` 判断后再 `CREATE INDEX`（MySQL 不支持 `IF NOT EXISTS`）。建表 DDL 由 `backend/scripts/gen_mysql_ddl.py` 从模型生成到 `backend/mysql_ddl.sql`（改模型后必须重新生成；模型列须带 `comment`，主键/ID 列用 `BigIntUnsigned`）。
- **测试用例组织**：项目空间（workspaces）→ 需求（requirements）→ 模块（modules）三级，用例挂模块下。

### 数据源与数据视图

- **连接池**：`datasource_query_service.connection_manager` 按 `(datasource_id, database)` 缓存 `AsyncEngine`；`invalidate(ds_id)` 释放该数据源全部库的 engine（配置变更/超时/连接异常后调用）；应用退出 `dispose_all`。
- **多库切换**：`list_tables` / `get_table_schema` / `execute_query` / `execute_readonly_query` 均接受可选 `database`，缺省回退数据源默认库（`effective = database or ds.database`）。`list_databases` 过滤 4 个系统库。
- **SQL 执行安全**：`_preprocess` 剥离注释后校验单语句；`_classify` 按首 token 白名单分流查询/执行路径；查询路径 `fetchmany` 截断 `settings.sql_max_rows`（1000）行；无绑定参数时字面 `%` 必须转义为 `%%`（aiomysql pyformat）。`validate_readonly_sql` 是数据视图与 MCP 只读查询共用的双保险之一。
- **数据视图**：数据源 + 只读 SQL，保存后外部系统通过 `GET /api/data/{slug}` 无鉴权取 JSON（`public_router`，手动加 CORS 头）；停用视图对外表现为不存在。脚本执行前预取所有启用视图注入 `DATA_VIEWS`（经 `ATP_DATA_VIEWS` 环境变量），单视图失败值为 `{"_error": ...}` 不影响脚本。
- **SQL 执行历史**：工作台执行（含失败）自动落 `query_history` 表，结果快照仅保留前 200 行样本；删除数据源时级联清理。落历史失败静默回滚，不影响执行响应。

### MCP 服务

- `backend/app/mcp/server.py`：官方 `mcp` 包的 FastMCP，以 streamable-http 子应用嵌入 FastAPI 进程（端点 `/mcp`），**直接 import services 层，不走 HTTP**；每个工具内 `async with AsyncSessionLocal() as db:` 自建会话；业务异常转 `ToolError`。挂载必须放在所有路由之后（`mount_mcp(app)`）。
- 工具集：脚本（list/get/create/update/delete/run_script + get_execution 轮询）、`list_workspaces`、`get_auth_credentials`（按域名查全局变量凭证）、数据源查询（list_datasources / list_databases / list_tables / get_table_schema / query_database，**只读**）。新增工具照 `@mcp.tool()` 样板，并同步更新顶部 `INSTRUCTIONS`。
- `GET /api/mcp/status` 返回真实工具列表与客户端接入命令（服务名 `fishcode-scripts` 硬编码于该接口，改名需同步）；Agent Skills 文档在 `backend/app/agent_skills/{script-authoring,script-execution,script-maintenance}/SKILL.md`，由 `agent_skill_service` 读取并在 `/api/mcp/skills` 暴露。

## 2. 构建与命令

### 后端（端口 8000）

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000   # 开发
pip install -r requirements.txt
playwright install chromium                  # 首次需要
```

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

- 临时执行脚本写入系统临时目录（`config.py` 的 `executions_dir` 指向 `tempfile.gettempdir()/atp_executions`）。**不要**改回 `backend/storage/`，否则 uvicorn `--reload` 会监听到运行文件导致服务自动重启、中断 WebSocket。
- 端口被占用或进程挂死：`lsof -ti:8000 | xargs kill -9` 后重启。
- 验证后端是否正常：`curl http://127.0.0.1:8000/api/health`。
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

- 后端：`backend/tests/` 目前为空；requirements 已含 pytest + httpx（用于 `AsyncClient` 测试 FastAPI）。新增测试放此处。
- 前端：vitest 已配置（`vitest.config.ts`），运行 `npm run test:unit`。
- 手工端到端验证路径：创建脚本 → 运行 → 检查执行面板实时日志与最终状态 → `GET /api/executions` 查看记录；数据源改动后用 curl 验证 `/api/datasources/{id}/...` 系列接口与前端工作台。

## 5. 安全

- 脚本以子进程执行，环境变量仅传 `PATH`、`PYTHONPATH`、`ATP_*`、`PYTHONUNBUFFERED`，不暴露后端内部环境。
- 子进程执行超时由 `settings.script_execution_timeout`（默认 120s）控制，超时 kill。
- 敏感值（secret 输入、variable/localStorage 类型全局变量）在前端列表中打码显示。
- 数据源密码明文存平台库（本地单用户场景），但 `DatasourceOut` 不回传密码；对外接口不暴露密码。
- 数据视图与 MCP `query_database` 仅允许只读语句白名单；外部取数 `GET /api/data/{slug}` 无鉴权，勿在视图 SQL 中暴露敏感数据。
- 用户代码可执行任意 Python，仅适用于本地单用户场景，勿暴露到公网。
- CORS 仅允许 `http://localhost:5173` / `http://127.0.0.1:5173`（公共取数接口单独手动加 `Access-Control-Allow-Origin: *`）。

## 6. 配置

- 后端配置集中在 `backend/app/config.py`（pydantic-settings），支持 `backend/.env` 覆盖（样例见 `.env.example`）。关键项：`headless`（浏览器是否无头）、`playwright_timeout`、`script_execution_timeout`、`sql_query_timeout`（30s）、`sql_max_rows`（1000）、`database_url`（MySQL DSN，默认 `mysql+aiomysql://root:helingfeng@127.0.0.1:3306/fishcode?charset=utf8mb4`，表级字符集 utf8mb4；注意 URL 驱动后缀必须是 `+aiomysql`，裸 `mysql://` 会去加载未安装的 MySQLdb）。
- 平台主库为 MySQL（`fishcode`）：建表 DDL 在 `backend/mysql_ddl.sql`；SQLite 存量数据经 `backend/scripts/migrate_sqlite_to_mysql.py` 一次性迁入（MySQL 侧已有数据的表自动跳过）。`backend/storage/app.db` 为历史 SQLite 存量，不再被服务读写。引擎已带 `pool_pre_ping`/`pool_recycle=3600` 防 MySQL 长连接被 `wait_timeout` 掐断。
- 前端 Vite 代理配置在 `frontend/vite.config.ts`：`/api` 代理需带 `ws: true`（WebSocket 日志推送依赖）。
- 数据库/存储均在 `backend/storage/`（历史 app.db、scripts/）；`app/skills/` 目录预留存放 Skill 模板 JSON；`app/agent_skills/` 存放 MCP 配套 Agent Skills 文档。

# fishCode Backend

小鱼（fishCode）后端：FastAPI + SQLAlchemy 2.0 (async) + MySQL，负责脚本/流程/执行记录/测试用例的 CRUD，并通过子进程运行 Playwright Python 脚本、实时回传日志。

## 技术栈

- Python 3.13（全 async），FastAPI + Pydantic v2
- SQLAlchemy 2.0 异步 ORM + aiomysql（MySQL 8，默认库 `fishcode`）
- Playwright（浏览器自动化执行引擎）
- MCP（Model Context Protocol）服务，供 AI 客户端调用脚本管理能力

## 目录结构

```
backend/
├── app/
│   ├── main.py            # 应用入口：路由注册、CORS、生命周期、WebSocket
│   ├── config.py          # pydantic-settings 配置（支持 .env 覆盖）
│   ├── database.py        # 引擎/会话 + init_db()（create_all + 幂等 ALTER TABLE 迁移，双方言兼容）
│   ├── websocket.py       # 执行日志 WebSocket 管理器
│   ├── routers/           # HTTP 入口（薄层：状态码与异常映射，无业务逻辑）
│   ├── services/          # 业务逻辑（操作模型，内部 commit，ValueError 抛业务错误）
│   ├── models/            # SQLAlchemy 模型（无外键，逻辑关联 + 索引，服务层校验）
│   ├── schemas/           # Pydantic 出入参（XxxBase/Create/Update/Out）
│   ├── engine/            # 脚本执行引擎（runner.py 模板嵌入、mock_generator.py）
│   ├── mcp/               # MCP 服务端实现
│   ├── agent_skills/      # Agent Skill 定义（SKILL.md）
│   └── skills/            # Skill 模板 JSON 存储目录
├── storage/               # 附件存储（历史 SQLite app.db 已不再使用）
├── mysql_ddl.sql          # MySQL 建表 DDL（规范样式，由 scripts/gen_mysql_ddl.py 生成）
├── scripts/               # gen_mysql_ddl.py（DDL 生成）、migrate_sqlite_to_mysql.py（SQLite 存量迁移）
├── tests/                 # pytest + httpx AsyncClient 测试
└── requirements.txt
```

## 快速开始

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # 首次需要

# 开发模式
uvicorn app.main:app --reload --port 8000

# 验证
curl http://127.0.0.1:8000/api/health   # => {"status":"ok"}
```

端口被占用时：`lsof -ti:8000 | xargs kill -9`。

## API 概览

| 前缀 | 说明 |
|---|---|
| `/api/scripts` | 脚本 CRUD 与运行（`/{id}/run` 异步执行，立即返回 execution_id） |
| `/api/flows` | 流程编排（节点拓扑执行，`{{global.xxx}}` 变量传递） |
| `/api/executions` | 执行记录 |
| `/api/skills` | 技能模板 |
| `/api/global-variables` | 全局变量（header / cookie / localStorage / variable 四类） |
| `/api/recordings` | 录制 |
| `/api/datasources` | 数据源（MySQL 等，支持测试连接与 SQL 查询） |
| `/api/data-views`、`/api/data` | 数据视图及其公开数据接口 |
| `/api/workspaces` | 项目空间 |
| `/api/requirements` | 需求 CRUD（删除守卫：其下有模块/用例则拒绝） |
| `/api/modules` | 模块 CRUD（删除守卫：其下有用例则拒绝） |
| `/api/test-cases` | 测试用例：CRUD、维度过滤（`?workspace_id=&requirement_id=&module_id=&status=`）、`PATCH /{id}/status` 单条状态、`POST /batch-status` 批量状态、`POST /import` Markdown 结构化导入 |
| `/api/code` | 代码检查/格式化（black） |
| `/api/mcp`、`/mcp` | MCP 服务 |
| `/api/ws/executions/{id}` | WebSocket：执行实时日志推送 |

测试用例状态：`pending`（未开始）、`in_progress`（进行中）、`completed`（已完成）、`blocked`（阻塞）。

交互式文档：启动后访问 `http://127.0.0.1:8000/docs`。

## 关键机制

- **脚本执行**：用户代码嵌入 `engine/runner.py` 的 `SCRIPT_TEMPLATE`（占位符 `.replace()`，禁用 `str.format()`），子进程执行，环境变量传入 `ATP_INPUTS` 等并强制 `PYTHONUNBUFFERED=1`；输出经 `__ATP_OUTPUTS__{json}` 标记回传，日志逐行经 WebSocket 推送。
- **异步执行**：run 接口先创建 `running` 状态的 Execution 立即响应，实际执行放 `asyncio.create_task` + 独立 `AsyncSessionLocal`，避免阻塞。
- **全局变量**：`header` 注入请求头、`localStorage` 执行前写入、`variable` 注入 `GLOBAL_VARS`；脚本以 `inherit_global` 控制继承。
- **数据模型约定**：无外键、无 relationship；父级归属用可空/必空 `xxx_id` bigint unsigned 列 + 索引 + 服务层校验；删除前由服务层统计子级并拒绝（如空间 → 脚本/流程/需求）。主键/ID 列统一 `BigIntUnsigned`（`database.py`），列带 `comment`。
- **MySQL 迁移**：无 Alembic。`database.py` 的 `init_db()` 在 `create_all` 后用 `inspect` + `ALTER TABLE` 为已有表补列（幂等；裸 SQL 标识符反引号、索引用 inspector 判断，兼容 MySQL/SQLite）。建表 DDL 由 `scripts/gen_mysql_ddl.py` 从模型生成到 `mysql_ddl.sql`（规范样式：列注释、varchar 默认值、`USING BTREE`、InnoDB + utf8mb4），改模型后必须重新生成。
- **临时执行脚本**写入系统临时目录（`config.executions_dir`），勿改回 `storage/`（`--reload` 会监听文件变化导致服务重启）。

## 配置

配置集中在 `app/config.py`，支持 `.env` 覆盖（样例见 `.env.example`）：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `database_url` | `mysql+aiomysql://root:***@127.0.0.1:3306/fishcode?charset=utf8mb4` | MySQL 地址（驱动后缀必须 `+aiomysql`） |
| `headless` | `True` | 浏览器是否无头运行 |
| `playwright_timeout` | `60000` (ms) | Playwright 操作超时 |
| `script_execution_timeout` | `120` (s) | 脚本执行超时，超时 kill |
| `sql_query_timeout` / `sql_max_rows` | `30` / `1000` | 数据源查询超时与行数上限 |

## 测试

```bash
source venv/bin/activate
pytest tests/
```

`tests/` 使用 pytest + httpx 的 `AsyncClient` 测试 FastAPI 接口。

## 安全说明

- 脚本以子进程执行任意 Python，仅适用于本地单用户场景，勿暴露到公网。
- 子进程环境变量仅透传 `PATH`、`PYTHONPATH`、`ATP_*`、`PYTHONUNBUFFERED`。
- CORS 仅允许 `http://localhost:5173`。
test tests/
```

`tests/` 使用 pytest + httpx 的 `AsyncClient` 测试 FastAPI 接口。

## 安全说明

- 脚本以子进程执行任意 Python，仅适用于本地单用户场景，勿暴露到公网。
- 子进程环境变量仅透传 `PATH`、`PYTHONPATH`、`ATP_*`、`PYTHONUNBUFFERED`。
- CORS 仅允许 `http://localhost:5173`。

# 小鱼（fishCode）

> **一切网页数据皆可采集。**

小鱼是一个本地运行的网页数据采集与自动化测试平台。只要浏览器能打开的页面——列表、详情、需要登录的内容、分页滚动加载的数据——编写（或让 AI 生成）一段 Playwright Python 脚本，就能把它变成稳定可重复调用的**采集接口**：可视化编排流程、高并发执行、实时查看日志与结果，并通过开放平台把采集能力以 API 形式提供给任意外部系统。

配套数据源管理、数据视图（SQL 对外取数）、测试用例管理，并内嵌 MCP 服务与 AI 助手，让智能体直接操作平台。

## 核心能力

- **脚本即采集器**：Monaco 编辑器编写 Playwright Python 脚本，参数化输入/输出定义；传入链接即可发起采集，结果结构化返回
- **流程编排**：Vue Flow 画布拖拽编排多个脚本节点，分层并行执行，节点间通过 `{{global.xxx}}`、`{{node_xxx.xxx}}` 模板语法传递变量
- **高并发执行**：Redis + arq 任务队列，独立 worker 进程按并发上限调度（每个执行 = 独立子进程 + Chromium），排队/执行状态可观测，崩溃自动恢复
- **实时日志**：日志总线逐行推送（WebSocket + 增量落库），断线重连不丢日志，晚连接可重放
- **开放平台**：为外部系统签发 App Key/Secret（HMAC-SHA256 签名认证），内置「传链接发起采集 / 查询采集结果 / 任务列表」三个开放接口，并支持把平台任意内部接口以代理方式封装给外部调用
- **登录态与凭证**：header / cookie / localStorage / variable 四类全局变量，按域名匹配自动注入采集环境
- **数据源与数据视图**：MySQL 等数据源连接管理与 SQL 工作台；数据视图以只读 SQL 对外提供 JSON 取数接口（`GET /api/data/{slug}`）
- **测试用例管理**：项目空间 → 需求 → 模块三级组织，Markdown 结构化导入，思维导图预览
- **MCP 服务与 AI 助手**：平台能力封装为 MCP 工具，供 Claude Code、Trae 等 AI 客户端直接编写脚本、发起采集、查询数据

## 界面预览

### 导入 MCP 和 Skills 后，使用 AI 创作脚本

输入你需要创作的脚本提示词

![](demo4.png)

### 脚本编辑与实时执行

一键运行并实时查看日志与结果：

![](demo1.png)

![](demo2.png)

![](demo3.png)

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13（全 async）、FastAPI、SQLAlchemy 2.0 异步 ORM、MySQL 8（aiomysql）、Playwright、Redis + arq（执行队列）、MCP |
| 前端 | Vue 3（`<script setup>` + TypeScript）、Element Plus、Pinia、Vue Flow（流程画布）、Monaco（代码/SQL 编辑）、markmap（思维导图） |

前后端分离 + 独立执行 worker 的三进程架构（API / worker / Redis），开发时由 Vite 代理 `/api`、`/storage`、`/mcp` 到后端。

## 快速开始

### 0）基础设施：MySQL 8 + Redis

```bash
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS fishcode DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -uroot -p fishcode < backend/mysql_ddl.sql   # 也可不执行，启动时 init_db 自动建表
redis-server --port 6390 --daemonize yes           # 执行队列（端口任意，与 .env 的 REDIS_URL 一致即可）
```

### 1）后端 API（端口 8000）

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # 首次需要
cp .env.example .env               # 按需修改 DATABASE_URL / REDIS_URL

uvicorn app.main:app --reload --port 8000
```

验证：`curl http://127.0.0.1:8000/api/health` → `{"status":"ok","queue":{...}}`

> DSN 必须带驱动后缀 `+aiomysql`，裸 `mysql://` 会去加载未安装的 MySQLdb 而报错。

### 2）执行 worker（独立进程，必启动）

```bash
cd backend
./venv/bin/python3 -m app.worker   # 无 --reload，改代码需手动重启
```

不启动 worker 时任务会停留在队列（接口正常返回 pending），`/api/health` 的 `queue.worker_alive=false` 可诊断。worker 带断线守护：Redis 瞬断自动重启，队列恢复后继续消费。

### 3）前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。

## 开放平台：把采集能力变成 API

在「开放平台 → 开放应用」创建应用获得 App Key / Secret，即可从任意外部系统发起采集：

```python
# 1) 传入链接，发起指定脚本采集（异步，立即返回 execution_id）
result = call_open_api(
    "POST",
    "/open/api/v1/collect/trigger",
    body={"url": "https://example.com/post/123", "script_id": 9},
)
execution_id = result["execution_id"]

# 2) 轮询采集结果（query 不参与签名，单独拼接）
result = call_open_api(
    "GET", "/open/api/v1/collect/result", query=f"execution_id={execution_id}"
)
print(result["status"], result["outputs"])   # 采集到的结构化数据
```

- 认证：`X-App-Key` / `X-Timestamp` / `X-Sign`（HMAC-SHA256，防重放）
- 还可将平台内部任意 `/api` 接口以代理方式封装成开放接口（服务端转发，外部不接触内部端口）
- 完整签名算法与调用示例见平台内「开放平台 → 接入文档」

## 页面一览

| 路由 | 说明 |
|---|---|
| `/` | 首页概览 |
| `/scripts` | 脚本管理（编辑、运行、实时日志） |
| `/flows` | 流程编排（画布） |
| `/executions` | 执行记录 |
| `/test-cases` | 测试用例管理 |
| `/workspaces` | 项目空间 |
| `/global-variables` | 全局变量（采集凭证与登录态） |
| `/datasources` | 数据源管理与 SQL 工作台 |
| `/data-views` | 数据视图（对外取数） |
| `/open-apps` | 开放平台：应用与密钥管理 |
| `/open-apis` | 开放平台：开放接口（内置采集 + 代理配置） |
| `/open-logs` | 开放平台：调用日志 |
| `/open-docs` | 开放平台：接入文档 |
| `/agent` | AI 助手（trae-cli 内嵌对话） |
| `/mcp` | MCP 服务状态与接入说明 |

## AI 助手与 MCP

平台内嵌 MCP 服务（端点 `/mcp`），将脚本、执行、项目空间、数据源查询等能力封装为工具；配套三个 Agent Skills（脚本编写/执行/维护）提供操作指引。

AI 助手页面（`/agent`）可一键完成接入：注册平台 MCP 到 trae-cli + 安装 Skills。之后在页面内直接对话，智能体即可编写采集脚本、发起执行、查询数据。

## 目录结构

```
├── AGENTS.md              # 架构指引（给 AI 与新成员的开发文档）
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── routers/       # HTTP 入口（薄层）
│   │   ├── services/      # 业务逻辑（日志总线/开放平台/采集编排等）
│   │   ├── models/        # SQLAlchemy 模型（列注释 + bigint unsigned 主键）
│   │   ├── schemas/       # Pydantic 出入参
│   │   ├── engine/        # 脚本执行引擎（SCRIPT_TEMPLATE + 子进程）
│   │   ├── worker.py      # 执行 worker（arq，断线守护）
│   │   ├── task_queue.py  # 任务队列接入（API 进程侧）
│   │   ├── mcp/           # MCP 服务端
│   │   └── agent_skills/  # Agent Skills 文档
│   ├── mysql_ddl.sql      # MySQL 建表 DDL（由 scripts/gen_mysql_ddl.py 生成）
│   ├── scripts/           # gen_mysql_ddl.py（DDL 生成）、migrate_sqlite_to_mysql.py（SQLite 存量迁移）
│   ├── tests/             # pytest 异步测试（66+ 用例）
│   └── storage/           # 附件存储
└── frontend/              # Vue 3 前端
    └── src/
        ├── api/           # Axios 封装
        ├── types/         # TS 接口
        ├── stores/        # Pinia store
        ├── views/         # 页面
        └── components/    # 复用组件
```

## 常用命令

```bash
# 基础设施
redis-server --port 6390 --daemonize yes      # 执行队列

# 后端
uvicorn app.main:app --reload --port 8000     # API 开发
./venv/bin/python3 -m app.worker              # 执行 worker（必启动）
pytest tests/                                 # 测试

# 前端
npm run dev          # 开发热重载
npm run build        # 类型检查 + 构建
npm run type-check   # 仅类型检查
npm run test:unit    # vitest
```

## 安全说明

- 脚本以子进程执行任意 Python，平台主体面向**本地单用户**场景；对外暴露能力请统一走「开放平台」的签名认证接口，勿将内部端口直接公开
- 开放接口签名含时间窗防重放，调用日志全量留痕；应用密钥可随时重新生成
- 数据源密码不明文回传；数据视图与 MCP 查询仅允许只读语句白名单
- CORS 仅允许本机前端地址

更多架构细节与开发约定见 [AGENTS.md](./AGENTS.md)。

# fishCode Frontend

小鱼（fishCode）前端：Vue 3 + TypeScript + Element Plus + Pinia，提供脚本管理、流程编排、执行监控、数据源工作台、测试用例管理等可视化界面。

## 技术栈

- Vue 3（`<script setup lang="ts">` 组合式 API）+ TypeScript
- Element Plus（全量手动注册，图标全局注册）
- Pinia（setup store 风格）+ Vue Router（扁平路由、懒加载）
- Axios（`api/client.ts` 裸实例，无拦截器）
- Monaco Editor（脚本/SQL 代码编辑）
- Vue Flow（流程画布）
- markmap-view（测试用例思维导图）

## 目录结构

```
frontend/src/
├── main.ts              # 入口：Element Plus 全量注册、图标循环注册
├── App.vue              # AppLayout 包裹 RouterView
├── router/index.ts      # 扁平路由，懒加载
├── api/                 # Axios 封装（每文件返回 AxiosPromise，调用方取 res.data）
│   └── client.ts        # 裸 axios 实例（baseURL /api，固定 JSON header）
├── types/               # TS 接口（snake_case，与后端 schema 一一对应）
├── stores/              # Pinia setup store（ref + async 函数包装 api）
├── views/               # 页面组件
├── components/          # 复用组件（AppLayout、ExecutionPanel、MindMapDialog 等）
└── utils/               # formatDateTime、markdownCases（MD 解析 + 思维导图数据构造）
```

## 快速开始

```bash
npm install
npm run dev          # 开发（5173 端口，代理 /api、/storage、/mcp 到后端 8000）
```

依赖后端先启动（见 `backend/README.md`）。

## 常用命令

```bash
npm run dev          # 开发热重载
npm run build        # 类型检查 + 生产构建
npm run type-check   # 仅 vue-tsc 类型检查
npm run test:unit    # vitest 单元测试
npm run preview      # 预览构建产物
```

## 页面清单

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | 首页 | 概览 |
| `/scripts`、`/scripts/:id` | 脚本管理 | 脚本列表、Monaco 编辑器、运行与实时日志（WebSocket + 轮询） |
| `/flows`、`/flows/:id` | 流程编排 | Vue Flow 画布，节点拓扑执行 |
| `/executions` | 执行记录 | 执行历史与状态 |
| `/test-cases` | 测试用例管理 | 项目空间/需求/模块三级组织，双维度树查看，单条/批量状态维护，Markdown 导入，思维导图预览 |
| `/workspaces` | 项目空间 | 侧边栏可全局切换当前空间 |
| `/global-variables` | 全局变量 | header / cookie / localStorage / variable 四类 |
| `/datasources`、`/datasources/:id/workbench` | 数据源 | 连接管理与 SQL 工作台（Monaco） |
| `/data-views` | 数据视图 | 数据视图配置 |
| `/mcp` | MCP 服务 | MCP 接入说明 |

## 约定

- 组件间通过 props/emit 通信，跨页面状态用 Pinia store。
- 时间展示统一用 `utils/format.ts` 的 `formatDateTime`。
- Element Plus 组件直接用标签；`ElMessage`、`ElMessageBox` 需显式导入。
- 新增页面：`views/` 加组件 → `router/index.ts` 加路由 → `components/AppLayout.vue` 的 `menuItems` 加菜单项（图标用 @element-plus/icons-vue 的组件名字符串）。
- 新增资源类型：`types/`（snake_case 接口）→ `api/`（AxiosPromise）→ `stores/`（setup store）→ `views/`。

## 测试用例导入的 Markdown 格式

```markdown
# 需求名（一级标题）
## 模块名（二级标题）
### 用例标题（三级标题）
前置条件：已登录
- 步骤 1
- 步骤 2
预期结果：显示成功提示
```

- `#` 需求名、`##` 模块、`###` 用例；H1 下的 H3 为无模块用例
- `前置/前提` 开头 → 前置条件；`预期/期望` 开头 → 预期结果；列表项/其他行 → 步骤

## Vite 代理

`vite.config.ts` 将 `/api`（含 WebSocket，`ws: true`）、`/storage`、`/mcp`（仅协议请求）代理到 `http://127.0.0.1:8000`。

## IDE 建议

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) 插件（禁用 Vetur）。

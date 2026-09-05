---
name: script-authoring
description: 在 fishcode 平台创建新的 Playwright 测试脚本，含代码模板约定（INPUTS/OUTPUTS/page/START_URL）与输入输出定义格式。用户要求编写/新建/生成测试脚本时使用。
---

# 编写新脚本

通过 MCP 服务 `fishcode-scripts` 创建脚本。代码体不需要任何 import——运行时模板已注入浏览器与全部内置变量。

## 前置：确定 workspace_id

`create_script` 必填 `workspace_id`。平台没有独立的列出空间工具，按此约定获取：

1. 先调 `list_scripts()`，从已有脚本里读取其 `workspace_id` 复用；
2. 平台为空时询问用户要使用哪个项目空间（可在后台「项目空间」页创建）。

## 字段结构

- `name`：脚本名；`description`：一句话说明用途；
- `start_url`：起始访问地址。登录态注入（localStorage/cookie 类型全局变量）依赖它，需要登录的站点务必填写；
- `inputs`：输入变量，元素结构 `{name, type, description, default, required}`，`type` ∈ `string|number|boolean|secret`；
- `outputs`：输出定义，元素结构 `{name, description}`。**代码里写入 `OUTPUTS` 的 key 必须与此处的 `name` 一一对应**；
- `inherit_global`：默认 `true`，需要登录态/全局请求头时保持默认。

## 需要登录验证的站点

创建前先调 `get_auth_credentials(域名或URL)` 确认平台是否已配置该站点的认证凭证（全局变量）：

- 有凭证：`start_url` 填站点地址、`inherit_global` 保持 `true`，执行时自动注入（无需在代码里手动处理）；
- 无凭证（四类均为空）：请用户先在后台「全局变量」页配置该域名的凭证，再创建脚本。

平台的「录制脚本」功能同样会按域名自动注入这批凭证（录制浏览器自带登录态）；引导用户录制前，可用 `get_auth_credentials` 先确认该站点凭证已配置，避免录制时被登录页拦截。

## 代码体约定

代码运行在模板的 `async def main()` 内、`async with async_playwright()` 上下文中，**直接写顶层逻辑即可**，可直接使用以下变量（无需导入）：

| 变量 | 说明 |
|---|---|
| `INPUTS` | 运行入参字典，取 `INPUTS["kw"]` |
| `OUTPUTS` | 结果字典，写 `OUTPUTS["result"] = ...` |
| `page` / `context` / `browser` | Playwright 对象，`page` 最常用 |
| `START_URL` | 脚本的起始 URL 字符串 |
| `GLOBAL_VARS` / `GLOBAL_HEADERS` | 全局变量 / 全局请求头 |
| `DATA_VIEWS` / `DATA_VIEWS_ONE` | 数据视图数据；后者取每个视图首行对象 |
| `expect` | Playwright 断言工具 |

要点：

- 这是 `async` 上下文，Playwright 调用需 `await`（如 `await page.goto(START_URL)`）；
- `print(...)` 是唯一的实时日志通道，关键步骤都打一行日志；
- 代码体内不要再 `import playwright` 或自行 `launch` 浏览器。

代码示例：

```python
keyword = INPUTS["keyword"]
await page.goto(START_URL)
await page.fill("#kw", keyword)
await page.click("#submit")
print("已提交搜索:", keyword)
OUTPUTS["result_url"] = page.url
```

## 标准流程

1. `create_script(...)` 创建；
2. `run_script(script_id, mode="mock")` 冒烟（自动生成输入）；
3. `get_execution(execution_id)` 轮询至 `finished=true`；
4. 若 `failed`，读 `logs` 末尾错误，`update_script` 修正后重跑。

---
name: script-execution
description: 运行 fishcode 测试脚本并轮询执行结果，使用 run_script + get_execution 异步两步式。用户要求运行/执行/验证/冒烟脚本时使用。
---

# 运行脚本并获取结果

脚本执行是异步的：`run_script` 将任务提交执行队列并立即返回 `execution_id`，结果需用 `get_execution` 轮询获取。

## 两步式流程

1. **启动**：`run_script(script_id, inputs={...}, mode="manual"|"mock", headless=true)`
   - 立即返回 `{execution_id, status}`，不等执行完成；`status` 可能为 `pending`（排队中，等待 worker 并发配额）或 `running`；
2. **轮询**：每 3-5 秒调用一次 `get_execution(execution_id)`，直到 `finished` 为 `true`；
   - 脚本默认超时 120s（排队时间另计），轮询预算建议留足（≥ 30 次）。

## 运行模式

- `mode="manual"` + `inputs`：使用真实入参，适合正式验证；
- `mode="mock"`：按输入定义自动生成 mock 入参，适合冒烟测试、无需真实数据；
- `headless=false`：本地弹出浏览器窗口观察过程（仅调试用）。

入参只需提供脚本 `inputs` 中定义且必填（或需要覆盖默认值）的字段，例如脚本定义了 `kw`（string，required）则传 `{"kw": "关键词"}`。

## 结果解读

`get_execution` 返回：

- `status`：`pending`（排队中）/ `running` / `success` / `failed`；`finished=true` 时 `logs` 与 `outputs` 为最终值；
- `success`：检查 `outputs` 字典是否与脚本 `outputs` 定义一致；
- `failed`：重点看 `logs` 末尾的 `Error:` 行与 Traceback；
  - 常见原因：选择器超时（页面结构变化/未等到元素）、缺少必填输入、`start_url` 未配置导致登录态未注入。

## 登录态问题排查

失败日志出现跳转登录页、401/403、验证码页或「未登录」类错误时：

1. `get_script(script_id)` 检查 `start_url` 是否填写、`inherit_global` 是否为 `true`（登录态注入依赖这两项）；
2. `get_auth_credentials(站点域名或URL)` 查询平台是否已配置该域名的凭证（返回 headers/cookies/localStorage/vars 四类）；
3. 四类均为空 → 请用户先在后台「全局变量」页配置该域名凭证，再重跑；有凭证但仍失败 → 多为凭证过期，请用户更新全局变量值。

## 排障闭环

失败时：`get_script(script_id)` 复查代码与输入定义 → `update_script` 修正（如放宽等待、修正选择器）→ 重新 `run_script`。连续两次失败应向用户说明日志关键错误。

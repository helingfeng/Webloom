---
name: script-maintenance
description: 查找、查看、修改与删除 fishcode 平台已有测试脚本；update_script 为部分更新语义。用户要求修改/优化/清理/排查脚本时使用。
---

# 维护已有脚本

## 查找与查看

1. `list_scripts(workspace_id=...)` 定位目标脚本（可按项目空间过滤）；
2. **动手修改前先 `get_script(script_id)` 读完整代码**，列表接口不含代码全文细节；
3. 按 `name`/`description` 判断是否为目标脚本，避免改错。

## 部分更新语义（重要）

`update_script` 只更新显式传入的字段，未传字段保持原值：

- `name`、`description`、`start_url`、`code`、`inherit_global`、`run_mode`（manual|mock）、`headless`、`workspace_id` 均可单独更新；
- **`inputs` / `outputs` 一旦传入即整体替换**，必须给完整数组——修改某个输入变量时，先读旧数组、在其基础上改、再整体传回；
- 传 `null`/不传 = 不修改；传空字符串 `""` = 清空该字段。

示例：给脚本追加一个输入变量

```
1. get_script(id) → 取 inputs 旧数组
2. 新数组 = 旧数组 + [{"name": "limit", "type": "number", "default": 10, "required": false}]
3. update_script(script_id=id, inputs=新数组)
```

## 危险操作：删除

`delete_script` 不可恢复。删除前必须：

1. `get_script(script_id)` 确认存在；
2. 向用户复述将删除的脚本名与 id，获得确认后再执行。

## 常见错误

- `脚本 N 不存在`：id 有误或已被删除，重新 `list_scripts` 确认；
- `项目空间 N 不存在`：`update_script` 迁移空间时目标 `workspace_id` 无效。

## 登录态与凭证

脚本因未登录/401/跳转登录页失败时：

1. 确认脚本 `start_url` 已填、`inherit_global` 为 `true`（登录态注入依赖这两项）；
2. `get_auth_credentials(站点域名或URL)` 查平台是否已配置该域名的认证凭证（全局变量），录制功能也复用同一套凭证注入；
3. 未配置或过期 → 请用户到后台「全局变量」页按域名维护凭证，无需改脚本代码。

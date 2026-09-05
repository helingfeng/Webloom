from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.skill import Skill


async def get_skills(db: AsyncSession) -> list[Skill]:
    result = await db.execute(select(Skill).order_by(Skill.id))
    return result.scalars().all()


async def get_skill(db: AsyncSession, skill_id: int) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def ensure_default_skills(db: AsyncSession) -> None:
    result = await db.execute(select(Skill))
    existing = {s.name: s for s in result.scalars().all()}

    # 默认 Skill 为系统内置（无编辑入口），模板变更时同步刷新已存在的记录
    defaults = [
        _build_login_skill(),
        _build_inspect_skill(),
        _build_verify_new_data_skill(),
    ]
    for default in defaults:
        row = existing.get(default.name)
        if row is None:
            db.add(default)
        elif (
            row.prompt_template != default.prompt_template
            or row.example_code != default.example_code
        ):
            row.description = default.description
            row.prompt_template = default.prompt_template
            row.example_code = default.example_code
            row.example_inputs = default.example_inputs
            row.example_outputs = default.example_outputs

    await db.commit()


def _build_login_skill() -> Skill:
    return Skill(
        name="登录脚本创建 Skill",
        description="用于创建登录型 Playwright 测试脚本，输出登录凭证",
        prompt_template="""你是一名 Playwright 自动化测试专家。请为本平台创建一个自动化测试脚本。

## 脚本规则

1. 只定义脚本的输入/输出结构，通过输入变量接收参数，通过 OUTPUTS 返回结果
2. 使用 async/await 编写 Playwright Python 代码片段
3. 可用对象：INPUTS、OUTPUTS、GLOBAL_HEADERS、GLOBAL_VARS、GLOBAL_LOCAL_STORAGE、page、context、browser
4. 需要使用 Playwright 录制获取真实的页面数据（真实访问页面、真实 selector、真实交互），禁止凭空编造页面结构和数据
5. selector 优先使用 id、name、placeholder、type 等稳定属性
6. 登录类脚本需将登录凭证（cookie / localStorage / token）写入 OUTPUTS，供下游脚本复用
7. 断言规范：
   - 页面关键状态校验优先用 Playwright 内置断言，expect 已由模板导入可直接使用，例如：await expect(page.locator('#userName')).to_be_visible()、await expect(page).to_have_title('工作台')
   - 自定义校验用 assert 条件, "失败说明" 或 raise AssertionError("失败说明")，断言失败会中断脚本，本次执行标记为 failed
   - 若失败时仍需返回数据（如错误信息、部分凭证），改用软校验：将 status=failed 与 error 写入 OUTPUTS，不要抛异常
   - 断言明细建议汇总到 OUTPUTS["assertions"]（list，每条含 name/passed/expected/actual），便于在执行结果中逐条查看
8. 只输出代码片段，不需要 import 和包装代码

## 目标 URL

{start_url}

## 输入变量结构

- username（string，必填）：登录用户名
- password（secret，必填）：登录密码

## 输出结构

- status（string）：登录结果，success / failed
- current_url（string）：登录后所在页面 URL
- error（string）：失败时的错误信息
- cookies（list）：登录后的 cookies（如系统使用）
- localStorage（dict）：登录后的 localStorage（如系统使用）
- assertions（list）：断言明细，每条含 name / passed / expected / actual

## 业务流程

需要根据以下脚本规则来编写业务流程（先访问目标 URL 录制真实页面，再实现流程）：

{业务流程：请在此描述具体的登录步骤，例如"打开登录页 → 填入账号密码 → 填入验证码 → 点击登录 → 校验跳转后的页面"}""",
        example_code='''await page.goto(INPUTS.get("start_url") or START_URL)
await expect(page.locator('#userName')).to_be_visible()  # 断言：登录表单已加载
await page.locator('#userName').fill(INPUTS["username"])
await page.locator('#password').fill(INPUTS["password"])
await page.locator('button[type="submit"]').click()
await page.wait_for_timeout(2000)
if "/user/login" not in page.url:
    OUTPUTS["status"] = "success"
    OUTPUTS["current_url"] = page.url
    OUTPUTS["localStorage"] = await page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
    OUTPUTS["assertions"] = [
        {"name": "登录后离开登录页", "passed": True, "expected": "非登录页", "actual": page.url},
    ]
else:
    OUTPUTS["status"] = "failed"
    OUTPUTS["current_url"] = page.url
    OUTPUTS["error"] = "登录后仍在登录页"
    OUTPUTS["assertions"] = [
        {"name": "登录后离开登录页", "passed": False, "expected": "非登录页", "actual": page.url},
    ]''',
        example_inputs=[
            {"name": "username", "type": "string", "description": "登录用户名", "required": True},
            {"name": "password", "type": "secret", "description": "登录密码", "required": True},
        ],
        example_outputs=[
            {"name": "status", "description": "登录结果 success/failed"},
            {"name": "current_url", "description": "登录后所在页面 URL"},
            {"name": "error", "description": "失败时的错误信息"},
            {"name": "cookies", "description": "登录后的 cookies"},
            {"name": "localStorage", "description": "登录后的 localStorage"},
            {"name": "assertions", "description": "断言明细（name/passed/expected/actual）"},
        ],
    )


def _build_inspect_skill() -> Skill:
    return Skill(
        name="查看网页数据 Skill",
        description="用于创建网页数据采集脚本：打开页面后提取文本、表格、接口返回等数据写入 OUTPUTS",
        prompt_template="""你是一名 Playwright 自动化测试专家。请为本平台创建一个网页数据采集脚本。

## 脚本规则

1. 只定义脚本的输入/输出结构，通过输入变量接收参数，通过 OUTPUTS 返回采集到的数据
2. 使用 async/await 编写 Playwright Python 代码片段
3. 可用对象：INPUTS、OUTPUTS、GLOBAL_HEADERS、GLOBAL_VARS、GLOBAL_LOCAL_STORAGE、page、context、browser
4. 需要使用 Playwright 录制获取真实的页面数据（真实访问页面、真实 selector、真实接口），禁止凭空编造页面结构和数据
5. selector 优先使用 id、name、class 语义化选择器、data-* 等稳定属性，避免依赖动态生成的 class
6. 采集数据脚本通常需要登录态：如平台已配置全局变量（localStorage/Header），脚本会自动携带，无需额外处理登录
7. 采集的数据统一写入 OUTPUTS，键名语义化；列表数据输出为 list，逐条数据输出为 dict
8. 如页面数据来自接口（XHR/fetch），优先用 page.expect_response / page.on("response") 监听接口拿结构化 JSON，比解析 DOM 更稳定
9. 断言规范：
   - 采集前的页面就绪校验优先用 Playwright 内置断言，expect 已由模板导入可直接使用，例如：await expect(page.locator("table tbody tr").first).to_be_visible()
   - 数据校验用 assert（如 assert data, "未采集到数据"），断言失败会中断脚本，本次执行标记为 failed
   - 若失败时仍需返回已采集到的部分数据，改用软校验：将 status=failed 与 error 写入 OUTPUTS，不要抛异常
   - 断言明细建议汇总到 OUTPUTS["assertions"]（list，每条含 name/passed/expected/actual）
10. 只输出代码片段，不需要 import 和包装代码

## 目标 URL

{start_url}

## 输入变量结构

- start_url（string，可选）：要访问的页面地址，默认用脚本配置的起始 URL
- wait_seconds（number，可选）：页面加载数据的等待秒数，默认 3

## 输出结构

- status（string）：采集结果，success / failed
- page_title（string）：页面标题
- current_url（string）：实际访问后的 URL
- data（list/dict）：采集到的数据主体
- error（string）：失败时的错误信息
- assertions（list）：断言明细，每条含 name / passed / expected / actual

## 业务流程

需要根据以下脚本规则来编写业务流程（先访问目标 URL 录制真实页面，确认数据所在位置，再实现流程）：

{业务流程：请在此描述要采集的数据和位置，例如"打开商品列表页 → 等待列表加载 → 抓取每条商品的名称、价格、链接 → 翻页采集 3 页 → 汇总输出"}""",
        example_code='''# 采集页面数据示例：打开列表页，等待渲染，提取表格/列表数据
await page.goto(INPUTS.get("start_url") or START_URL)
await expect(page.locator("table tbody tr").first).to_be_visible()  # 断言：列表数据已渲染
await page.wait_for_timeout(int(INPUTS.get("wait_seconds", 3)) * 1000)

OUTPUTS["page_title"] = await page.title()
OUTPUTS["current_url"] = page.url

# 示例 1：提取列表数据（按实际 selector 调整）
rows = await page.locator("table tbody tr").all()
data = []
for row in rows:
    data.append({
        "name": await row.locator("td").nth(0).inner_text(),
        "price": await row.locator("td").nth(1).inner_text(),
    })
assert data, "未采集到数据"  # 断言：至少采集到一条数据
OUTPUTS["data"] = data
OUTPUTS["status"] = "success"''',
        example_inputs=[
            {"name": "start_url", "type": "string", "description": "要采集的页面地址", "required": False},
            {"name": "wait_seconds", "type": "number", "description": "等待页面加载秒数，默认 3", "required": False},
        ],
        example_outputs=[
            {"name": "status", "description": "采集结果 success/failed"},
            {"name": "page_title", "description": "页面标题"},
            {"name": "current_url", "description": "实际访问后的 URL"},
            {"name": "data", "description": "采集到的数据主体（list 或 dict）"},
            {"name": "error", "description": "失败时的错误信息"},
            {"name": "assertions", "description": "断言明细（name/passed/expected/actual）"},
        ],
    )


def _build_verify_new_data_skill() -> Skill:
    return Skill(
        name="查看新增数据 Skill",
        description="用于创建校验新增数据的脚本：提交/创建数据后，到列表页检索并提取新增的那条记录，确认写入成功",
        prompt_template="""你是一名 Playwright 自动化测试专家。请为本平台创建一个校验新增数据的脚本。

## 脚本规则

1. 只定义脚本的输入/输出结构，通过输入变量接收参数，通过 OUTPUTS 返回校验结果和新增数据
2. 使用 async/await 编写 Playwright Python 代码片段
3. 可用对象：INPUTS、OUTPUTS、GLOBAL_HEADERS、GLOBAL_VARS、GLOBAL_LOCAL_STORAGE、page、context、browser
4. 需要使用 Playwright 录制获取真实的页面数据（真实访问页面、真实 selector、真实交互），禁止凭空编造页面结构和数据
5. selector 优先使用 id、name、placeholder、type、data-* 等稳定属性，避免依赖动态生成的 class
6. 定位新增记录优先使用列表页的搜索/筛选功能缩小范围（按名称、编号等唯一字段检索），避免翻页遍历
7. 找到新增记录后，提取该条记录的关键字段写入 OUTPUTS["data"]（dict），字段名与页面列名对应
8. 校验结果写入 OUTPUTS["found"]（boolean）；新增数据通常在提交流程之后，可配合流程编排用 {{node_xxx.xxx}} 引用上游脚本输出的字段（如订单号、名称）作为检索关键字
9. 断言规范：
   - 列表加载、搜索结果出现优先用 Playwright 内置断言，expect 已由模板导入可直接使用，例如：await expect(page.locator("table tbody tr").first).to_be_visible()
   - 找不到新增记录属业务失败：用软校验，将 status=failed、error 与 found=false 写入 OUTPUTS，不要抛异常（便于排查数据是否落库）
   - 页面结构异常（列表没渲染、搜索框找不到）才用 assert / raise 中断脚本
   - 断言明细汇总到 OUTPUTS["assertions"]（list，每条含 name/passed/expected/actual）
10. 只输出代码片段，不需要 import 和包装代码

## 目标 URL

{start_url}

## 输入变量结构

- start_url（string，可选）：列表页地址，默认用脚本配置的起始 URL
- keyword（string，必填）：检索新增数据的关键字（名称、编号等唯一字段，可由上游脚本输出传入）
- wait_seconds（number，可选）：检索后等待结果加载的秒数，默认 3

## 输出结构

- status（string）：校验结果，success / failed
- found（boolean）：是否找到新增数据
- data（dict）：新增记录的关键字段（找到时）
- current_url（string）：检索后的页面 URL
- error（string）：失败时的错误信息
- assertions（list）：断言明细，每条含 name / passed / expected / actual

## 业务流程

需要根据以下脚本规则来编写业务流程（先访问目标 URL 录制真实页面，确认搜索框与列表结构，再实现流程）：

{业务流程：请在此描述要校验的新增数据和检索方式，例如"打开订单列表页 → 按订单号搜索 → 找到刚创建的订单 → 提取订单号、金额、状态 → 校验状态为已支付"}""",
        example_code='''# 校验新增数据示例：打开列表页，按关键字检索，提取新增的那条记录
await page.goto(INPUTS.get("start_url") or START_URL)
await expect(page.locator("table tbody tr").first).to_be_visible()  # 断言：列表已加载

# 按关键字检索新增记录（按实际搜索框 selector 调整）
keyword = str(INPUTS["keyword"])
await page.locator('input[name="keyword"]').fill(keyword)
await page.locator('button[type="submit"]').click()
await page.wait_for_timeout(int(INPUTS.get("wait_seconds", 3)) * 1000)

OUTPUTS["current_url"] = page.url

# 提取命中的第一条记录
row = page.locator("table tbody tr").first
OUTPUTS["found"] = await row.count() > 0
if OUTPUTS["found"]:
    OUTPUTS["data"] = {
        "name": await row.locator("td").nth(0).inner_text(),
        "price": await row.locator("td").nth(1).inner_text(),
        "status": await row.locator("td").nth(2).inner_text(),
    }
    OUTPUTS["status"] = "success"
else:
    OUTPUTS["status"] = "failed"
    OUTPUTS["error"] = f"列表中未找到新增数据: {keyword}"
OUTPUTS["assertions"] = [
    {"name": "列表中存在新增数据", "passed": OUTPUTS["found"], "expected": keyword, "actual": "已找到" if OUTPUTS["found"] else "未找到"},
]''',
        example_inputs=[
            {"name": "start_url", "type": "string", "description": "列表页地址", "required": False},
            {"name": "keyword", "type": "string", "description": "检索新增数据的关键字（可由上游脚本输出传入）", "required": True},
            {"name": "wait_seconds", "type": "number", "description": "检索后等待秒数，默认 3", "required": False},
        ],
        example_outputs=[
            {"name": "status", "description": "校验结果 success/failed"},
            {"name": "found", "description": "是否找到新增数据"},
            {"name": "data", "description": "新增记录的关键字段（dict）"},
            {"name": "current_url", "description": "检索后的页面 URL"},
            {"name": "error", "description": "失败时的错误信息"},
            {"name": "assertions", "description": "断言明细（name/passed/expected/actual）"},
        ],
    )

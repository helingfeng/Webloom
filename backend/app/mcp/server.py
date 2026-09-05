"""平台能力 MCP 服务（脚本管理 + 测试用例管理 + 数据源查询）：FastMCP + streamable http，嵌入现有 FastAPI 进程。"""

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from app.database import AsyncSessionLocal
from app.schemas.datasource import DatasourceOut
from app.schemas.execution import ExecutionOut
from app.schemas.module import ModuleCreate, ModuleOut
from app.schemas.requirement import RequirementCreate, RequirementOut
from app.schemas.script import (
    OutputDefinition,
    ScriptCreate,
    ScriptOut,
    ScriptUpdate,
    VariableDefinition,
)
from app.schemas.test_case import (
    CaseStatus,
    ImportCaseIn,
    ImportModuleIn,
    TestCaseCreate,
    TestCaseImportIn,
    TestCaseOut,
    TestCaseUpdate,
)
from app.schemas.workspace import WorkspaceOut
from app.services import (
    datasource_query_service,
    datasource_service,
    execution_service,
    global_variable_service,
    module_service,
    requirement_service,
    script_service,
    test_case_service,
    workspace_service,
)
from app.services.global_variable_service import extract_domain
from app.services.script_run_service import start_script_execution

INSTRUCTIONS = """小鱼（fishcode）自动化测试与数据采集平台 MCP 服务：脚本管理 + 测试用例管理 + 数据源查询。

约定：
1. 用 list_workspaces 查项目空间列表（拿 workspace_id），用 list_scripts 查脚本
   （可按 workspace_id 过滤），get_script 看完整代码与参数定义；
2. create_script 创建、update_script 部分更新（只传需要改的字段）、delete_script 删除；
3. 运行是异步两步式：run_script 立即返回 execution_id，随后每 3-5 秒调用
   get_execution(execution_id) 轮询，直到 finished 为 true；
4. 脚本代码体内可直接使用 INPUTS / OUTPUTS / GLOBAL_VARS / GLOBAL_HEADERS /
   GLOBAL_LOCAL_STORAGE 与 page / context / browser，无需自行导入；
5. 目标站点需要登录验证时，用 get_auth_credentials(域名或URL) 查询平台已配置的
   认证凭证（全局变量），返回结构可直接用于注入登录态；
6. 查询业务数据：list_datasources 拿 datasource_id → list_databases 选库 →
   list_tables / get_table_schema 看表与结构 → query_database 执行只读 SQL；
   list_tables / get_table_schema / query_database 的 database 参数可指定库，
   缺省用数据源默认库；
7. 测试用例管理（项目空间 → 需求 → 模块 → 用例三级组织）：list_requirements /
   list_modules 逐级定位，list_test_cases 可按空间/需求/模块/状态过滤，
   get_test_case 看详情；create_test_case 新增、update_test_case 部分更新
   （module_id 传 0 表示移出模块）、batch_update_test_case_status 批量改状态、
   delete_test_case / batch_delete_test_cases 删除；需要把需求文档批量转成
   用例时用 import_test_cases（自动创建缺失的需求与模块，模块按名复用）。"""

mcp = FastMCP("fishcode-scripts", instructions=INSTRUCTIONS)


def _dump(obj: Any, schema_cls: type) -> dict:
    """ORM 对象 -> Pydantic schema -> JSON 可序列化 dict（datetime 转 ISO 字符串）。"""
    return schema_cls.model_validate(obj).model_dump(mode="json")


@mcp.tool()
async def list_workspaces() -> str:
    """列出所有项目空间。返回 JSON 数组字符串，元素含 id、name、description。
    创建脚本、按空间过滤脚本等操作需要 workspace_id 时，先用本工具查询。"""
    async with AsyncSessionLocal() as db:
        items = await workspace_service.get_workspaces(db)
    return json.dumps([_dump(w, WorkspaceOut) for w in items], ensure_ascii=False)


@mcp.tool()
async def list_scripts(
    workspace_id: int | None = None, skip: int = 0, limit: int = 100
) -> str:
    """列出测试脚本，可按项目空间过滤。返回 JSON 数组字符串，
    元素含 id、name、inputs/outputs 定义等。"""
    async with AsyncSessionLocal() as db:
        items = await script_service.get_scripts(
            db, skip=skip, limit=limit, workspace_id=workspace_id
        )
    return json.dumps([_dump(s, ScriptOut) for s in items], ensure_ascii=False)


@mcp.tool()
async def get_script(script_id: int) -> dict:
    """获取单个脚本详情（含完整代码、输入输出定义、是否继承全局变量）。"""
    async with AsyncSessionLocal() as db:
        script = await script_service.get_script(db, script_id)
    if not script:
        raise ToolError(f"脚本 {script_id} 不存在")
    return _dump(script, ScriptOut)


@mcp.tool()
async def create_script(
    workspace_id: int,
    name: str,
    description: str = "",
    start_url: str = "",
    inputs: list[VariableDefinition] = [],
    outputs: list[OutputDefinition] = [],
    code: str = "",
    inherit_global: bool = True,
    run_mode: Literal["manual", "mock"] = "manual",
    headless: bool = True,
) -> dict:
    """创建脚本。inputs 元素结构 {name, type(string|number|boolean|secret),
    description, default, required}；outputs 元素结构 {name, description}。
    workspace_id 必须是已存在的项目空间（可先从 list_scripts 结果中获得）。"""
    try:
        payload = ScriptCreate(
            workspace_id=workspace_id,
            name=name,
            description=description,
            start_url=start_url,
            inputs=inputs,
            outputs=outputs,
            code=code,
            inherit_global=inherit_global,
            run_mode=run_mode,
            headless=headless,
        )
    except ValidationError as exc:
        raise ToolError(f"inputs/outputs 定义格式不合法: {exc}") from exc
    async with AsyncSessionLocal() as db:
        try:
            script = await script_service.create_script(db, payload)
        except ValueError as exc:  # 项目空间不存在
            raise ToolError(str(exc)) from exc
    return _dump(script, ScriptOut)


@mcp.tool()
async def update_script(
    script_id: int,
    name: str | None = None,
    description: str | None = None,
    start_url: str | None = None,
    workspace_id: int | None = None,
    inputs: list[VariableDefinition] | None = None,
    outputs: list[OutputDefinition] | None = None,
    code: str | None = None,
    inherit_global: bool | None = None,
    run_mode: Literal["manual", "mock"] | None = None,
    headless: bool | None = None,
) -> dict:
    """部分更新脚本：只更新显式传入的字段，未传字段保持原值。
    注意 inputs/outputs 一旦传入即整体替换，需给完整数组。"""
    async with AsyncSessionLocal() as db:
        script = await script_service.get_script(db, script_id)
        if not script:
            raise ToolError(f"脚本 {script_id} 不存在")
        # read-merge-write：ScriptUpdate 是全量 schema，以当前值为基底合并
        merged: dict[str, Any] = {
            "workspace_id": script.workspace_id,
            "name": script.name,
            "description": script.description,
            "start_url": script.start_url,
            "inputs": script.inputs or [],
            "outputs": script.outputs or [],
            "code": script.code,
            "inherit_global": script.inherit_global,
            "run_mode": script.run_mode,
            "headless": script.headless,
        }
        if name is not None:
            merged["name"] = name
        if description is not None:
            merged["description"] = description
        if start_url is not None:
            merged["start_url"] = start_url
        if workspace_id is not None:
            merged["workspace_id"] = workspace_id
        if code is not None:
            merged["code"] = code
        if inherit_global is not None:
            merged["inherit_global"] = inherit_global
        if run_mode is not None:
            merged["run_mode"] = run_mode
        if headless is not None:
            merged["headless"] = headless
        try:
            if inputs is not None:
                merged["inputs"] = [i.model_dump() for i in inputs]
            if outputs is not None:
                merged["outputs"] = [o.model_dump() for o in outputs]
            updated = await script_service.update_script(
                db, script, ScriptUpdate(**merged)
            )
        except (ValueError, ValidationError) as exc:
            raise ToolError(str(exc)) from exc
    return _dump(updated, ScriptOut)


@mcp.tool()
async def delete_script(script_id: int) -> dict:
    """删除脚本（不可恢复）。"""
    async with AsyncSessionLocal() as db:
        script = await script_service.get_script(db, script_id)
        if not script:
            raise ToolError(f"脚本 {script_id} 不存在")
        await script_service.delete_script(db, script)
    return {"deleted": script_id}


@mcp.tool()
async def run_script(
    script_id: int,
    inputs: dict[str, Any] | None = None,
    mode: Literal["manual", "mock"] | None = None,
    headless: bool | None = None,
) -> dict:
    """异步运行脚本，立即返回 execution_id（不等执行完成）。
    mode=manual 使用 inputs 实参；mode=mock 按定义自动生成 mock 输入；
    不传 mode 时使用脚本保存的 run_mode，不传 headless 时使用脚本保存的 headless。
    之后用 get_execution(execution_id) 轮询，建议间隔 3-5 秒。"""
    async with AsyncSessionLocal() as db:
        script = await script_service.get_script(db, script_id)
        if not script:
            raise ToolError(f"脚本 {script_id} 不存在")
        execution = await start_script_execution(
            db,
            script,
            mode=mode or script.run_mode,
            inputs=inputs or {},
            headless=script.headless if headless is None else headless,
        )
    return {
        "execution_id": execution.id,
        "status": "running",
        "next_step": "调用 get_execution(execution_id) 轮询，直到 finished 为 true",
    }


@mcp.tool()
async def get_execution(execution_id: int) -> dict:
    """查询执行结果：status 为 running/success/failed；finished=true 时
    logs 与 outputs 为最终值。"""
    async with AsyncSessionLocal() as db:
        execution = await execution_service.get_execution(db, execution_id)
    if not execution:
        raise ToolError(f"执行记录 {execution_id} 不存在")
    data = _dump(execution, ExecutionOut)
    data["finished"] = execution.status in ("success", "failed")
    return data


@mcp.tool()
async def get_auth_credentials(domain_or_url: str) -> dict:
    """按域名查询平台已配置的认证凭证（全局变量），用于访问需要登录验证的站点。

    参数可传完整 URL（如 https://admin.example.com/login）或纯域名（如 admin.example.com）。
    匹配规则与脚本执行/录制一致：域名精确或子域名匹配，未绑定域名的凭证全局生效。
    返回结构与录制器注入凭证（applied_globals）一致：
    - headers：请求头字典，对应 new_context(extra_http_headers=headers)；
    - cookies：Playwright add_cookies 格式列表，对应 context.add_cookies(cookies)；
    - localStorage：键值字典，需先 goto 站点再用 localStorage.setItem 逐条写入；
    - vars：普通全局变量字典，代码内作业务数据使用。
    若脚本设置 inherit_global=true 并填写了 start_url，执行时会自动注入，无需手动处理；
    本工具用于先确认平台是否已配置凭证、或在代码中按需自行注入。"""
    target = domain_or_url.strip()
    if not target:
        raise ToolError("domain_or_url 不能为空")
    # 纯域名补 scheme，保证 extract_domain（urlparse）能解析出 host
    start_url = target if "://" in target else f"https://{target}"
    host = extract_domain(start_url)
    if not host:
        raise ToolError(f"无法从 {domain_or_url} 解析出域名")
    async with AsyncSessionLocal() as db:
        headers = await global_variable_service.get_active_headers(db, start_url)
        gvars = await global_variable_service.get_active_vars(db, start_url)
        local_storage = await global_variable_service.get_active_local_storage(
            db, start_url
        )
        cookies = await global_variable_service.get_active_cookies(db, start_url)
    return {
        "domain": host,
        "headers": headers,
        "cookies": cookies,
        "localStorage": local_storage,
        "vars": gvars,
    }


# ---------- 测试用例管理 ----------


@mcp.tool()
async def list_requirements(workspace_id: int | None = None) -> str:
    """列出需求，可按项目空间过滤。返回 JSON 数组字符串，元素含 id、workspace_id、
    name、description。测试用例挂在需求下（可再按模块分组），创建/查询用例前先用
    本工具拿 requirement_id。"""
    async with AsyncSessionLocal() as db:
        items = await requirement_service.get_requirements(
            db, workspace_id=workspace_id
        )
    return json.dumps([_dump(r, RequirementOut) for r in items], ensure_ascii=False)


@mcp.tool()
async def create_requirement(
    workspace_id: int, name: str, description: str = ""
) -> dict:
    """在项目空间下创建需求（测试用例的一级组织）。
    workspace_id 可从 list_workspaces 结果中获得。"""
    async with AsyncSessionLocal() as db:
        try:
            req = await requirement_service.create_requirement(
                db,
                RequirementCreate(
                    workspace_id=workspace_id, name=name, description=description
                ),
            )
        except ValueError as exc:  # 项目空间不存在
            raise ToolError(str(exc)) from exc
    return _dump(req, RequirementOut)


@mcp.tool()
async def list_modules(requirement_id: int) -> str:
    """列出需求下的模块。返回 JSON 数组字符串，元素含 id、requirement_id、name。
    用例可挂在模块下，创建用例前先用本工具拿 module_id。"""
    async with AsyncSessionLocal() as db:
        items = await module_service.get_modules(db, requirement_id=requirement_id)
    return json.dumps([_dump(m, ModuleOut) for m in items], ensure_ascii=False)


@mcp.tool()
async def create_module(requirement_id: int, name: str) -> dict:
    """在需求下创建模块（测试用例的二级分组）。"""
    async with AsyncSessionLocal() as db:
        try:
            module = await module_service.create_module(
                db, ModuleCreate(requirement_id=requirement_id, name=name)
            )
        except ValueError as exc:  # 需求不存在
            raise ToolError(str(exc)) from exc
    return _dump(module, ModuleOut)


@mcp.tool()
async def list_test_cases(
    workspace_id: int | None = None,
    requirement_id: int | None = None,
    module_id: int | None = None,
    status: CaseStatus | None = None,
) -> str:
    """列出测试用例，可按项目空间/需求/模块/状态过滤（requirement_id 优先于
    workspace_id）。返回 JSON 数组字符串，元素含 id、requirement_id、module_id、
    title、steps、expected_result、status 等。
    status 取值 pending（未开始）/in_progress（进行中）/completed（已完成）/
    blocked（阻塞）。"""
    async with AsyncSessionLocal() as db:
        items = await test_case_service.get_test_cases(
            db,
            workspace_id=workspace_id,
            requirement_id=requirement_id,
            module_id=module_id,
            status=status,
        )
    return json.dumps([_dump(c, TestCaseOut) for c in items], ensure_ascii=False)


@mcp.tool()
async def get_test_case(case_id: int) -> dict:
    """获取单个测试用例详情（标题、前置条件、步骤、预期结果、状态）。"""
    async with AsyncSessionLocal() as db:
        case = await test_case_service.get_test_case(db, case_id)
    if not case:
        raise ToolError(f"测试用例 {case_id} 不存在")
    return _dump(case, TestCaseOut)


@mcp.tool()
async def create_test_case(
    requirement_id: int,
    title: str,
    module_id: int | None = None,
    precondition: str = "",
    steps: list[str] = [],
    expected_result: str = "",
    status: CaseStatus = "pending",
) -> dict:
    """创建测试用例。挂在需求下，module_id 可选（不传则直属于需求）。
    steps 为有序步骤字符串数组；status 取值 pending/in_progress/completed/blocked。"""
    try:
        payload = TestCaseCreate(
            requirement_id=requirement_id,
            module_id=module_id,
            title=title,
            precondition=precondition,
            steps=steps,
            expected_result=expected_result,
            status=status,
        )
    except ValidationError as exc:
        raise ToolError(f"用例字段不合法: {exc}") from exc
    async with AsyncSessionLocal() as db:
        try:
            case = await test_case_service.create_test_case(db, payload)
        except ValueError as exc:  # 需求/模块不存在或模块不属于该需求
            raise ToolError(str(exc)) from exc
    return _dump(case, TestCaseOut)


@mcp.tool()
async def update_test_case(
    case_id: int,
    title: str | None = None,
    module_id: int | None = None,
    requirement_id: int | None = None,
    precondition: str | None = None,
    steps: list[str] | None = None,
    expected_result: str | None = None,
    status: CaseStatus | None = None,
) -> dict:
    """部分更新测试用例：只更新显式传入的字段，未传字段保持原值；
    steps 传入即整体替换。module_id 传 0 表示移出模块（用例直属于需求）；
    移动到其他需求时应同时传该需求下的 module_id（或传 0），否则会因
    模块不属于新需求而报错。"""
    async with AsyncSessionLocal() as db:
        case = await test_case_service.get_test_case(db, case_id)
        if not case:
            raise ToolError(f"测试用例 {case_id} 不存在")
        # read-merge-write：TestCaseUpdate 是全量 schema，以当前值为基底合并
        merged: dict[str, Any] = {
            "requirement_id": case.requirement_id,
            "module_id": case.module_id,
            "title": case.title,
            "precondition": case.precondition,
            "steps": case.steps or [],
            "expected_result": case.expected_result,
            "status": case.status,
        }
        if title is not None:
            merged["title"] = title
        if precondition is not None:
            merged["precondition"] = precondition
        if steps is not None:
            merged["steps"] = steps
        if expected_result is not None:
            merged["expected_result"] = expected_result
        if status is not None:
            merged["status"] = status
        if requirement_id is not None:
            merged["requirement_id"] = requirement_id
        if module_id is not None:
            merged["module_id"] = None if module_id == 0 else module_id
        try:
            updated = await test_case_service.update_test_case(
                db, case, TestCaseUpdate(**merged)
            )
        except (ValueError, ValidationError) as exc:
            raise ToolError(str(exc)) from exc
    return _dump(updated, TestCaseOut)


@mcp.tool()
async def batch_update_test_case_status(ids: list[int], status: CaseStatus) -> dict:
    """批量更新测试用例状态（pending/in_progress/completed/blocked）。
    任一 id 不存在则整体拒绝，返回 {"updated": 数量}。"""
    async with AsyncSessionLocal() as db:
        try:
            updated = await test_case_service.batch_update_status(db, ids, status)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return {"updated": updated}


@mcp.tool()
async def delete_test_case(case_id: int) -> dict:
    """删除单个测试用例（不可恢复）。"""
    async with AsyncSessionLocal() as db:
        case = await test_case_service.get_test_case(db, case_id)
        if not case:
            raise ToolError(f"测试用例 {case_id} 不存在")
        await test_case_service.delete_test_case(db, case)
    return {"deleted": case_id}


@mcp.tool()
async def batch_delete_test_cases(ids: list[int]) -> dict:
    """批量删除测试用例（不可恢复）。任一 id 不存在则整体拒绝，
    返回 {"deleted": 数量}。"""
    async with AsyncSessionLocal() as db:
        try:
            deleted = await test_case_service.batch_delete(db, ids)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return {"deleted": deleted}


@mcp.tool()
async def import_test_cases(
    workspace_id: int,
    requirement_id: int | None = None,
    requirement_name: str = "",
    modules: list[ImportModuleIn] = [],
    cases: list[ImportCaseIn] = [],
) -> dict:
    """批量导入测试用例（适合把需求文档整理成用例后一次入库）：
    - 未传 requirement_id 时必须传 requirement_name，会自动创建需求；
    - modules 元素结构 {name, cases: [{title, precondition, steps,
      expected_result}]}，模块按名复用（已存在则不重建）；
    - cases 为不分组、直接挂在需求下的用例，元素结构同上；
    - steps 为有序步骤字符串数组，导入的用例状态默认 pending。
    返回 {requirement_id, requirement_name, module_count, case_count}。"""
    try:
        payload = TestCaseImportIn(
            workspace_id=workspace_id,
            requirement_id=requirement_id,
            requirement_name=requirement_name,
            modules=modules,
            cases=cases,
        )
    except ValidationError as exc:
        raise ToolError(f"导入结构不合法: {exc}") from exc
    async with AsyncSessionLocal() as db:
        try:
            result = await test_case_service.import_test_cases(db, payload)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return result


# ---------- 数据源查询 ----------


async def _get_datasource_or_error(db, datasource_id: int):
    ds = await datasource_service.get_datasource(db, datasource_id)
    if not ds:
        raise ToolError(f"数据源 {datasource_id} 不存在")
    return ds


@mcp.tool()
async def list_datasources() -> str:
    """列出平台已配置的数据源（不含密码）。返回 JSON 数组字符串，
    元素含 id、name、host、port、user、database（默认库）等。
    查询业务数据需要 datasource_id 时，先用本工具查询。"""
    async with AsyncSessionLocal() as db:
        items = await datasource_service.get_datasources(db)
    return json.dumps([_dump(d, DatasourceOut) for d in items], ensure_ascii=False)


@mcp.tool()
async def list_databases(datasource_id: int) -> str:
    """列出数据源连接账号可见的数据库（已过滤 information_schema 等系统库）。
    返回库名 JSON 数组字符串。"""
    async with AsyncSessionLocal() as db:
        ds = await _get_datasource_or_error(db, datasource_id)
    try:
        databases = await datasource_query_service.list_databases(ds)
    except Exception as exc:
        raise ToolError(f"获取数据库列表失败: {exc}") from exc
    return json.dumps(databases, ensure_ascii=False)


@mcp.tool()
async def list_tables(datasource_id: int, database: str | None = None) -> str:
    """列出指定库的表（含类型、近似行数、注释）。返回 JSON 数组字符串。
    database 缺省时使用数据源默认库。"""
    async with AsyncSessionLocal() as db:
        ds = await _get_datasource_or_error(db, datasource_id)
    try:
        tables = await datasource_query_service.list_tables(ds, database)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"获取表列表失败: {exc}") from exc
    return json.dumps([t.model_dump() for t in tables], ensure_ascii=False)


@mcp.tool()
async def get_table_schema(
    datasource_id: int, table_name: str, database: str | None = None
) -> str:
    """获取表结构：字段名、类型、可空、Key、默认值、注释等。返回 JSON 数组字符串。
    database 缺省时使用数据源默认库。"""
    async with AsyncSessionLocal() as db:
        ds = await _get_datasource_or_error(db, datasource_id)
    try:
        columns = await datasource_query_service.get_table_schema(
            ds, table_name, database
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"获取表结构失败: {exc}") from exc
    return json.dumps([c.model_dump() for c in columns], ensure_ascii=False)


@mcp.tool()
async def query_database(
    datasource_id: int, sql: str, database: str | None = None
) -> dict:
    """在数据源上执行只读 SQL 查询（仅限 SELECT/SHOW/DESC/DESCRIBE/EXPLAIN/
    WITH/VALUES/TABLE），返回 columns/rows/row_count/truncated/elapsed_ms 等。
    最多返回 1000 行，超出时 truncated 为 true；失败时 success=false 且 error 有原因。
    database 缺省时使用数据源默认库。"""
    async with AsyncSessionLocal() as db:
        ds = await _get_datasource_or_error(db, datasource_id)
    result = await datasource_query_service.execute_readonly_query(
        ds, sql, database=database
    )
    return result.model_dump(mode="json")

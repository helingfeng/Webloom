import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.script import Script
from app.models.execution import Execution
from app.config import settings
from app.engine.mock_generator import generate_mock_inputs


SCRIPT_TEMPLATE = '''import asyncio
import json
import os
from playwright.async_api import async_playwright, expect

INPUTS = json.loads(os.environ.get("ATP_INPUTS", "{}"))
GLOBAL_HEADERS = json.loads(os.environ.get("ATP_GLOBAL_HEADERS", "{}"))
GLOBAL_VARS = json.loads(os.environ.get("ATP_GLOBAL_VARS", "{}"))
GLOBAL_LOCAL_STORAGE = json.loads(os.environ.get("ATP_GLOBAL_LOCAL_STORAGE", "{}"))
GLOBAL_COOKIES = json.loads(os.environ.get("ATP_GLOBAL_COOKIES", "[]"))
DATA_VIEWS = json.loads(os.environ.get("ATP_DATA_VIEWS", "{}"))
# 单行便捷访问：DATA_VIEWS_ONE["slug"] 取首行对象；结果为空时为 None；失败视图保留 {"_error": ...}
DATA_VIEWS_ONE = {
    _slug: (rows[0] if isinstance(rows, list) and rows else rows)
    for _slug, rows in DATA_VIEWS.items()
}
START_URL = os.environ.get("ATP_START_URL", "")
OUTPUTS = {}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=__HEADLESS__)
        context = await browser.new_context(
            extra_http_headers=GLOBAL_HEADERS if GLOBAL_HEADERS else None
        )
        # 自动注入 cookies（如已配置 cookie 类型全局变量）
        if GLOBAL_COOKIES:
            print("[global] Injecting cookies: " + ", ".join(c["name"] for c in GLOBAL_COOKIES))
            await context.add_cookies(GLOBAL_COOKIES)
        page = await context.new_page()
        page.set_default_timeout(__TIMEOUT__)

        # 实时画面：CDP screencast 持续截帧写入临时文件，供前端轮询展示
        _frame_path = os.environ.get("ATP_FRAME_FILE", "")
        if _frame_path:
            try:
                import base64 as _b64
                _cdp = await context.new_cdp_session(page)
                await _cdp.send(
                    "Page.startScreencast",
                    {"format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 800},
                )
                def _on_frame(event):
                    try:
                        with open(_frame_path, "wb") as _f:
                            _f.write(_b64.b64decode(event["data"]))
                        # 必须 ack 才会推送下一帧
                        asyncio.get_running_loop().create_task(
                            _cdp.send(
                                "Page.screencastFrameAck",
                                {"sessionId": event["sessionId"]},
                            )
                        )
                    except Exception:
                        pass
                _cdp.on("Page.screencastFrame", _on_frame)
                print("[live] Screencast started: " + _frame_path)
            except Exception as _e:
                print("[live] Screencast unavailable: " + str(_e))

        # 自动注入 localStorage 登录态（如已配置 localStorage 类型全局变量）
        if GLOBAL_LOCAL_STORAGE and START_URL:
            print("[global] Injecting localStorage credentials into " + START_URL)
            await page.goto(START_URL, wait_until="domcontentloaded")
            await page.evaluate(
                """(items) => {
                    for (const [k, v] of Object.entries(items)) {
                        localStorage.setItem(k, v);
                    }
                }""",
                GLOBAL_LOCAL_STORAGE,
            )
            print("[global] localStorage injected, reloading...")
            await page.goto(START_URL, wait_until="domcontentloaded")

__USER_CODE__

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
    print("__ATP_OUTPUTS__" + json.dumps(OUTPUTS))
'''


class ScriptExecutionError(RuntimeError):
    """脚本执行失败，携带子进程完整日志（含 traceback / 断言原因）"""

    def __init__(self, message: str, logs: str = ""):
        super().__init__(message)
        self.logs = logs


def _extract_error_line(logs: str) -> str:
    """从子进程日志中提取最后的异常行（如 AssertionError: xxx）作为失败原因摘要"""
    lines = [line.strip() for line in logs.splitlines() if line.strip()]
    for line in reversed(lines):
        if "Error" in line or "Exception" in line:
            return line
    return ""


def _split_browser_inputs(
    input_defs: list[dict], inputs: dict
) -> tuple[dict[str, str], dict[str, str], list[dict]]:
    """按输入变量定义拆出 header / localStorage / cookie 三类浏览器注入项。

    变量名即注入名（Header 名 / localStorage 键 / cookie 名），运行值作为其值。
    """
    type_by_name = {
        d.get("name"): d.get("type") for d in (input_defs or []) if d.get("name")
    }
    headers: dict[str, str] = {}
    local_storage: dict[str, str] = {}
    cookies: list[dict] = []
    for name, value in (inputs or {}).items():
        var_type = type_by_name.get(name)
        if var_type == "header":
            headers[name] = str(value)
        elif var_type == "localStorage":
            local_storage[name] = str(value)
        elif var_type == "cookie":
            cookies.append({"name": name, "value": str(value)})
    return headers, local_storage, cookies


async def run_script(
    db: AsyncSession,
    script: Script,
    mode: str = "manual",
    user_inputs: dict | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> Execution:
    user_inputs = user_inputs or {}
    inputs = user_inputs if mode == "manual" else generate_mock_inputs(script.inputs)

    execution = Execution(
        target_type="script",
        target_id=script.id,
        mode=mode,
        inputs=inputs,
        status="running",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    try:
        logs, outputs = await execute_script_code(script, inputs, execution.id, log_callback)
        execution.status = "success"
        execution.logs = logs
        execution.outputs = outputs
    except Exception as exc:
        execution.status = "failed"
        detail_logs = getattr(exc, "logs", "") or ""
        error_msg = f"Error: {exc}"
        execution.logs = f"{detail_logs}\n{error_msg}".strip() if detail_logs else error_msg
        execution.outputs = {}
        if log_callback:
            log_callback(error_msg)
    finally:
        execution.finished_at = datetime.now()
        await db.commit()
        await db.refresh(execution)

    return execution


async def execute_script_code(
    script: Script,
    inputs: dict,
    execution_id: int,
    log_callback: Callable[[str], None] | None = None,
    global_headers: dict[str, str] | None = None,
    global_vars: dict[str, str] | None = None,
    global_local_storage: dict[str, str] | None = None,
    global_cookies: list[dict] | None = None,
    data_views: dict | None = None,
    headless: bool | None = None,
) -> tuple[str, dict]:
    # 未显式指定时回退到全局配置（默认无窗口）
    if headless is None:
        headless = settings.headless
    timeout = settings.playwright_timeout

    # 输入变量中的 header/localStorage/cookie 注入浏览器，同名时覆盖全局变量（输入优先）
    input_headers, input_local_storage, input_cookies = _split_browser_inputs(
        script.inputs, inputs
    )
    merged_headers = {**(global_headers or {}), **input_headers}
    merged_local_storage = {**(global_local_storage or {}), **input_local_storage}
    cookie_host = urlparse(script.start_url or "").netloc.split(":")[0]
    if input_cookies and cookie_host:
        # cookie 域取起始 URL host（去端口）；与全局 cookie 同名时输入优先
        input_names = {c["name"] for c in input_cookies}
        merged_cookies = [
            c for c in (global_cookies or []) if c.get("name") not in input_names
        ]
        merged_cookies.extend(
            {"name": c["name"], "value": c["value"], "domain": cookie_host, "path": "/"}
            for c in input_cookies
        )
    else:
        merged_cookies = list(global_cookies or [])

    indented_code = "\n".join(
        "        " + line for line in script.code.splitlines()
    )
    full_code = (
        SCRIPT_TEMPLATE
        .replace("__HEADLESS__", "True" if headless else "False")
        .replace("__TIMEOUT__", str(timeout))
        .replace("__USER_CODE__", indented_code)
    )

    run_file = settings.executions_dir / f"run_{execution_id}.py"
    run_file.write_text(full_code, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "ATP_INPUTS": json.dumps(inputs),
        "ATP_GLOBAL_HEADERS": json.dumps(merged_headers),
        "ATP_GLOBAL_VARS": json.dumps(global_vars or {}),
        "ATP_GLOBAL_LOCAL_STORAGE": json.dumps(merged_local_storage),
        "ATP_GLOBAL_COOKIES": json.dumps(merged_cookies),
        "ATP_DATA_VIEWS": json.dumps(data_views or {}),
        "ATP_START_URL": script.start_url or "",
        # 实时画面：模板内 CDP screencast 持续截帧写入该文件，供前端轮询展示
        "ATP_FRAME_FILE": str(settings.executions_dir / f"frame_{execution_id}.jpg"),
        "PYTHONUNBUFFERED": "1",
    }

    logs: list[str] = []

    async def read_stream(stream, prefix: str):
        while True:
            try:
                line = await stream.readline()
            except Exception:
                break
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            log_line = f"{prefix}{text}"
            logs.append(log_line)
            if log_callback:
                log_callback(log_line)

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(run_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, ""),
                    read_stream(process.stderr, ""),
                ),
                timeout=settings.script_execution_timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ScriptExecutionError(
                "Script execution timed out", "".join(logs)
            )

        return_code = await process.wait()
        full_logs = "".join(logs)

        if return_code != 0:
            reason = _extract_error_line(full_logs)
            message = f"Script exited with code {return_code}"
            if reason:
                message += f": {reason}"
            raise ScriptExecutionError(message, full_logs)

        outputs = _parse_outputs(full_logs)
        return full_logs, outputs
    finally:
        # 运行文件用后即删（成功/失败/超时统一清理），防止临时目录无限堆积
        run_file.unlink(missing_ok=True)


def cleanup_execution_temp_files(execution_id: int) -> None:
    """清理某次执行的全部临时产物（运行脚本 + 实时画面帧）；幂等可重复调用"""
    for path in settings.executions_dir.glob(f"run_{execution_id}_*.py"):
        path.unlink(missing_ok=True)
    frame = settings.executions_dir / f"frame_{execution_id}.jpg"
    frame.unlink(missing_ok=True)


def _parse_outputs(text: str) -> dict:
    marker = "__ATP_OUTPUTS__"
    for line in text.splitlines():
        idx = line.find(marker)
        if idx != -1:
            json_str = line[idx + len(marker) :]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"_raw_output": json_str}
    return {}


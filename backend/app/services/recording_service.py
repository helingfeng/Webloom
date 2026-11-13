import asyncio
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import AsyncSessionLocal
from app.services import global_variable_service
from app.services.browser_setting_service import get_browser_options
from app.engine.collection import create_collection_context


class RecordingSession:
    def __init__(self, recording_id: int, start_url: str, output_file: Path):
        self.id = recording_id
        self.start_url = start_url
        self.output_file = output_file
        self.status = "recording"
        self.error = ""
        self.raw_code = ""
        self.code = ""
        self.detected_start_url = ""
        self.applied_globals: dict = {}
        self.started_at = datetime.now()
        self.finished_at: datetime | None = None
        self._task: asyncio.Task | None = None


# 单用户本地平台，录制会话仅保存在内存中
_sessions: dict[int, RecordingSession] = {}
_next_id = 1


async def start_recording(start_url: str) -> RecordingSession:
    """启动录制：自建有头浏览器 context（携带按域名匹配的全局变量配置），
    通过 Playwright 内部协议启动 Inspector 录制器。

    用户在浏览器中操作，关闭浏览器窗口即结束录制，
    生成的 python-async 代码写入 output_file。
    """
    global _next_id
    recording_id = _next_id
    _next_id += 1

    output_file = settings.executions_dir / f"recording_{recording_id}.py"

    session = RecordingSession(recording_id, start_url, output_file)
    _sessions[recording_id] = session

    # 按录制起始 URL 的域名加载全局变量（不传则仅加载未绑定域名的全局变量）
    async with AsyncSessionLocal() as db:
        headers, gvars, local_storage, cookies = (
            await global_variable_service.get_active_globals_grouped(db, start_url)
        )

    session.applied_globals = {
        "headers": headers,
        "vars": gvars,
        "localStorage": local_storage,
        "cookies": cookies,
    }

    session._task = asyncio.create_task(
        _run_recorder(session, headers, local_storage, cookies)
    )
    return session


async def _run_recorder(
    session: RecordingSession,
    headers: dict[str, str],
    local_storage: dict[str, str],
    cookies: list[dict],
) -> None:
    from app.engine.browser import managed_browser

    session.output_file.write_text("", encoding="utf-8")

    browser = None
    try:
        async with managed_browser(
            await get_browser_options(), headless=False
        ) as browser:
            # 录制环境与脚本执行环境一致：注入公共 Header 全局变量
            context, collection = await create_collection_context(
                browser, settings.collection_policy(), headers=headers,
                cookies=cookies, local_storage=local_storage,
                start_url=session.start_url, timeout=settings.playwright_timeout,
            )
            # 启动 Inspector 录制器（内部协议，与 codegen CLI 同源）
            await context._impl_obj._channel.send(
                "enableRecorder",
                None,
                {
                    "language": "python-async",
                    "mode": "recording",
                    "codegenMode": "actions",
                    "handleSIGINT": False,
                    "outputFile": str(session.output_file),
                    "contextOptions": {},
                },
            )
            page = await context.new_page()

            if session.start_url:
                await page.goto(session.start_url, wait_until="domcontentloaded")

            # 录制中的页面全部关闭（用户关掉了浏览器窗口）即结束
            while context.pages:
                await asyncio.sleep(0.5)
        browser = None
        await _finalize(session)
    except asyncio.CancelledError:
        session.status = "failed"
        session.error = "录制已中止"
        session.finished_at = datetime.now()
        raise
    except Exception as exc:
        session.status = "failed"
        session.error = f"录制失败: {exc}"
        session.finished_at = datetime.now()


async def get_recording(recording_id: int) -> RecordingSession | None:
    session = _sessions.get(recording_id)
    if session and session.status == "recording" and session._task.done():
        await _finalize(session)
    return session


async def stop_recording(session: RecordingSession) -> RecordingSession:
    """中止录制：取消录制任务（不产生代码）"""
    if session.status == "recording" and session._task and not session._task.done():
        session._task.cancel()
        try:
            await session._task
        except (asyncio.CancelledError, Exception):
            pass
    if session.status == "recording":
        session.status = "failed"
        session.error = "录制已中止"
        session.finished_at = datetime.now()
    return session


async def _finalize(session: RecordingSession) -> None:
    session.finished_at = datetime.now()

    raw_code = ""
    if session.output_file.exists():
        raw_code = session.output_file.read_text(encoding="utf-8").strip()

    if raw_code:
        session.raw_code = raw_code
        session.code, session.detected_start_url = _extract_fragment(raw_code)
        session.status = "completed"
    else:
        session.status = "failed"
        session.error = "The recording produced no valid code (the browser may have been closed forcibly)"


def _extract_fragment(code: str) -> tuple[str, str]:
    """从录制器生成的完整脚本中提取平台代码片段：

    取 run() 函数体内 page 创建之后、浏览器关闭之前的部分，
    返回 (片段, 录制中第一个 goto 的 URL)
    """
    lines = code.splitlines()
    start_idx = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if start_idx is None:
            if "page = await context.new_page()" in stripped:
                start_idx = i + 1
        elif stripped.startswith("# -----") or stripped.startswith(
            "await context.close()"
        ):
            end_idx = i
            break

    if start_idx is None:
        return "", ""

    body = lines[start_idx:end_idx]
    dedented = [line[4:] if line.startswith("    ") else line for line in body]

    detected_start_url = ""
    for line in dedented:
        stripped = line.strip()
        if stripped.startswith("await page.goto("):
            detected_start_url = (
                stripped[len("await page.goto(") : -1].strip().strip('"').strip("'")
            )
            break

    return "\n".join(dedented).strip(), detected_start_url

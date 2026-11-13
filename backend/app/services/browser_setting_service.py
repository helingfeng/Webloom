"""数据库开关优先于环境默认值；跨 API、MCP、worker 即时读取，不缓存。"""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.engine.browser import BrowserOptions
from app.models.browser_setting import BrowserSetting
from app.schemas.browser_setting import BrowserSettingOut


async def _get_options(db: AsyncSession) -> BrowserOptions:
    enabled = await db.scalar(
        select(BrowserSetting.cloakbrowser_enabled).where(BrowserSetting.id == 1)
    )
    options = settings.browser_options()
    if enabled is None:
        return options
    return replace(options, engine="cloakbrowser" if enabled else "playwright")


async def get_browser_options() -> BrowserOptions:
    async with AsyncSessionLocal() as db:
        return await _get_options(db)


def _status(options: BrowserOptions) -> BrowserSettingOut:
    return BrowserSettingOut(
        **options.public_status(),
        cloakbrowser_enabled=options.engine == "cloakbrowser",
    )


async def get_browser_setting(db: AsyncSession) -> BrowserSettingOut:
    return _status(await _get_options(db))


async def update_browser_setting(db: AsyncSession, enabled: bool) -> BrowserSettingOut:
    options = replace(
        settings.browser_options(), engine="cloakbrowser" if enabled else "playwright"
    )
    status = _status(options)
    if enabled and not status.ready:
        raise ValueError("无法启用 CloakBrowser：请先安装依赖并配置许可证")

    # 固定主键 upsert，首次并发保存也不会重复创建设置。
    if db.get_bind().dialect.name == "mysql":
        from sqlalchemy.dialects.mysql import insert

        statement = insert(BrowserSetting).values(id=1, cloakbrowser_enabled=enabled)
        statement = statement.on_duplicate_key_update(cloakbrowser_enabled=enabled)
    else:
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(BrowserSetting).values(id=1, cloakbrowser_enabled=enabled)
        statement = statement.on_conflict_do_update(
            index_elements=["id"], set_={"cloakbrowser_enabled": enabled}
        )
    await db.execute(statement)
    await db.commit()
    return status

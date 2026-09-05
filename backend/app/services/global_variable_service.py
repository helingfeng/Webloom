from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.global_variable import GlobalVariable
from app.schemas.global_variable import GlobalVariableCreate, GlobalVariableUpdate


def extract_domain(start_url: str) -> str:
    """从起始 URL 中提取 host（含端口），用于域名匹配"""
    if not start_url:
        return ""
    return urlparse(start_url).netloc or ""


def _domain_matches(var_domain: str, host: str) -> bool:
    """变量绑定域名与脚本 host 是否匹配：

    - var_domain 为空：全局生效
    - 精确相等，或 host 是 var_domain 的子域名（admin.example.com 匹配 example.com）
    """
    var_domain = var_domain.strip().lower()
    if not var_domain:
        return True
    host = host.strip().lower()
    return host == var_domain or host.endswith("." + var_domain)


async def get_global_variables(db: AsyncSession) -> list[GlobalVariable]:
    result = await db.execute(select(GlobalVariable).order_by(GlobalVariable.id))
    return result.scalars().all()


async def get_global_variable(db: AsyncSession, var_id: int) -> GlobalVariable | None:
    result = await db.execute(select(GlobalVariable).where(GlobalVariable.id == var_id))
    return result.scalar_one_or_none()


async def create_global_variable(
    db: AsyncSession, var_in: GlobalVariableCreate
) -> GlobalVariable:
    var = GlobalVariable(**var_in.model_dump())
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


async def update_global_variable(
    db: AsyncSession, var: GlobalVariable, var_in: GlobalVariableUpdate
) -> GlobalVariable:
    for key, value in var_in.model_dump().items():
        setattr(var, key, value)
    await db.commit()
    await db.refresh(var)
    return var


async def delete_global_variable(db: AsyncSession, var: GlobalVariable) -> None:
    await db.delete(var)
    await db.commit()


async def get_active_headers(db: AsyncSession, start_url: str = "") -> dict[str, str]:
    host = extract_domain(start_url)
    result = await db.execute(
        select(GlobalVariable).where(
            GlobalVariable.type == "header", GlobalVariable.enabled.is_(True)
        )
    )
    return {
        v.name: v.value
        for v in result.scalars().all()
        if _domain_matches(v.domain, host)
    }


async def get_active_vars(db: AsyncSession, start_url: str = "") -> dict[str, str]:
    host = extract_domain(start_url)
    result = await db.execute(
        select(GlobalVariable).where(
            GlobalVariable.type == "variable", GlobalVariable.enabled.is_(True)
        )
    )
    return {
        v.name: v.value
        for v in result.scalars().all()
        if _domain_matches(v.domain, host)
    }


async def get_active_local_storage(db: AsyncSession, start_url: str = "") -> dict[str, str]:
    host = extract_domain(start_url)
    result = await db.execute(
        select(GlobalVariable).where(
            GlobalVariable.type == "localStorage", GlobalVariable.enabled.is_(True)
        )
    )
    return {
        v.name: v.value
        for v in result.scalars().all()
        if _domain_matches(v.domain, host)
    }


async def get_active_cookies(db: AsyncSession, start_url: str = "") -> list[dict]:
    """返回 Playwright add_cookies 格式的 cookie 列表。

    变量的 name 为 cookie 名、value 为 cookie 值；
    domain 取变量绑定的域名（未绑定时用起始 URL 的 host），保证 cookie 落到正确站点。
    """
    host = extract_domain(start_url)
    result = await db.execute(
        select(GlobalVariable).where(
            GlobalVariable.type == "cookie", GlobalVariable.enabled.is_(True)
        )
    )
    cookies = []
    for v in result.scalars().all():
        if not _domain_matches(v.domain, host):
            continue
        # cookie 所属域名：优先变量绑定域名，否则用起始 URL host（去端口）
        cookie_domain = (v.domain or host).split(":")[0]
        cookies.append(
            {
                "name": v.name,
                "value": v.value,
                "domain": cookie_domain,
                "path": "/",
            }
        )
    return cookies

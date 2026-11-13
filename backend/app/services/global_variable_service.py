import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.engine.domains import normalize_domain
from app.models.global_variable import GlobalVariable
from app.schemas.global_variable import GlobalVariableCreate, GlobalVariableUpdate


def extract_domain(start_url: str) -> str:
    return (urlparse(start_url).hostname or "").lower().rstrip(".") if start_url else ""


def _domain_matches(var_domain: str, host: str) -> bool:
    try:
        domain = normalize_domain(var_domain)
        target = normalize_domain(host)
    except ValueError:
        return False
    return not domain or target == domain or target.endswith("." + domain)


async def get_global_variables(db: AsyncSession) -> list[GlobalVariable]:
    return list(
        (
            await db.execute(select(GlobalVariable).order_by(GlobalVariable.id.desc()))
        ).scalars()
    )


async def get_global_variable(db: AsyncSession, var_id: int) -> GlobalVariable | None:
    return await db.get(GlobalVariable, var_id)


async def list_matching_global_variables(
    db: AsyncSession,
    domain: str | None = None,
    kind: str | None = None,
    enabled: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[GlobalVariable], int]:
    """按目标域筛选（包含通用/父域），兼容历史 URL/大小写域名写法。"""
    target = normalize_domain(domain) if domain is not None else None
    rows = await get_global_variables(db)
    matched = [
        row for row in rows
        if (target is None or _domain_matches(row.domain or "", target))
        and (kind is None or row.type == kind)
        and (enabled is None or row.enabled == enabled)
    ]
    start = max(skip, 0)
    return matched[start:start + min(max(limit, 1), 100)], len(matched)


async def _validate(
    db: AsyncSession, data: dict, exclude_id: int | None = None
) -> dict:
    data["name"] = data["name"].strip()
    data["domain"] = normalize_domain(data.get("domain", ""))
    name, kind = data["name"], data["type"]
    if not name or len(name) > 255 or "\r" in name or "\n" in name:
        raise ValueError("变量名不能为空，最长 255 字符且不能包含换行")
    if kind in ("header", "cookie") and not re.fullmatch(
        r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name
    ):
        raise ValueError("Header / Cookie 名称含无效字符")
    if kind == "header" and any(c in data["value"] for c in ("\r", "\n")):
        raise ValueError("Header 值不能包含换行")
    # 兼容旧数据中的大小写、URL 和端口写法；同作用域下不再隐式覆盖。
    for item in await get_global_variables(db):
        if item.id == exclude_id or item.type != kind:
            continue
        try:
            domain = normalize_domain(item.domain or "")
        except ValueError:
            continue
        same_name = (
            item.name.lower() == name.lower() if kind == "header" else item.name == name
        )
        if domain == data["domain"] and same_name:
            raise ValueError("相同类型、名称和域名的变量已存在，请编辑已有变量")
    return data


async def create_global_variable(
    db: AsyncSession, var_in: GlobalVariableCreate
) -> GlobalVariable:
    var = GlobalVariable(**await _validate(db, var_in.model_dump()))
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


async def update_global_variable(
    db: AsyncSession, var: GlobalVariable, var_in: GlobalVariableUpdate
) -> GlobalVariable:
    merged = {
        key: getattr(var, key)
        for key in ("name", "value", "type", "domain", "enabled", "description")
    }
    changes = var_in.model_dump(exclude_unset=True, exclude_none=True)
    if set(changes) <= {"enabled", "description"}:
        for key, value in changes.items():
            setattr(var, key, value)
        await db.commit()
        await db.refresh(var)
        return var
    merged.update(changes)
    for key, value in (await _validate(db, merged, var.id)).items():
        setattr(var, key, value)
    await db.commit()
    await db.refresh(var)
    return var


async def delete_global_variable(db: AsyncSession, var: GlobalVariable) -> None:
    await db.delete(var)
    await db.commit()


async def get_active_globals_grouped(
    db: AsyncSession, start_url: str = ""
) -> tuple[dict[str, str], dict[str, str], dict[str, str], list[dict]]:
    """确定性合并：通用 < 父域 < 具体域；同范围旧重复项按 ID 后者覆盖。"""
    host = extract_domain(start_url)
    rows = (
        (
            await db.execute(
                select(GlobalVariable).where(GlobalVariable.enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )
    matched = []
    for row in rows:
        if _domain_matches(row.domain or "", host):
            domain = normalize_domain(row.domain or "")
            matched.append((len(domain), row.id, domain, row))
    chosen = {}
    for _, _, domain, row in sorted(matched, key=lambda item: (item[0], item[1])):
        key = (row.type, row.name.lower() if row.type == "header" else row.name)
        chosen[key] = (domain, row)
    headers, variables, storage, cookies = {}, {}, {}, []
    for domain, row in chosen.values():
        if row.type == "header":
            headers[row.name] = row.value
        elif row.type == "variable":
            variables[row.name] = row.value
        elif row.type == "localStorage":
            storage[row.name] = row.value
        elif row.type == "cookie" and host:
            cookies.append(
                {
                    "name": row.name,
                    "value": row.value,
                    "domain": domain or host,
                    "path": "/",
                }
            )
    return headers, variables, storage, cookies


async def get_active_headers(db: AsyncSession, start_url: str = "") -> dict[str, str]:
    return (await get_active_globals_grouped(db, start_url))[0]


async def get_active_vars(db: AsyncSession, start_url: str = "") -> dict[str, str]:
    return (await get_active_globals_grouped(db, start_url))[1]


async def get_active_local_storage(
    db: AsyncSession, start_url: str = ""
) -> dict[str, str]:
    return (await get_active_globals_grouped(db, start_url))[2]


async def get_active_cookies(db: AsyncSession, start_url: str = "") -> list[dict]:
    return (await get_active_globals_grouped(db, start_url))[3]

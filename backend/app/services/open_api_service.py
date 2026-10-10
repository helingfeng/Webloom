"""开放平台接口服务：代理路由 CRUD + 调用日志 + 内置采集接口 + 代理转发。

外部端点（/open 前缀）分两类：
- 内置采集接口：/open/api/v1/collect/{trigger,result,tasks}，固定开放、按应用鉴权
- 代理接口：管理端在 open_apis 表配置「外部路径 → 平台内部 /api 路径」的映射，
  服务端转发（调用方只见开放域名 + 应用凭证，不接触平台内部端口）
"""

import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.open_platform import OpenApiLog, OpenApiRoute
from app.schemas.open_platform import OpenApiRouteCreate, OpenApiRouteUpdate

# 代理允许的内部路径前缀（防止把开放代理指向非平台接口）
_ALLOWED_TARGET_PREFIX = "/api/"
_PROXY_TIMEOUT = 30  # 秒


# ---------- 代理路由 CRUD ----------


async def get_routes(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[OpenApiRoute]:
    result = await db.execute(
        select(OpenApiRoute).order_by(OpenApiRoute.id.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


async def count_routes(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(OpenApiRoute.id)))
    return result.scalar_one()


async def get_route(db: AsyncSession, route_id: int) -> OpenApiRoute | None:
    return await db.get(OpenApiRoute, route_id)


def _validate_route_pair(method: str, path: str, target_path: str) -> None:
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        raise ValueError(f"不支持的 HTTP 方法：{method}")
    if not path.startswith("/"):
        raise ValueError("外部路径必须以 / 开头（相对 /open 前缀）")
    if path.startswith("/open"):
        raise ValueError("外部路径无需携带 /open 前缀")
    if not target_path.startswith(_ALLOWED_TARGET_PREFIX):
        raise ValueError("内部目标路径必须以 /api/ 开头")


async def create_route(db: AsyncSession, route_in: OpenApiRouteCreate) -> OpenApiRoute:
    _validate_route_pair(route_in.method, route_in.path, route_in.target_path)
    exists = await db.execute(
        select(OpenApiRoute).where(
            OpenApiRoute.method == route_in.method, OpenApiRoute.path == route_in.path
        )
    )
    if exists.scalar_one_or_none() is not None:
        raise ValueError(f"{route_in.method} {route_in.path} 已存在")
    route = OpenApiRoute(**route_in.model_dump())
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return route


async def update_route(
    db: AsyncSession, route: OpenApiRoute, route_in: OpenApiRouteUpdate
) -> OpenApiRoute:
    data = route_in.model_dump(exclude_unset=True)
    merged = {
        "method": data.get("method", route.method),
        "path": data.get("path", route.path),
        "target_path": data.get("target_path", route.target_path),
    }
    _validate_route_pair(**merged)
    if ("method" in data or "path" in data) and (
        merged["method"] != route.method or merged["path"] != route.path
    ):
        exists = await db.execute(
            select(OpenApiRoute).where(
                OpenApiRoute.method == merged["method"],
                OpenApiRoute.path == merged["path"],
                OpenApiRoute.id != route.id,
            )
        )
        if exists.scalar_one_or_none() is not None:
            raise ValueError(f"{merged['method']} {merged['path']} 已存在")
    for key, value in data.items():
        setattr(route, key, value)
    await db.commit()
    await db.refresh(route)
    return route


async def delete_route(db: AsyncSession, route: OpenApiRoute) -> None:
    await db.delete(route)
    await db.commit()


# ---------- 调用日志（静默落库，镜像 query_history 约定）----------


async def record_open_log(
    db: AsyncSession,
    *,
    app_id: int | None,
    app_key: str,
    path: str,
    method: str,
    status_code: int,
    success: bool,
    execution_id: int | None = None,
    request_ip: str = "",
    detail: str = "",
) -> None:
    log = OpenApiLog(
        app_id=app_id,
        app_key=app_key,
        path=path,
        method=method,
        status_code=status_code,
        success=success,
        execution_id=execution_id,
        request_ip=request_ip,
        detail=detail,
    )
    db.add(log)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


async def get_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    app_id: int | None = None,
    success: bool | None = None,
) -> list[OpenApiLog]:
    stmt = select(OpenApiLog)
    if app_id is not None:
        stmt = stmt.where(OpenApiLog.app_id == app_id)
    if success is not None:
        stmt = stmt.where(OpenApiLog.success == success)
    result = await db.execute(stmt.order_by(OpenApiLog.id.desc()).offset(skip).limit(limit))
    return result.scalars().all()


async def count_logs(
    db: AsyncSession, app_id: int | None = None, success: bool | None = None
) -> int:
    stmt = select(func.count(OpenApiLog.id))
    if app_id is not None:
        stmt = stmt.where(OpenApiLog.app_id == app_id)
    if success is not None:
        stmt = stmt.where(OpenApiLog.success == success)
    result = await db.execute(stmt)
    return result.scalar_one()


async def clear_logs(db: AsyncSession) -> int:
    result = await db.execute(delete(OpenApiLog))
    await db.commit()
    return result.rowcount or 0


# ---------- 采集触发归属查询 ----------


async def owned_execution_ids(
    db: AsyncSession, app_id: int, limit: int = 50, script_path_only: bool = True
) -> list[int]:
    """该应用通过采集触发接口发起过的 execution_id（新→旧）"""
    stmt = select(OpenApiLog.execution_id).where(
        OpenApiLog.app_id == app_id,
        OpenApiLog.execution_id.is_not(None),
        OpenApiLog.success == True,  # noqa: E712
    )
    if script_path_only:
        stmt = stmt.where(OpenApiLog.path == "/open/api/v1/collect/trigger")
    result = await db.execute(stmt.order_by(OpenApiLog.id.desc()).limit(limit))
    return [eid for (eid,) in result.all()]


# ---------- 代理转发 ----------

_proxy_client: httpx.AsyncClient | None = None


def get_proxy_client() -> httpx.AsyncClient:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = httpx.AsyncClient(
            base_url=settings.open_api_internal_base_url, timeout=_PROXY_TIMEOUT
        )
    return _proxy_client


async def close_proxy_client() -> None:
    global _proxy_client
    if _proxy_client is not None:
        await _proxy_client.aclose()
        _proxy_client = None


def _path_to_regex(pattern: str) -> re.Pattern:
    """把 /v1/executions/{execution_id} 编译为 ^/v1/executions/(?P<execution_id>[^/]+)$"""
    parts = re.split(r"(\{[a-zA-Z_][a-zA-Z0-9_]*\})", pattern)
    chunks: list[str] = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            chunks.append(f"(?P<{part[1:-1]}>[^/]+)")
        else:
            chunks.append(re.escape(part))
    return re.compile("^" + "".join(chunks) + "$")


def match_route_path(route: OpenApiRoute, actual_path: str) -> dict[str, str] | None:
    match = _path_to_regex(route.path).match(actual_path)
    return match.groupdict() if match else None


def build_target_path(route: OpenApiRoute, params: dict[str, str]) -> str:
    target = route.target_path
    for key, value in params.items():
        target = target.replace("{" + key + "}", quote(value, safe=""))
    return target


async def forward_request(
    method: str,
    target_path: str,
    *,
    params: Any = None,
    content: bytes | None = None,
    content_type: str = "application/json",
) -> httpx.Response:
    """服务端转发到平台内部接口（透传原始请求体；转发不带调用方签名头）"""
    client = get_proxy_client()
    headers = {"Content-Type": content_type} if content else None
    return await client.request(
        method, target_path, params=params, content=content, headers=headers
    )

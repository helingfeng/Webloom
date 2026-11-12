"""开放平台应用服务：App 凭证 CRUD + 请求签名认证。

签名算法（开放调用方需按此实现）：
    canonical = "{METHOD}\\n{path}\\n{timestamp}\\n{sha256_hex(body)}"
    X-Sign    = HMAC-SHA256(app_secret, canonical).hexdigest()  # 小写 hex
其中 path 为完整请求路径（含 /open 前缀，不含 query），timestamp 为 Unix 秒，
时间窗由 settings.open_api_sign_ttl_seconds 控制（默认 ±300s）。
"""

import hashlib
import hmac
import secrets
import time

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.open_platform import OpenApp
from app.schemas.open_platform import OpenAppCreate, OpenAppUpdate

_KEY_PREFIX = "fk"


async def get_open_apps(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[OpenApp]:
    result = await db.execute(
        select(OpenApp).order_by(OpenApp.id.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


async def count_open_apps(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(OpenApp.id)))
    return result.scalar_one()


async def get_open_app(db: AsyncSession, app_id: int) -> OpenApp | None:
    return await db.get(OpenApp, app_id)


async def get_open_app_by_key(db: AsyncSession, app_key: str) -> OpenApp | None:
    result = await db.execute(select(OpenApp).where(OpenApp.app_key == app_key))
    return result.scalar_one_or_none()


def _generate_credentials() -> tuple[str, str]:
    app_key = f"{_KEY_PREFIX}{secrets.token_hex(8)}"
    app_secret = secrets.token_hex(24)
    return app_key, app_secret


async def create_open_app(db: AsyncSession, app_in: OpenAppCreate) -> OpenApp:
    name = str(app_in.name or "").strip()
    if not name:
        raise ValueError("应用名称不能为空")
    app_key, app_secret = _generate_credentials()
    app = OpenApp(
        name=name,
        description=app_in.description,
        enabled=app_in.enabled,
        app_key=app_key,
        app_secret=app_secret,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def update_open_app(
    db: AsyncSession, app: OpenApp, app_in: OpenAppUpdate
) -> OpenApp:
    data = app_in.model_dump(exclude_unset=True)
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            raise ValueError("应用名称不能为空")
        data["name"] = name
    for key, value in data.items():
        setattr(app, key, value)
    await db.commit()
    await db.refresh(app)
    return app


async def regenerate_secret(db: AsyncSession, app: OpenApp) -> OpenApp:
    """重新生成 App Secret（旧密钥立即失效）"""
    _, app.app_secret = _generate_credentials()
    await db.commit()
    await db.refresh(app)
    return app


async def delete_open_app(db: AsyncSession, app: OpenApp) -> None:
    await db.delete(app)
    await db.commit()


async def authenticate_request(
    db: AsyncSession, request: Request
) -> tuple[OpenApp | None, str]:
    """校验开放接口签名请求。返回 (app, "") 表示通过；(None, 错误原因) 表示拒绝。

    会消费 request body（供后续 handler 复用 request.state.body）。
    """
    body = await request.body()
    request.state.body = body

    authorization = request.headers.get("Authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        key, separator, secret = token.partition(".")
        if scheme.lower() != "bearer" or not separator:
            return None, "Authorization 格式应为 Bearer <App Key>.<App Secret>"
        app = await get_open_app_by_key(db, key)
        if app is None or not hmac.compare_digest(
            app.app_secret.encode(), secret.encode()
        ):
            return None, "应用凭证无效"
        if not app.enabled:
            return None, "应用已停用"
        return app, ""

    app_key = request.headers.get("X-App-Key", "")
    timestamp = request.headers.get("X-Timestamp", "")
    sign = request.headers.get("X-Sign", "")
    if not app_key or not timestamp or not sign:
        return None, "缺少认证头（X-App-Key / X-Timestamp / X-Sign）"
    if not timestamp.isdigit():
        return None, "X-Timestamp 必须为 Unix 秒级时间戳"

    ts = int(timestamp)
    now = int(time.time())
    if abs(now - ts) > settings.open_api_sign_ttl_seconds:
        return None, "签名已过期（时间戳偏差超限）"

    app = await get_open_app_by_key(db, app_key)
    if app is None:
        return None, "应用不存在"
    if not app.enabled:
        return None, "应用已停用"

    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{request.method}\n{request.url.path}\n{timestamp}\n{body_hash}"
    expected = hmac.new(
        app.app_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sign.strip().lower()):
        if request.url.query:
            return (
                None,
                "签名校验失败（query 不参与签名，请只对 path 签名，query 直接拼在 URL 上）",
            )
        return None, "签名校验失败"

    return app, ""

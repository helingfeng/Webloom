from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.datasource import Datasource
from app.schemas.datasource import DatasourceCreate, DatasourceUpdate
from app.services import query_history_service
from app.services.datasource_query_service import connection_manager


async def get_datasources(db: AsyncSession) -> list[Datasource]:
    result = await db.execute(select(Datasource).order_by(Datasource.id))
    return result.scalars().all()


async def get_datasource(db: AsyncSession, ds_id: int) -> Datasource | None:
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    return result.scalar_one_or_none()


async def create_datasource(db: AsyncSession, ds_in: DatasourceCreate) -> Datasource:
    ds = Datasource(**ds_in.model_dump())
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def update_datasource(
    db: AsyncSession, ds: Datasource, ds_in: DatasourceUpdate
) -> Datasource:
    data = ds_in.model_dump(exclude_unset=True)
    # 密码留空 = 不修改
    if not data.get("password"):
        data.pop("password", None)
    for key, value in data.items():
        setattr(ds, key, value)
    await db.commit()
    await db.refresh(ds)
    # 配置已变，旧 engine 必须作废
    await connection_manager.invalidate(ds.id)
    return ds


async def delete_datasource(db: AsyncSession, ds: Datasource) -> None:
    # 先清执行历史，再删数据源（无外键，需手动级联）
    await query_history_service.delete_histories_by_datasource(db, ds.id)
    await db.delete(ds)
    await db.commit()
    await connection_manager.invalidate(ds.id)

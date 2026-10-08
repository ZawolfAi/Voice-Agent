import asyncio
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .config import get_settings
from .models import Base

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_kwargs = {"pool_pre_ping": True, "future": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = connect_args
    engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **engine_kwargs)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
_schema_ready = False
_schema_lock = asyncio.Lock()


async def init_db() -> None:
    global _schema_ready
    async with _schema_lock:
        if _schema_ready:
            return
        await _initialize_schema()
        _schema_ready = True


async def _initialize_schema() -> None:
    if settings.database_url.startswith("sqlite") and settings.app_env.lower() == "test":
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        return
    if settings.database_url.startswith("sqlite") and settings.app_env.lower() == "development":
        await engine.dispose()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncIterator[AsyncSession]:
    if not _schema_ready:
        await init_db()
    async with session_factory() as session:
        yield session

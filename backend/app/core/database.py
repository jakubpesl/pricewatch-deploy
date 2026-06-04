from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_connect_args = {"ssl": "require"} if "supabase.com" in _db_url else {}
engine = create_async_engine(
    _db_url,
    echo=settings.ENVIRONMENT == "development",
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

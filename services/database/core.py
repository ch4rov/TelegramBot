from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import config
from services.database.models import Base

engine = create_async_engine(url=config.DB_URL, echo=False)
session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from config.settings import DB_URL, DB_ECHO

ASYNC_DB_URL = DB_URL.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
engine = create_async_engine(ASYNC_DB_URL, pool_pre_ping=True, echo=DB_ECHO)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with SessionLocal() as db:
        yield db

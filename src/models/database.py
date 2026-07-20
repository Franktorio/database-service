# ~/src/models/database.py

from src.models.base import Base
import src.models.tables #ignore

from config.loader import DATABASE_URL

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.services.logging import log_message

PRINT_PREFIX = "DATABASE"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    poolclass=NullPool,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    log_message(f"[INFO] [{PRINT_PREFIX}] Initializing database schema.")
    log_message(f"[DEBUG] [{PRINT_PREFIX}] SQLAlchemy engine echo is enabled for development visibility.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log_message(f"[INFO] [{PRINT_PREFIX}] Database schema initialization complete.")

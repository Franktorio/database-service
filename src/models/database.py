# ~/src/models/database.py

from src.models.base import Base
import src.models.tables #ignore

from config.loader import (
    DATABASE_URL,
    OPERATING_MODE,
    POSTGRESQL_POOL_SIZE,
    POSTGRESQL_POOL_MAX_OVERFLOW,
    POSTGRESQL_POOL_TIMEOUT_SECONDS,
    POSTGRESQL_POOL_RECYCLE_SECONDS,
    POSTGRESQL_POOL_PRE_PING
)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.services.system.logging import log_message

PRINT_PREFIX = "DATABASE"

engine = create_async_engine(
    DATABASE_URL,
    echo=(OPERATING_MODE == "development"),
    
    pool_size=POSTGRESQL_POOL_SIZE,
    max_overflow=POSTGRESQL_POOL_MAX_OVERFLOW,
    pool_timeout=POSTGRESQL_POOL_TIMEOUT_SECONDS,
    pool_recycle=POSTGRESQL_POOL_RECYCLE_SECONDS,
    pool_pre_ping=POSTGRESQL_POOL_PRE_PING,
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
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                await conn.run_sync(lambda sync_conn, idx=index: idx.create(bind=sync_conn, checkfirst=True))
    log_message(f"[INFO] [{PRINT_PREFIX}] Database schema initialization complete.")

async def close_db():
    log_message(f"[INFO] [{PRINT_PREFIX}] Closing database engine.")
    await engine.dispose()
    log_message(f"[INFO] [{PRINT_PREFIX}] Database engine closed.")
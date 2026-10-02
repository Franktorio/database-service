# ~/src/models/database.py

from functools import wraps

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
from sqlalchemy import text
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

def with_session(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        session = kwargs.get("session")
        close_session = False
        if session is None:
            session = SessionLocal()
            kwargs["session"] = session
            close_session = True

        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            if close_session:
                await session.close()

    return wrapper


async def session_depends():
    """FastAPI dependency yielding a single AsyncSession, reused across all CRUD calls in a request."""
    async with SessionLocal() as session:
        yield session


async def init_db():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    log_message(f"[INFO] [{PRINT_PREFIX}] Database connectivity verified.")

async def close_db():
    await engine.dispose()

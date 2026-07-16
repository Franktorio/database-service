# ~/src/models/database.py

from src.models.base import Base
import src.models.tables #ignore

from config.loader import DATABASE_URL

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

PRINT_PREFIX = "DATABASE"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    print(f"[INFO] [{PRINT_PREFIX}] Initializing database schema.")
    print(f"[DEBUG] [{PRINT_PREFIX}] SQLAlchemy engine echo is enabled for development visibility.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"[INFO] [{PRINT_PREFIX}] Database schema initialization complete.")
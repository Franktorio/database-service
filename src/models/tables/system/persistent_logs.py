# ~src/models/tables/system/persistent_logs.py

from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import func, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.services.logging import log_message

PRINT_PREFIX = "PERSISTENT LOGS TABLE"

LOG_LEVEL = Literal["INFO", "WARNING", "ERROR", "DEBUG"]
LOG_TYPES = Literal["REQUEST", "API AUTH", "USER AUTH", "API RATE LIMIT", "USER RATE LIMIT", "IP BLOCK"]

class PersistentLog(Base):
    __tablename__ = "persistent_logs"
    __table_args__ = (
        Index("ix_persistent_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    log_type: Mapped[LOG_TYPES] = mapped_column(nullable=False)
    log_level: Mapped[LOG_LEVEL] = mapped_column(nullable=False)
    message: Mapped[str] = mapped_column(nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )


log_message(f"[DEBUG] [{PRINT_PREFIX}] PersistentLog model registered.")

# ~src/models/tables/api_key_table.py

from datetime import datetime

from sqlalchemy import func, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.services.logging import log_message

PRINT_PREFIX = "API KEY TABLE"

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    key_hash: Mapped[str] = mapped_column(nullable=False, unique=True)
    permission_level: Mapped[int] = mapped_column(nullable=False, default=0)
    rate_limit: Mapped[int] = mapped_column(nullable=False, default=1000)
    email: Mapped[str] = mapped_column(nullable=True, default="")
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )


log_message(f"[DEBUG] [{PRINT_PREFIX}] ApiKey model registered.")

# ~/src/models/tables/system/auth_cookie_table.py

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class AuthCookie(Base):
    __tablename__ = "auth_cookies"
    __table_args__ = (
        Index("ix_auth_cookies_expires_at_revoked", "expires_at", "revoked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    token_hash: Mapped[str] = mapped_column(nullable=False, unique=True)
    username: Mapped[str] = mapped_column(
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )
# ~/src/models/tables/system/user_roles.py

from datetime import datetime

from sqlalchemy import func, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

class UserRoles(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Cascade on both means that if a user or role is deleted, the corresponding entries in this table will also be deleted automatically.
    
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
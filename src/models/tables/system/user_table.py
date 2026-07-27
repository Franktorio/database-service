# ~src/models/tables/user_table.py

from datetime import datetime

from sqlalchemy import func, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ARRAY

from src.models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)

    username: Mapped[str] = mapped_column(nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)

    email: Mapped[str] = mapped_column(nullable=True, default="")
    password_salt: Mapped[str] = mapped_column(nullable=False, default="")
    hash_iterations: Mapped[int] = mapped_column(nullable=False, default=210000)
    hash_algorithm: Mapped[str] = mapped_column(nullable=False, default="pbkdf2_sha256")
    login_rate_limit: Mapped[int] = mapped_column(nullable=False, default=10)
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default_factory=list,
    )

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

    @property
    def role(self) -> str:
        """Backward-compatible primary role accessor backed by roles list."""
        return self.roles[0] if self.roles else ""

    @role.setter
    def role(self, value: str) -> None:
        self.roles = [value] if value else []

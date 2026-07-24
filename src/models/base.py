# ~/src/models/base.py
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from src.services.system.logging import log_message

PRINT_PREFIX = "MODEL BASE"

class Base(DeclarativeBase, MappedAsDataclass):
    def to_dict(self) -> dict:
        """Convert the SQLAlchemy model instance to a dictionary."""
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Serializing {self.__class__.__name__} to dictionary.")
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    def from_dict(self, data: dict):
        """Update the SQLAlchemy model instance from a dictionary."""
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Updating {self.__class__.__name__} from dictionary payload.")
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self


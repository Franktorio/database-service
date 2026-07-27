# ~/src/models/base.py
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

class Base(DeclarativeBase, MappedAsDataclass):
    def to_dict(self) -> dict:
        """Convert the SQLAlchemy model instance to a dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    def from_dict(self, data: dict):
        """Update the SQLAlchemy model instance from a dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self


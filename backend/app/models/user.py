import uuid
from sqlalchemy import UUID, Boolean, Column, Integer, String, Text
from sqlalchemy.orm import relationship
from app.config.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    active = Column(Boolean, default=True)
    password = Column(Text, nullable=True)
    roles = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan"
    )

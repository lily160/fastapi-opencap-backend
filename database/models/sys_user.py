from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String

from database.db import Base


class User(Base):
    __tablename__ = "sys_user"

    user_id = Column("user_id", String(36), primary_key=True, comment="user id")
    username = Column(String(32), unique=True, nullable=False, comment="username")
    password_hash = Column(String(255), nullable=False, comment="password hash")
    email = Column(String(255), unique=True, comment="email")
    phone = Column(String(32), unique=True, comment="phone")
    role = Column(String(32), nullable=False, comment="role")
    is_active = Column(Boolean, nullable=False, default=True, comment="is active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="created at")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="updated at")

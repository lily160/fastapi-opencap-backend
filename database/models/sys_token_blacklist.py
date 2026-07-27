from sqlalchemy import Column, DateTime, String
from datetime import datetime
from uuid import uuid4

from database.db import Base


class TokenBlacklist(Base):
    __tablename__ = 'sys_token_blacklist'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), comment="唯一ID")
    user_id = Column(String(64), index=True, nullable=False, comment="关联用户ID")
    token_hash = Column(String(64), unique=True, index=True, nullable=True, comment="Refresh Token哈希")
    jti = Column(String(64), unique=True, index=True, nullable=True, comment="Access Token唯一标识")
    token_type = Column(String(16), nullable=False, comment="Token类型(access/refresh)")
    expires_at = Column(DateTime, nullable=False, comment="Token过期时间")
    revoked_at = Column(DateTime, nullable=True, comment="Token失效时间")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")

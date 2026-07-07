from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey
from datetime import datetime
from database.db import Base

class TokenBlacklist(Base):
    __tablename__ = 'sys_token_blacklist'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增ID")
    token = Column(Text, nullable=False, comment="失效的Token")
    user_id = Column(String(64), ForeignKey('sys_user.user_id'), comment="关联用户ID")
    expired_at = Column(DateTime, nullable=False, comment="Token过期时间")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="加入黑名单时间")
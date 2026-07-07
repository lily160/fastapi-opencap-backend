from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from datetime import datetime
from database.db import Base

class UserPermissionOverride(Base):
    __tablename__ = 'sys_user_permission_override'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增ID")
    user_id = Column(String(64), ForeignKey('sys_user.user_id'), comment="用户ID")
    permission_code = Column(String(64), ForeignKey('sys_permission.permission_code'), comment="权限点编码")
    effect = Column(String(8), nullable=False, comment="grant / revoke")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
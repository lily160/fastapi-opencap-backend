from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from datetime import datetime
from database.db import Base

class RolePermission(Base):
    __tablename__ = 'sys_role_permission'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增ID")
    role = Column(String(16), nullable=False, comment="角色(user/admin)")
    permission_code = Column(String(64), ForeignKey('sys_permission.permission_code'), comment="权限点编码")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
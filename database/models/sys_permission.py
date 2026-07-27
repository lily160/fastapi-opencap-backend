from sqlalchemy import Column, String, DateTime
from datetime import datetime
from database.db import Base

class Permission(Base):
    __tablename__ = 'sys_permission'

    permission_code = Column(String(64), primary_key=True, comment="权限点编码")
    permission_name = Column(String(64), nullable=False, comment="权限点中文名称")
    description = Column(String(255), comment="权限说明")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
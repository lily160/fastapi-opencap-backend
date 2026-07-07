from sqlalchemy import Column, String, Integer, Boolean, DateTime
from datetime import datetime
from database.db import Base

class User(Base):
    __tablename__ = 'sys_user'

    user_id = Column(String(64), primary_key=True, comment="用户唯一ID")
    username = Column(String(32), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希值")
    email = Column(String(128), unique=True, comment="邮箱")
    phone = Column(String(20), unique=True, comment="手机号")
    role = Column(String(16), nullable=False, comment="角色(user/admin/super_admin)")
    permissions_version = Column(Integer, default=1, comment="权限版本号")
    is_active = Column(Boolean, nullable=False, default=True, comment="账号是否激活")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    last_login_at = Column(DateTime, comment="最后登录时间")
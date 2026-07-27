from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from database.db import Base


class ForgotPasswordSession(Base):
    __tablename__ = "sys_forgot_password"

    forgot_id = Column(String(64), primary_key=True, comment="忘记密码流程ID")
    user_id = Column(String(64), ForeignKey("sys_user.id"), nullable=False, index=True, comment="用户ID")
    contact_type = Column(String(16), comment="验证码发送方式")
    code_hash = Column(String(64), comment="验证码哈希")
    code_expires_at = Column(DateTime, comment="验证码过期时间")
    lookup_expires_at = Column(DateTime, nullable=False, comment="找回流程过期时间")
    last_sent_at = Column(DateTime, comment="最近发送时间")
    retry_count = Column(Integer, nullable=False, default=0, comment="验证码错误次数")
    used_at = Column(DateTime, comment="重置完成时间")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

from sqlalchemy import Column, String, BigInteger, Boolean, DateTime, ForeignKey
from datetime import datetime
from database.db import Base

class UploadFile(Base):
    __tablename__ = 'sys_upload_file'

    file_id = Column(String(64), primary_key=True, comment="文件唯一ID")
    user_id = Column(String(64), ForeignKey('sys_user.id'), comment="所属用户ID")
    original_name = Column(String(255), nullable=False, comment="文件原始名称")
    storage_name = Column(String(255), nullable=False, comment="存储名称")
    file_path = Column(String(512), nullable=False, comment="物理存储路径")
    file_size = Column(BigInteger, nullable=False, comment="文件大小(字节)")
    mime_type = Column(String(64), nullable=False, comment="文件MIME类型")
    file_type = Column(String(16), nullable=False, comment="文件类型(video/config/result)")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="上传时间")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="是否删除(软删除)")

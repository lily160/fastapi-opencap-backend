from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from database.db import Base


class CameraConfig(Base):
    __tablename__ = 'sys_camera_config'

    config_id = Column(String(64), primary_key=True, comment="配置文件唯一ID")
    file_type = Column(String(16), nullable=False, comment="配置类型(calib/intrinsics)")
    device_model = Column(String(64), nullable=False, comment="设备型号")
    file_id = Column(String(64), ForeignKey('sys_upload_file.file_id'), comment="配置文件存储ID")
    uploaded_by = Column(String(64), ForeignKey('sys_user.user_id'), comment="上传管理员ID")

    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="是否删除(软删除)")

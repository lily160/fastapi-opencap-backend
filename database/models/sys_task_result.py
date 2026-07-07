from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from database.db import Base


class TaskResult(Base):
    __tablename__ = 'sys_task_result'

    result_id = Column(String(64), primary_key=True, comment="结果文件唯一ID")
    task_id = Column(String(64), ForeignKey('sys_task.task_id'), comment="关联的包装后任务ID")
    algo_id = Column(String(64), ForeignKey('sys_task.algo_id'), comment="关联的算法原始任务ID")
    file_id = Column(String(64), ForeignKey('sys_upload_file.file_id'), comment="结果文件存储ID")

    file_type = Column(String(32), nullable=False, comment="结果文件类型")
    file_path = Column(String(512), nullable=False, comment="结果文件物理路径")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="生成时间")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="是否删除(软删除)")
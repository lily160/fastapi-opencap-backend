from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey
from datetime import datetime
from database.db import Base


class OperationLog(Base):
    __tablename__ = 'sys_operation_log'

    log_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增ID")
    user_id = Column(String(64), ForeignKey('sys_user.id'), comment="操作用户ID")
    operation_type = Column(String(32), nullable=False, comment="操作类型")

    task_id = Column(String(64), ForeignKey('sys_task.task_id'), nullable=True, comment="关联任务ID")
    algo_id = Column(String(64), nullable=True, comment="关联算法ID")
    file_id = Column(String(64), ForeignKey('sys_upload_file.file_id'), nullable=True, comment="关联文件ID")

    request_params = Column(Text, comment="请求参数摘要(脱敏)")
    ip_address = Column(String(64), comment="客户端IP地址")
    operation_result = Column(String(16), nullable=False, comment="操作结果(success/fail)")
    error_message = Column(Text, comment="错误信息")
    operation_time = Column(DateTime, nullable=False, default=datetime.utcnow, comment="操作时间")

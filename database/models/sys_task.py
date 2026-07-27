from sqlalchemy import Column, String, Boolean, DateTime, DECIMAL, Integer, Text, JSON, ForeignKey
from datetime import datetime
from database.db import Base


class Task(Base):
    __tablename__ = 'sys_task'

    task_id = Column(String(64), primary_key=True, comment="包装后的对外任务ID")
    algo_id = Column(String(64), unique=True, nullable=False, comment="算法原始任务ID")
    user_id = Column(String(64), ForeignKey('sys_user.id'), comment="任务创建用户ID")
    video_file_id = Column(String(64), ForeignKey('sys_upload_file.file_id'), comment="关联的视频文件ID")

    height_m = Column(DECIMAL(5, 2), nullable=False, comment="身高(米)")
    mass_kg = Column(DECIMAL(6, 2), nullable=False, comment="体重(千克)")
    sex = Column(String(8), nullable=False, comment="性别")
    activity = Column(String(50), nullable=False, comment="运动类型")

    calib_path = Column(String(512), comment="标定文件路径")
    intrinsics_path = Column(String(512), comment="相机内参路径")
    estimate_local_only = Column(Boolean, nullable=False, default=False, comment="是否仅本地估计")
    rerun = Column(Boolean, nullable=False, default=False, comment="是否重跑")

    status = Column(String(16), nullable=False, default="QUEUED", comment="任务状态")
    progress = Column(Integer, default=0, comment="任务进度")
    error_message = Column(Text, comment="错误信息")
    metadata_path = Column(String(512), nullable=False, comment="生成的metadata路径")
    estimated_duration = Column(Integer, comment="预估耗时(秒)")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    timeout_at = Column(DateTime, comment="任务超时时间")

    metadata_json = Column(JSON, comment="自定义扩展字段")
    pipeline_steps_json = Column(JSON, comment="流水线步骤快照")
    analysis_metrics_json = Column(JSON, comment="分析指标快照")

    is_deleted = Column(Boolean, nullable=False, default=False, comment="是否删除(软删除)")

import os
from celery import Celery

# 智能读取配置：优先读取 Docker 环境变量，如果本地直接跑则使用 localhost
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# 初始化 Celery 实例
celery_app = Celery(
    "algo_worker",
    broker=REDIS_URL,
    backend=BACKEND_URL,
    include=['routers.algo_tasks']

)

# 基础配置项（可选，推荐加上）
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
)

# 自动发现任务：会自动去项目根目录的 tasks 文件夹下找任务代码
celery_app.autodiscover_tasks(["tasks"])
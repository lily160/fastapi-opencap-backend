import logging
import uuid
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from database.db import SessionLocal
from database.models import Task, TaskResult
from core.algo_client import algo_client
from config.settings import POLL_INTERVAL, TASK_MAX_TIMEOUT_SEC

logger = logging.getLogger(__name__)


async def poll_tasks_job():
    """定时轮询任务进度的核心逻辑"""
    db: Session = SessionLocal()
    try:
        # 1. 从数据库捞出所有还在“排队”或“运行中”的任务
        active_tasks = db.query(Task).filter(
            Task.status.in_(["QUEUED", "RUNNING"]),
            Task.is_deleted == False
        ).all()

        for task in active_tasks:
            # 2. 超时兜底保护（如果超过 30 分钟还没算完，直接掐死）
            timeout_limit = task.created_at + timedelta(seconds=TASK_MAX_TIMEOUT_SEC)
            if datetime.utcnow() > timeout_limit:
                task.status = "FAILED"
                task.error_message = "任务执行超时（超过30分钟），已自动终止"
                continue

            try:
                # 3. 呼叫算法服务，查询真实状态
                res = await algo_client.get_status(task.algo_id)
                algo_status = res.get("status")

                if algo_status == "RUNNING":
                    task.status = "RUNNING"
                    task.progress = res.get("progress", task.progress)

                elif algo_status == "SUCCEEDED":
                    task.status = "SUCCEEDED"
                    task.progress = 100

                    # 4. 算完了！把算法返回的文件路径，登记到结果表(sys_task_result)里
                    result_paths = res.get("result_paths", {})
                    for file_type, path in result_paths.items():
                        new_result = TaskResult(
                            result_id=uuid.uuid4().hex,
                            task_id=task.task_id,
                            algo_id=task.algo_id,
                            file_type=file_type,
                            file_path=path
                        )
                        db.add(new_result)

                elif algo_status == "FAILED":
                    task.status = "FAILED"
                    task.error_message = res.get("error_message", "算法内部执行失败")

            except Exception as e:
                logger.error(f"轮询任务 {task.task_id} 异常: {str(e)}")

        # 5. 一次性把所有的状态更新提交到数据库
        db.commit()
    finally:
        db.close()


def start_scheduler():
    """启动定时调度器 (在 main.py 中被调用)"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_tasks_job, 'interval', seconds=POLL_INTERVAL)
    scheduler.start()
    logger.info("🤖 后台任务轮询调度器已启动...")
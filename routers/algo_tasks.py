# 文件路径：tasks/algo_tasks.py
import uuid
import logging
import asyncio
from core.celery_app import celery_app
from database.db import SessionLocal
from database.models import Task, TaskResult
from core.algo_client import algo_client

# 加上 @celery_app.task 装饰器，将它变成消息队列任务
@celery_app.task(name="process_algo_task", bind=True)
def process_algo_in_background(self, safe_task_id: str, algo_payload: dict):
    # 在 Celery 里，直接用原生同步查库，不需要 run_in_threadpool！
    db = SessionLocal()
    try:
        # 1. 更新状态为 RUNNING
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if task:
            task.status = "RUNNING"
            db.commit()

        # 2. 调用真正的异步算法 (用 asyncio.run 桥接即可)
        algo_response = asyncio.run(algo_client.run_mono(algo_payload))

        if not algo_response:
            raise ValueError("算法服务端未返回有效数据 (Response is None)")

        # 3. 拦截假取消
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if not task or task.status == "CANCELED":
            return

        # 4. 保存成功结果
        task.status = "SUCCEEDED"
        task.progress = 100

        result_paths = {
            "ik_results": algo_response.get("ik_file_path"),
            "mono_json": algo_response.get("json_file_path"),
            "viewer_video": algo_response.get("video_file_path"),
            "trc_file": algo_response.get("trc_file_path"),
            "scaled_model": algo_response.get("scaled_model_file_path")
        }

        for file_type, path in result_paths.items():
            if path:
                db.add(TaskResult(
                    result_id=uuid.uuid4().hex,
                    task_id=safe_task_id,
                    algo_id=safe_task_id,
                    file_type=file_type,
                    file_path=path
                ))
        db.commit()

    except Exception as e:
        logging.error(f"任务 {safe_task_id} 执行异常: {str(e)}", exc_info=True)
        # 兜底失败状态
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if task and task.status != "CANCELED":
            task.status = "FAILED"
            task.progress = 0
            task.error_message = f"算法运行失败: {str(e)}"
            db.commit()
    finally:
        db.close() # 必须关闭连接
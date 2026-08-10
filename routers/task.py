import uuid
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from config.constants import CODE_CREATE, CODE_PARAM_ERR, CODE_NOT_FOUND, CODE_FORBIDDEN
from core.algo_client import algo_client, cancel_algo_task
from core.id_wrapper import generate_task_id
from core.yaml_generator import generate_metadata_yaml
from database.db import get_db
from database.models import Task, UploadFile, User, TaskResult
from schemas.task.task_schema import TaskCreateReq
from core.rbac_permission import AuthContext, get_auth_context, require_permission

# 引入抽离出去的 Celery 任务
from routers.algo_tasks import process_algo_in_background

router = APIRouter()

DEFAULT_CALIB = r"D:\B24160206\conda\opencap-monocular\examples\walking4\calib.txt"
DEFAULT_INTRINSICS = r"D:\B24160206\conda\opencap-monocular\examples\Intrinsics\iPhone17,1\Deployed\cameraIntrinsics.pickle"


# ==========================================
# 创建任务
# ==========================================
@router.post("/mono", status_code=CODE_CREATE)
async def create_mono_task(
        req: TaskCreateReq,
        # 🚨 已删除 background_tasks: BackgroundTasks
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:create"))
):
    user_id = current_user.user_id

    # 1. 校验视频文件
    video = db.query(UploadFile).filter(
        UploadFile.file_id == req.video_file_id,
        UploadFile.user_id == user_id,
        UploadFile.is_deleted == False
    ).first()

    if not video:
        raise HTTPException(status_code=CODE_PARAM_ERR, detail="视频文件非法或无权限")

    video_absolute_path = os.path.abspath(video.file_path)

    # 2. 生成任务 ID 与配置
    temp_seed = f"seed-{uuid.uuid4().hex[:12]}"
    safe_task_id = generate_task_id(temp_seed)

    real_metadata_path = generate_metadata_yaml(
        task_id=safe_task_id,
        height_m=req.height_m,
        mass_kg=req.mass_kg,
        sex=req.sex,
        activity=req.activity,
        custom_metadata=req.metadata_info
    )

    final_calib = req.calib_path if req.calib_path else DEFAULT_CALIB
    final_intrinsics = req.intrinsics_path if req.intrinsics_path else DEFAULT_INTRINSICS

    algo_payload = {
        "video_path": video_absolute_path,
        "metadata_path": real_metadata_path,
        "calib_path": final_calib,
        "intrinsics_path": final_intrinsics,
        "estimate_local_only": req.estimate_local_only,
        "rerun": req.rerun,
        "session_id": safe_task_id,
        "activity": req.activity
    }

    # 3. 数据入库
    new_task = Task(
        task_id=safe_task_id,
        algo_id=safe_task_id,
        user_id=user_id,
        video_file_id=req.video_file_id,
        height_m=req.height_m,
        mass_kg=req.mass_kg,
        sex=req.sex,
        activity=req.activity,
        estimate_local_only=req.estimate_local_only,
        rerun=req.rerun,
        metadata_path=real_metadata_path,
        calib_path=final_calib,
        intrinsics_path=final_intrinsics,
        status="QUEUED"
    )
    db.add(new_task)
    db.commit()

    # 4. 🚀 丢给 Redis 和 Celery 处理！
    process_algo_in_background.delay(safe_task_id, algo_payload)

    return {
        "task_id": safe_task_id,
        "status": "QUEUED",
        "estimated_duration": 1800
    }


# ==========================================
# 查询单个任务状态
# ==========================================
@router.get("/{task_id}")
def get_task_status(
        task_id: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:read:self"))
):
    current_user_id = current_user.user_id

    task = db.query(Task).filter(Task.task_id == task_id, Task.is_deleted == False).first()
    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在")

    if task.user_id != current_user_id:
        raise HTTPException(status_code=CODE_FORBIDDEN, detail="权限不足")

    response_data = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "created_at": task.created_at,
        "error_message": task.error_message,
        "results": []
    }

    if task.status == "SUCCEEDED":
        results = db.query(TaskResult).filter(
            TaskResult.task_id == task_id,
            TaskResult.is_deleted == False
        ).all()
        response_data["results"] = [
            {"file_type": r.file_type, "result_id": r.result_id} for r in results
        ]

    return response_data


# ==========================================
# 查询个人任务列表
# ==========================================
@router.get("", status_code=200)
def get_task_list(
        status: Optional[str] = Query(None, description="任务状态筛选"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:read:self"))
):
    current_user_id = current_user.user_id

    query = db.query(Task).filter(Task.user_id == current_user_id, Task.is_deleted == False)
    if status:
        query = query.filter(Task.status == status)

    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    task_list = [{
        "task_id": t.task_id,
        "status": t.status,
        "activity": t.activity,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "progress": t.progress
    } for t in tasks]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "tasks": task_list
    }


# ==========================================
# 取消任务
# ==========================================
@router.post("/{task_id}/cancel", status_code=200)
def cancel_task(
        task_id: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:cancel:self"))
):
    current_user_id = current_user.user_id

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在或无权限")

    if task.status in ["QUEUED", "RUNNING"]:
        task.status = "CANCELED"
        db.commit()

    try:
        cancel_algo_task(task.algo_id)
    except Exception as e:
        logging.error(f"通知算法端取消任务 {task.algo_id} 失败: {e}")

    return {
        "task_id": task.task_id,
        "status": task.status
    }


# ==========================================
# 重跑任务
# ==========================================
@router.post("/{task_id}/rerun", status_code=200)
async def rerun_task(
        task_id: str,
        # 🚨 已删除 background_tasks: BackgroundTasks
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:rerun:self"))
):
    current_user_id = current_user.user_id

    old_task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not old_task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原任务不存在或无权限")

    video = db.query(UploadFile).filter(
        UploadFile.file_id == old_task.video_file_id,
        UploadFile.user_id == current_user_id,
        UploadFile.is_deleted == False
    ).first()

    if not video:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原视频文件已从硬盘彻底丢失或被删除")

    temp_seed = f"seed-rerun-{uuid.uuid4().hex[:12]}"
    new_safe_task_id = generate_task_id(temp_seed)

    rerun_calib = old_task.calib_path or DEFAULT_CALIB
    rerun_intrinsics = old_task.intrinsics_path or DEFAULT_INTRINSICS

    algo_payload = {
        "video_path": video.file_path,
        "metadata_path": old_task.metadata_path,
        "calib_path": rerun_calib,
        "intrinsics_path": rerun_intrinsics,
        "estimate_local_only": old_task.estimate_local_only,
        "rerun": True,
        "session_id": new_safe_task_id,
        "activity": old_task.activity
    }

    new_task = Task(
        task_id=new_safe_task_id,
        algo_id=new_safe_task_id,
        user_id=current_user_id,
        video_file_id=old_task.video_file_id,
        height_m=old_task.height_m,
        mass_kg=old_task.mass_kg,
        sex=old_task.sex,
        activity=old_task.activity,
        estimate_local_only=old_task.estimate_local_only,
        rerun=True,
        metadata_path=old_task.metadata_path,
        calib_path=rerun_calib,
        intrinsics_path=rerun_intrinsics,
        status="QUEUED"
    )
    db.add(new_task)
    db.commit()

    # 4. 🚀 丢给 Redis 和 Celery 处理！
    process_algo_in_background.delay(new_safe_task_id, algo_payload)

    return {
        "new_task_id": new_safe_task_id,
        "status": "QUEUED"
    }
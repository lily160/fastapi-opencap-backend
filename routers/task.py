import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config.constants import CODE_CREATE, CODE_PARAM_ERR, CODE_NOT_FOUND, CODE_FORBIDDEN
from core.algo_client import algo_client
from core.id_wrapper import generate_task_id
from core.yaml_generator import generate_metadata_yaml
from database.db import get_db
# 【修改1】引入 User 模型
from database.models import Task, UploadFile, User
from schemas.task.task_schema import TaskCreateReq
# 【修改2】从队友的 RBAC 权限模块引入核心鉴权依赖
from core.rbac_permission import AuthContext, get_auth_context

router = APIRouter()

# ==========================================
# 创建任务
# ==========================================
@router.post("/mono", status_code=CODE_CREATE)
async def create_mono_task(
    req: TaskCreateReq, 
    db: Session = Depends(get_db),
    # 【修改3】通过 Depends 注入当前登录用户对象
    auth_context: AuthContext = Depends(get_auth_context)
):
    # 直接提取真实登录用户的 ID
    user_id = auth_context.user.user_id

    # 校验视频文件是否归属当前用户
    video = db.query(UploadFile).filter(
        UploadFile.file_id == req.video_file_id,
        UploadFile.user_id == user_id,
        UploadFile.is_deleted == False
    ).first()

    if not video:
        raise HTTPException(status_code=CODE_PARAM_ERR, detail="视频文件非法或无权限")

    # 提前为这次调用算法计算出包装后的安全 task_id
    temp_seed = f"seed-{uuid.uuid4().hex[:12]}"
    safe_task_id = generate_task_id(temp_seed)

    # 动态生成 metadata.yaml 文件
    real_metadata_path = generate_metadata_yaml(
        task_id=safe_task_id,
        height_m=req.height_m,
        mass_kg=req.mass_kg,
        sex=req.sex,
        activity=req.activity,
        custom_metadata=req.metadata_info
    )

    # 组装传递给算法服务的参数载荷 (Payload)
    algo_payload = {
        "video_path": video.file_path,  
        "metadata_path": real_metadata_path,  
        "calib_path": req.calib_path or "default_calib.yaml",  
        "intrinsics_path": req.intrinsics_path or "default_intrinsics.yaml",  
        "estimate_local_only": req.estimate_local_only,
        "rerun": req.rerun,
        "session_id": safe_task_id,  
        "activity": req.activity
    }

    # 通过异步调用，向算法服务提交任务，获取真实的 algo_id
    raw_algo_id = await algo_client.run_mono(algo_payload)

    # 用真实的 algo_id 重新覆盖包装一次 task_id
    final_task_id = generate_task_id(raw_algo_id)

    # 数据入库，状态置为 QUEUED
    new_task = Task(
        task_id=safe_task_id,
        algo_id=raw_algo_id,
        user_id=user_id,
        video_file_id=req.video_file_id,
        height_m=req.height_m,
        mass_kg=req.mass_kg,
        sex=req.sex,
        activity=req.activity,
        estimate_local_only=req.estimate_local_only,
        rerun=req.rerun,
        metadata_path=real_metadata_path,
        status="QUEUED"
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return {
        "task_id": new_task.task_id,
        "status": new_task.status,
        "created_at": new_task.created_at,
        "estimated_duration": 300
    }


# ==========================================
# 查询单个任务状态
# ==========================================
@router.get("/{task_id}")
def get_task_status(
    task_id: str, 
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user_id = auth_context.user.user_id

    # 从数据库查询任务
    task = db.query(Task).filter(Task.task_id == task_id, Task.is_deleted == False).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在")

    # 核心权限校验：判断任务的拥有者，与当前请求者是否一致
    if task.user_id != current_user_id:
        raise HTTPException(
            status_code=CODE_FORBIDDEN,
            detail="权限不足：您无权查看其他用户的任务状态"
        )

    return {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "created_at": task.created_at,
        "error_message": task.error_message
    }


# ==========================================
# 查询个人任务列表
# ==========================================
@router.get("", status_code=200)
def get_task_list(
    status: Optional[str] = Query(None, description="任务状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user_id = auth_context.user.user_id

    # 构建基础查询（当前登录用户且未删除）
    query = db.query(Task).filter(
        Task.user_id == current_user_id,
        Task.is_deleted == False
    )

    # 状态筛选
    if status:
        query = query.filter(Task.status == status)

    # 计算总数并分页
    total = query.count()
    tasks = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 组装返回数据
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
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user_id = auth_context.user.user_id

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在或无权限")

    # 仅允许取消排队中或运行中的任务，且支持幂等性
    if task.status in ["QUEUED", "RUNNING"]:
        task.status = "CANCELED"
        db.commit()

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
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user_id = auth_context.user.user_id

    # 查询原任务参数
    old_task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not old_task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原任务不存在或无权限")

    video = db.query(UploadFile).filter(UploadFile.file_id == old_task.video_file_id).first()
    if not video:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原视频文件已从硬盘彻底丢失或被物理删除")

    # 预先包装一个临时的新 task_id 用作 session_id 传给算法
    temp_seed = f"seed-rerun-{uuid.uuid4().hex[:12]}"
    temp_new_task_id = generate_task_id(temp_seed)

    algo_payload = {
        "video_path": video.file_path,  
        "metadata_path": old_task.metadata_path,  
        "calib_path": old_task.calib_path or "default_calib.yaml",
        "intrinsics_path": old_task.intrinsics_path or "default_intrinsics.yaml",
        "estimate_local_only": old_task.estimate_local_only,
        "rerun": True,  
        "session_id": temp_new_task_id,  
        "activity": old_task.activity
    }

    # 异步调用算法获取全新的 algo_id
    new_raw_algo_id = await algo_client.run_mono(algo_payload)
    final_new_task_id = generate_task_id(new_raw_algo_id)

    new_task = Task(
        task_id=final_new_task_id,  
        algo_id=new_raw_algo_id,  
        user_id=current_user_id,
        video_file_id=old_task.video_file_id,
        height_m=old_task.height_m,
        mass_kg=old_task.mass_kg,
        sex=old_task.sex,
        activity=old_task.activity,
        estimate_local_only=old_task.estimate_local_only,
        rerun=True,  
        metadata_path=old_task.metadata_path,  
        status="QUEUED"
    )

    db.add(new_task)
    db.commit()

    return {
        "new_task_id": final_new_task_id,
        "status": "QUEUED"
    }
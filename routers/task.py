from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from database.models import Task, UploadFile
from schemas.task.task_schema import TaskCreateReq
from config.constants import CODE_CREATE, CODE_PARAM_ERR, CODE_NOT_FOUND, CODE_FORBIDDEN
from core.id_wrapper import generate_task_id
from core.yaml_generator import generate_metadata_yaml
from core.algo_client import algo_client

from fastapi import Query
from typing import Optional
import uuid

router = APIRouter()

# ==========================================
# 创建任务
# ==========================================
@router.post("/mono", status_code=CODE_CREATE)
async def create_mono_task(req: TaskCreateReq, db: Session = Depends(get_db)):
    # 模拟获取当前登录用户 (后续由组员 A 的 auth 模块提供 Depends 依赖)
    current_user_id = "test_user_id"

    # 校验视频文件是否归属当前用户
    video = db.query(UploadFile).filter(
        UploadFile.file_id == req.video_file_id,
        UploadFile.user_id == current_user_id,
        UploadFile.is_deleted == False
    ).first()

    if not video:
        raise HTTPException(status_code=CODE_PARAM_ERR, detail="视频文件非法或无权限")

    # ------------------ 新增/修改逻辑开始 ------------------
    #  提前为这次调用算法计算出包装后的安全 task_id
    # (因为调用算法服务需要传递这个作为 session_id)
    # 我们这里通过一个随机值来初始化产生一个临时唯一的 ID 种子，进而包装它
    temp_seed = f"seed-{uuid.uuid4().hex[:12]}"
    safe_task_id = generate_task_id(temp_seed)

    # 动态生成 metadata.yaml 文件(由 core/yaml_generator.py 实现)
    real_metadata_path = generate_metadata_yaml(
        task_id=safe_task_id,
        height_m=req.height_m,
        mass_kg=req.mass_kg,
        sex=req.sex,
        activity=req.activity,
        custom_metadata=req.metadata_info
    )

    # 组装传递给算法服务的参数载荷 (Payload)
    # 注：根据文档要求，如果用户是普通用户，则不传入自定义配置路径，后台在此处应设置默认配置
    algo_payload = {
        "video_path": video.file_path,  # 视频文件真实物理路径
        "metadata_path": real_metadata_path,  # 刚生成的元数据物理路径
        "calib_path": req.calib_path or "default_calib.yaml",  # 标定路径 (无则默认)
        "intrinsics_path": req.intrinsics_path or "default_intrinsics.yaml",  # 内参路径 (无则默认)
        "estimate_local_only": req.estimate_local_only,
        "rerun": req.rerun,
        "session_id": safe_task_id,  # 充当算法内部的 session_id
        "activity": req.activity
    }

    # 通过异步调用，向算法服务提交任务，获取真实的 algo_id
    # 算法内部服务如果报错崩溃，algo_client 会自动抛出 CustomException 被全局捕获
    raw_algo_id = await algo_client.run_mono(algo_payload)

    # 拿到真实的 algo_id 后，为了完全对齐包装逻辑，我们用真实的 algo_id 重新覆盖包装一次 task_id
    final_task_id = generate_task_id(raw_algo_id)

    # 数据入库，状态置为 QUEUED
    new_task = Task(
        task_id=safe_task_id,
        algo_id=raw_algo_id,
        user_id=current_user_id,
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

# TODO: 后续由组员 A 在 auth 模块实现标准的 get_current_user 依赖后引入
# from core.security import get_current_user_id

@router.get("/{task_id}")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    # 1. 引入用户鉴权依赖，获取当前发起请求的登录用户 ID
    # current_user_id: str = Depends(get_current_user_id)
    # 【临时模拟】在组员 A 写好鉴权前，先用临时变量模拟当前登录的用户 ID
    current_user_id = "test_user_id"

    # 2. 从数据库查询任务（仅凭包装后的 task_id 和未软删除状态）
    task = db.query(Task).filter(Task.task_id == task_id, Task.is_deleted == False).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在")

    # ------------------ 补齐 TODO：权限安全校验 ------------------
    # 3. 核心权限校验：判断任务的拥有者，与当前请求者是否一致
    # （注：如果后续拓展管理员权限，可以在这里加上 `or current_user_role in ['admin', 'super_admin']` 放行）
    if task.user_id != current_user_id:
        raise HTTPException(
            status_code=CODE_FORBIDDEN,
            detail="权限不足：您无权查看其他用户的任务状态"
        )
    # ------------------ 校验结束 ------------------

    # 返回数据库中缓存的状态，实现前端与算法的解耦
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
        db: Session = Depends(get_db)
):
    # TODO: 替换为真实鉴权获取 user_id
    current_user_id = "test_user_id"

    # 构建基础查询（当前用户且未删除）
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
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    # TODO: 替换为真实鉴权获取 user_id
    current_user_id = "test_user_id"

    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在或无权限")

    # 仅允许取消排队中或运行中的任务，且支持幂等性（已经是 CANCELED 就不报错）
    if task.status in ["QUEUED", "RUNNING"]:
        task.status = "CANCELED"
        # TODO: 后续可在此处追加调用算法侧的强制终止接口（如果算法支持的话）
        db.commit()

    return {
        "task_id": task.task_id,
        "status": task.status
    }


# ==========================================
# 重跑任务
# ==========================================
@router.post("/{task_id}/rerun", status_code=200)
async def rerun_task(task_id: str, db: Session = Depends(get_db)):
    # TODO: 替换为真实鉴权获取 user_id
    current_user_id = "test_user_id"

    # 查库提取：查询原任务参数
    old_task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not old_task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原任务不存在或无权限")

    # ------------------ 新增/修改逻辑开始 ------------------

    # 【就是漏了这两行！】拿着旧任务里记下来的视频 ID，去上传文件表（sys_upload_file）里查出视频的真实物理路径
    video = db.query(UploadFile).filter(UploadFile.file_id == old_task.video_file_id).first()
    if not video:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原视频文件已从硬盘彻底丢失或被物理删除")

    # 预先包装一个临时的新 task_id 用作 session_id 传给算法
    temp_seed = f"seed-rerun-{uuid.uuid4().hex[:12]}"
    temp_new_task_id = generate_task_id(temp_seed)

    # 组装历史参数载荷，向算法重新发起请求
    algo_payload = {
        "video_path": video.file_path,  # 复制原视频真实物理路径
        "metadata_path": old_task.metadata_path,  # 复用旧的 metadata 物理路径
        "calib_path": old_task.calib_path or "default_calib.yaml",
        "intrinsics_path": old_task.intrinsics_path or "default_intrinsics.yaml",
        "estimate_local_only": old_task.estimate_local_only,
        "rerun": True,  # 标记为 True (重跑)
        "session_id": temp_new_task_id,  # 传递临时的 session_id
        "activity": old_task.activity
    }

    # 【异步调用算法】获取全新的 algo_id
    new_raw_algo_id = await algo_client.run_mono(algo_payload)

    # 对最终拿到的新 algo_id 进行安全精细包装
    final_new_task_id = generate_task_id(new_raw_algo_id)

    # 提取旧参数，在本地数据库创建全新任务记录
    new_task = Task(
        task_id=final_new_task_id,  # 关联全新包装后的 task_id
        algo_id=new_raw_algo_id,  # 关联全新拿回的 algo_id
        user_id=current_user_id,
        video_file_id=old_task.video_file_id,
        height_m=old_task.height_m,
        mass_kg=old_task.mass_kg,
        sex=old_task.sex,
        activity=old_task.activity,
        estimate_local_only=old_task.estimate_local_only,
        rerun=True,  # 标记为重跑任务
        metadata_path=old_task.metadata_path,  # 复用原配置文件路径
        status="QUEUED"
    )

    db.add(new_task)
    db.commit()

    # 返回全新包装后的任务 ID
    return {
        "new_task_id": final_new_task_id,
        "status": "QUEUED"
    }

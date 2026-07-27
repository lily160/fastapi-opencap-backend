import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config.constants import CODE_CREATE, CODE_PARAM_ERR, CODE_NOT_FOUND, CODE_FORBIDDEN
from core.algo_client import algo_client
from core.id_wrapper import generate_task_id
from core.yaml_generator import generate_metadata_yaml
from database.db import get_db, SessionLocal
# 【修改1】引入 User 模型
from database.models import Task, UploadFile, User, TaskResult
from schemas.task.task_schema import TaskCreateReq
# 【修改2】从队友的 RBAC 权限模块引入核心鉴权依赖
from core.rbac_permission import AuthContext, get_auth_context, require_permission

router = APIRouter()

# ==========================================
# 创建任务
# ==========================================
from fastapi import BackgroundTasks
import os

DEFAULT_CALIB = r"D:\B24160206\conda\opencap-monocular\examples\walking4\calib.txt"
DEFAULT_INTRINSICS = r"D:\B24160206\conda\opencap-monocular\examples\Intrinsics\iPhone17,1\Deployed\cameraIntrinsics.pickle"
# ==========================================
# 后台任务：处理“死等模式”的算法请求
# ==========================================
async def process_algo_in_background(safe_task_id: str, algo_payload: dict):
    # 🌟 极度关键：必须开启全新且独立的数据库 Session
    db: Session = SessionLocal()
    try:
        # 1. 算法开始前，将状态变更为“运行中”
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if task:
            task.status = "RUNNING"
            db.commit()

        # 2. 调用算法接口
        algo_response = await algo_client.run_mono(algo_payload)

        # 🚨 防御 1：拦截空返回值
        if not algo_response:
            raise ValueError("算法服务端未返回有效数据或请求失败 (Response is None)")

        # 🚨 防御 2：先提取数据，此时先不要去改数据库里的状态为成功
        result_paths = {
            "ik_results": algo_response.get("ik_file_path"),
            "mono_json": algo_response.get("json_file_path"),
            "viewer_video": algo_response.get("video_file_path"),
            "trc_file": algo_response.get("trc_file_path"),
            "scaled_model": algo_response.get("scaled_model_file_path")
        }

        # 🚨 防御 3：防骗校验 (防止算法谎报 200 但什么都没生成)
        if not result_paths.get("ik_results") and not result_paths.get("mono_json"):
             raise Exception("算法接口貌似执行成功，但未能提取到核心结果文件路径")

        # 3. 只有在解析和校验全都通过后，才正式宣告成功！
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if task:
            task.status = "SUCCEEDED"
            task.progress = 100

            # 4. 将各种结果文件存入 TaskResult 表
            for file_type, path in result_paths.items():
                if path:  # 如果算法生成了该文件
                    new_result = TaskResult(
                        result_id=uuid.uuid4().hex,
                        task_id=safe_task_id,
                        algo_id=safe_task_id,
                        file_type=file_type,
                        file_path=path
                    )
                    db.add(new_result)
            db.commit()

    except Exception as e:
        # 兜底：如果算法超时、崩溃或解析异常
        task = db.query(Task).filter(Task.task_id == safe_task_id).first()
        if task:
            task.status = "FAILED"
            task.progress = 0  # 🚨 失败时一定要确保进度归零或保持当前进度
            task.error_message = f"算法运行失败: {str(e)}"
            db.commit()
    finally:
        # 🌟 极度关键：跑完必须关闭独立的 Session
        db.close()

# ==========================================
# 主接口：负责鉴权、参数校验、入库与分发
# ==========================================
@router.post("/mono", status_code=CODE_CREATE)
async def create_mono_task(
        req: TaskCreateReq,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission("task:create"))
):
    user_id = current_user.user_id

    # 1. 校验视频文件（必须拿到视频的绝对路径）
    video = db.query(UploadFile).filter(
        UploadFile.file_id == req.video_file_id,
        UploadFile.user_id == user_id,
        UploadFile.is_deleted == False
    ).first()

    if not video:
        raise HTTPException(status_code=CODE_PARAM_ERR, detail="视频文件非法或无权限")

    video_absolute_path = os.path.abspath(video.file_path)

    # 2. 生成对外的安全 task_id
    temp_seed = f"seed-{uuid.uuid4().hex[:12]}"
    safe_task_id = generate_task_id(temp_seed)

    # 3. 动态生成 metadata.yaml 文件（拿到绝对路径）
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

    # 4. 组装传递给算法服务的参数载荷
    algo_payload = {
        "video_path": video_absolute_path,
        "metadata_path": real_metadata_path,
        "calib_path": final_calib,
        "intrinsics_path": final_intrinsics,
        "estimate_local_only": req.estimate_local_only,
        "rerun": req.rerun,
        "session_id": safe_task_id,  # 算法会把这个作为 case_dir 的文件夹名
        "activity": req.activity
    }

    # 5. 直接入库！不要在接口里 await 算法服务！
    new_task = Task(
        task_id=safe_task_id,
        algo_id=safe_task_id,  # 既然算法不返回真正的algo_id了，用同一个值占位
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

    # 6. 将超级耗时的任务丢给后台执行，注意只需传 ID 和 Payload
    background_tasks.add_task(process_algo_in_background, safe_task_id, algo_payload)

    # 7. 接口在一瞬间响应前端，实现无缝交互
    return {
        "task_id": safe_task_id,
        "status": "QUEUED",
        "estimated_duration": 1800  # 建议返回预估时间（秒）
    }

# ==========================================
# 查询单个任务状态
# ==========================================
from database.models import Task, TaskResult  # 记得引入 TaskResult


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

    # 1. 从数据库查询任务主表
    task = db.query(Task).filter(Task.task_id == task_id, Task.is_deleted == False).first()

    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="任务不存在")

    # 2. 核心权限校验：防止越权
    if task.user_id != current_user_id:
        raise HTTPException(
            status_code=CODE_FORBIDDEN,
            detail="权限不足：您无权查看其他用户的任务状态"
        )

    # 3. 组装基础返回体
    response_data = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "created_at": task.created_at,
        "error_message": task.error_message,
        "results": []  # 👈 新增结果占位符
    }

    # 4. 如果任务已经成功，去 sys_task_result 表里把产出的文件记录拿出来
    if task.status == "SUCCEEDED":
        results = db.query(TaskResult).filter(
            TaskResult.task_id == task_id,
            TaskResult.is_deleted == False
        ).all()

        # 组装结果文件信息（注意：这里最好只返回 file_type 和 result_id 给前端去调用下载接口，不要暴露服务器物理绝对路径 file_path）
        response_data["results"] = [
            {
                "file_type": r.file_type,
                "result_id": r.result_id,
                # "download_url": f"/api/v1/download/{r.result_id}" # 甚至可以直接拼装好下载链接给前端
            } for r in results
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
        # 👇 换成高级金库锁
        current_user: User = Depends(require_permission("task:read:self"))
):
    current_user_id = current_user.user_id

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
        # 👇 换成高级金库锁
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
# 别忘了在函数签名注入 BackgroundTasks
@router.post("/{task_id}/rerun", status_code=200)
async def rerun_task(
    task_id: str,
    background_tasks: BackgroundTasks, # 👈 必须加上这个
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("task:rerun:self"))
):
    current_user_id = current_user.user_id

    # 1. 查询原任务参数
    old_task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == current_user_id,
        Task.is_deleted == False
    ).first()

    if not old_task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原任务不存在或无权限")

    video = db.query(UploadFile).filter(UploadFile.file_id == old_task.video_file_id).first()
    if not video:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="原视频文件已从硬盘彻底丢失")

    # 2. 生成新的任务ID
    temp_seed = f"seed-rerun-{uuid.uuid4().hex[:12]}"
    new_safe_task_id = generate_task_id(temp_seed)

    # 3. 组装载荷 (注意这里默认值最好用您文件顶部定义的常量)
    algo_payload = {
        "video_path": video.file_path,
        "metadata_path": old_task.metadata_path,
        "calib_path": old_task.calib_path or DEFAULT_CALIB,
        "intrinsics_path": old_task.intrinsics_path or DEFAULT_INTRINSICS,
        "estimate_local_only": old_task.estimate_local_only,
        "rerun": True,
        "session_id": new_safe_task_id,
        "activity": old_task.activity
    }

    # 4. 直接入库（不等待算法！）
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
        status="QUEUED" # 初始状态必须是排队
    )
    db.add(new_task)
    db.commit()

    # 5. 把苦力活丢给后台！
    background_tasks.add_task(process_algo_in_background, new_safe_task_id, algo_payload)

    # 6. 瞬间响应前端
    return {
        "new_task_id": new_safe_task_id,
        "status": "QUEUED"
    }
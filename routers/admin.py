from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database.db import get_db
from core.security import get_current_user
from core.rbac_permission import require_admin, require_super_admin, require_permission
from core.file_security import save_config_file
from utils.uuid_util import generate_uuid
from config.constants import *
# 修复模型导入：使用大写ORM类名（匹配models文件定义）
from database.models.sys_task import Task
from database.models.sys_camera_config import CameraConfig
from database.models.sys_upload_file import UploadFile as DBUploadFile
from database.models.sys_user import User
from database.models.sys_task_result import TaskResult
from database.models.sys_permission import Permission
from database.models.sys_role_permission import RolePermission
from database.models.sys_user_permission_override import UserPermissionOverride
from schemas.admin.admin_schema import *
from core.rbac_permission import AuthContext, get_auth_context

router = APIRouter()

# ====================== 6.1 查看全量任务列表 ======================
@router.get("/tasks", response_model=PageResp)
def admin_get_all_tasks(
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    require_permission(current_user, "task:read:admin")
    query = db.query(Task).filter(Task.is_deleted == 0)
    if status:
        query = query.filter(Task.status == status)
    if user_id:
        query = query.filter(Task.user_id == user_id)
    total = query.count()
    tasks = query.offset((page-1)*page_size).limit(page_size).all()
    task_list = [{
        "task_id": t.task_id,
        "status": t.status,
        "activity": t.activity,
        "created_at": t.created_at.isoformat()+"Z",
        "updated_at": t.updated_at.isoformat()+"Z",
        "progress": t.progress
    } for t in tasks]
    return {"total": total, "page": page, "page_size": page_size, "tasks": task_list}

# ====================== 6.2 上传相机配置文件 ======================
@router.post("/config/intrinsics", response_model=CameraConfigResp)
def upload_camera_config(
    file_type: str = Query(..., pattern="^(calib|intrinsics)$"),
    device_model: str = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    file_info = save_config_file(file, current_user.user_id, file_type)
    config_id = generate_uuid()
    cfg = CameraConfig(
        config_id=config_id,
        file_type=file_type,
        device_model=device_model,
        file_id=file_info["file_id"],
        uploaded_by=current_user.user_id,
        is_deleted=0
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return CameraConfigResp(
        config_id=cfg.config_id,
        device_model=device_model,
        file_type=file_type,
        updated_at=cfg.updated_at.isoformat()+"Z"
    )

# ====================== 6.3 获取相机配置列表 ======================
@router.get("/configs")
def list_camera_config(
    device_model: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    query = db.query(CameraConfig, UploadFile, User)\
        .join(UploadFile, CameraConfig.file_id == UploadFile.file_id)\
        .join(User, CameraConfig.uploaded_by == User.user_id)\
        .filter(CameraConfig.is_deleted == 0)
    if device_model:
        query = query.filter(CameraConfig.device_model == device_model)
    if file_type:
        query = query.filter(CameraConfig.file_type == file_type)
    rows = query.all()
    configs = []
    for cfg, uf, user in rows:
        configs.append(CameraConfigItem(
            config_id=cfg.config_id,
            device_model=cfg.device_model,
            file_type=cfg.file_type,
            file_name=uf.original_name,
            uploaded_by_username=user.username,
            updated_at=cfg.updated_at.isoformat()+"Z"
        ))
    return {"total": len(configs), "configs": configs}

# ====================== 6.4 删除相机配置 ======================
@router.delete("/configs/{config_id}", status_code=CODE_NO_CONTENT)
def delete_camera_config(
    config_id: str,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    cfg = db.query(CameraConfig).filter(CameraConfig.config_id == config_id).first()
    if not cfg:
        raise HTTPException(CODE_NOT_FOUND, "配置不存在")
    cfg.is_deleted = 1
    db.commit()
    return

# ====================== 6.5 查看全量用户列表 ======================
@router.get("/users", response_model=PageResp)
def list_all_user(
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    require_permission(current_user, "user:manage")
    query = db.query(User)
    if username:
        query = query.filter(User.username.like(f"%{username}%"))
    total = query.count()
    users = query.offset((page-1)*page_size).limit(page_size).all()
    user_list = []
    for u in users:
        task_cnt = db.query(Task).filter(Task.user_id == u.user_id, Task.is_deleted == 0).count()
        user_list.append(AdminUserItem(
            user_id=u.user_id,
            username=u.username,
            role=u.role,
            is_active=u.is_active == 1,
            task_count=task_cnt,
            created_at=u.created_at.isoformat()+"Z"
        ))
    return {"total": total, "page": page, "page_size": page_size, "users": user_list}

# ====================== 6.6 修改用户状态/封禁 ======================
@router.put("/users/{user_id}")
def update_user_status(
    user_id: str,
    body: UserStatusUpdate,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    require_permission(current_user, "user:manage")
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(CODE_NOT_FOUND, "用户不存在")
    user.is_active = 1 if body.is_active else 0
    db.commit()
    return {"user_id": user_id, "is_active": body.is_active, "message": "User status updated successfully"}

# ====================== 6.7 管理员强制取消任务 ======================
@router.post("/tasks/{task_id}/force-cancel")
def force_cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    require_permission(current_user, "task:force_cancel:admin")
    task = db.query(Task).filter(Task.task_id == task_id, Task.is_deleted == 0).first()
    if not task:
        raise HTTPException(CODE_NOT_FOUND, "任务不存在")
    if task.status not in [TaskStatus.QUEUED, TaskStatus.RUNNING]:
        raise HTTPException(CODE_PARAM_ERR, "仅排队/运行中任务可取消")
    # 导入并调用取消算法任务函数
    from core.algo_client import cancel_algo_task
    cancel_algo_task(task.algo_id)
    task.status = TaskStatus.CANCELED
    db.commit()
    return {"task_id": task_id, "status": "CANCELED", "message": "Task forcefully canceled by administrator"}

# ====================== 6.8 超级管理员修改用户角色 ======================
@router.put("/users/{user_id}/role")
def change_user_role(
    user_id: str,
    body: UserRoleUpdate,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_super_admin(current_user)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(CODE_NOT_FOUND, "用户不存在")
    if user.role == UserRole.SUPER_ADMIN:
        raise HTTPException(CODE_CONFLICT, "禁止修改超级管理员角色")
    user.role = body.role
    user.permissions_version += 1 # 权限版本自增，旧Token失效
    db.commit()
    return {
        "user_id": user_id,
        "username": user.username,
        "role": body.role,
        "message": "User role updated successfully"
    }

# ====================== 6.9 批量删除任务 ======================
@router.post("/tasks/batch-delete", response_model=BatchDeleteResp)
def batch_delete_task(
    req: BatchDeleteTaskReq,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_admin(current_user)
    require_permission(current_user, "task:delete:admin")
    if len(req.task_ids) == 0 or len(req.task_ids) > 100:
        raise HTTPException(CODE_PARAM_ERR, "任务ID列表不能为空或超过100条")
    deleted = 0
    fail_list = []
    for tid in req.task_ids:
        t = db.query(Task).filter(Task.task_id == tid, Task.is_deleted == 0).first()
        if not t:
            fail_list.append({"task_id": tid, "reason": "task not found"})
            continue
        if t.status in [TaskStatus.QUEUED, TaskStatus.RUNNING]:
            fail_list.append({"task_id": tid, "reason": "运行/排队任务禁止删除"})
        else:
            t.is_deleted = 1
            deleted += 1
    db.commit()
    return BatchDeleteResp(deleted_count=deleted, failed=fail_list)

# ====================== 6.10 权限点列表 ======================
@router.get("/permissions")
def list_permissions(
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_super_admin(current_user)
    return {"permissions": PERMISSION_LIST}

# ====================== 6.11 角色权限配置 ======================
@router.put("/roles/{role}/permissions")
def config_role_permission(
    role: str,
    body: RolePermissionReq,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_super_admin(current_user)
    require_permission(current_user, "permission:manage")
    if role not in [UserRole.USER, UserRole.ADMIN]:
        raise HTTPException(CODE_PARAM_ERR, "角色仅支持user/admin")
    # 清空原有角色权限
    db.query(RolePermission).filter(RolePermission.role == role).delete()
    for perm_code in body.permissions:
        rp = RolePermission(role=role, permission_code=perm_code)
        db.add(rp)
    db.commit()
    return {
        "role": role,
        "permissions": body.permissions,
        "message": "Role permissions updated successfully"
    }

# ====================== 6.12 用户权限覆盖 ======================
@router.put("/users/{user_id}/permissions")
def user_permission_override(
    user_id: str,
    body: UserPermissionOverrideReq,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_auth_context)
):
    current_user = auth_context.user
    require_super_admin(current_user)
    require_permission(current_user, "permission:manage")
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(CODE_NOT_FOUND, "用户不存在")
    # 清空该用户原有覆盖权限
    db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == user_id).delete()
    # 新增grant/revoke权限
    for code in body.grant:
        db.add(UserPermissionOverride(user_id=user_id, permission_code=code, effect="grant"))
    for code in body.revoke:
        db.add(UserPermissionOverride(user_id=user_id, effect="revoke", permission_code=code))
    user.permissions_version += 1
    db.commit()
    # 合并角色+覆盖权限返回
    from core.security import merge_user_permissions
    final_perms = merge_user_permissions(db, user)
    return {
        "user_id": user_id,
        "permissions": final_perms,
        "message": "User permissions updated successfully"
    }

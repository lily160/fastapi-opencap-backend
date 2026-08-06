from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.constants import UserRole
from core.security import AuthContext, get_auth_context, get_current_user
from database.db import get_db
from database.models.sys_user import User
from database.models.sys_role_permission import RolePermission
from database.models.sys_user_permission_override import UserPermissionOverride


# ===================== 角色权限基础映射工具 =====================
def get_role_permissions(role: str) -> list[str]:
    # 兼容枚举和字符串两种转入
    role_value = role.value if hasattr(role, "value") else role
    if role_value == UserRole.SUPER_ADMIN.value:
        return ["*"]
    if role_value == UserRole.ADMIN.value:
        return ["task:read:admin", "task:delete:admin", "user:manage"]
    return ["task:create", "task:read:self"]


def merge_user_permissions(db: Session, user: User) -> list[str]:
    # 如果是超级管理员，直接返回通配符最高权限，不需要去查数据库
    role_value = user.role.value if hasattr(user.role, "value") else user.role
    if role_value == UserRole.SUPER_ADMIN.value:  # 或者直接写 "super_admin"
        return ["*"]

    """合并角色默认权限 + 用户自定义grant/revoke覆盖权限"""

    # 获取角色基础权限
    base_rp_list = db.query(RolePermission).filter(RolePermission.role == user.role).all()
    base_perms = [op.permission_code for op in base_rp_list]

    # 获取用户授予权限
    grant_op_list = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user.user_id,
        UserPermissionOverride.effect == "grant"
    ).all()
    grant_codes = [op.permission_code for op in grant_op_list]

    # 获取用户撤销权限
    revoke_op_list = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user.user_id,
        UserPermissionOverride.effect == "revoke"
    ).all()
    revoke_codes = [op.permission_code for op in revoke_op_list]

    # 合并并去重，移除撤销项
    full = list(set(base_perms + grant_codes))
    final = [p for p in full if p not in revoke_codes]
    return final


# ===================== 细粒度权限校验依赖工厂 =====================
def require_permission(permission: str):
    """
    生成权限校验依赖：校验当前用户是否拥有指定权限
    用法：Depends(require_permission("task:delete:admin"))
    """
    def dependency(
            auth_ctx: AuthContext = Depends(get_auth_context),
            db: Session = Depends(get_db)
    ) -> User:
        # 优先使用JWT携带权限，实时校验读取数据库最终权限
        real_perms = merge_user_permissions(db, auth_ctx.user)
        if "*" not in real_perms and permission not in real_perms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return auth_ctx.user

    return dependency


# ===================== 角色准入校验依赖 =====================
def require_admin(user: User = Depends(get_current_user)) -> User:
    """校验当前用户是普通管理员/超级管理员"""
    if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin permission required")
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """仅允许超级管理员访问"""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super admin permission required")
    return user

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.constants import UserRole
from core.security import decode_token, get_current_user
from database.db import get_db
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User

# 实例化 HTTPBearer 身份验证方案。
# auto_error=True 表示如果请求头中没有有效的 Authorization: Bearer <token>，
# FastAPI 会在进入路由函数前自动拦截请求，并返回 HTTP 403 Forbidden 错误。
bearer_scheme = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class AuthContext:
    user: User
    token: str
    payload: dict

def get_role_permissions(role: str) -> list[str]:
    role_value = role.value if hasattr(role, "value") else role#兼容枚举和字符串两种转入
    if role_value == UserRole.SUPER_ADMIN.value:
        return ["*"]
    if role_value == UserRole.ADMIN.value:
        return ["task:read:admin", "task:delete:admin", "user:manage"]
    return ["task:create", "task:read:self"]


async def get_auth_context(
     # 从请求头 Authorization: Bearer <token> 中自动解析 JWT
    auth_info: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    try:
        # 解码 JWT，同时验证签名、过期时间等
        payload = decode_token(auth_info.credentials)
    except JWTError as exc:
        # Token 非法、过期或被篡改
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的访问令牌") from exc
    # 本接口只允许使用 Access Token，
    # Refresh Token 不能访问业务接口
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的访问令牌")
    # 如果用户退出登录，会将 JWT 的 jti 写入黑名单，
    # 后续即使 Token 未过期，也不能继续使用。
    result = await db.execute(
        select(TokenBlacklist).where(
            TokenBlacklist.jti == payload.get("jti"),
            TokenBlacklist.token_type == "access",
        )
    )
    revoked = result.scalars().first()
    if revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="access token revoked")
    #查询用户
    user = await db.get(User, payload.get("sub"))
    # 用户不存在或已被禁用，不允许继续访问
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is disabled")
    # 将当前用户、Token 和 JWT Payload 封装成 AuthContext，
    # 后续接口可直接使用，不需要再次解析 Token。
    return AuthContext(user=user, token=auth_info.credentials, payload=payload)


def require_permission(permission: str):
    def dependency(auth_context: AuthContext = Depends(get_auth_context)) -> User:
        # 从 JWT Payload 中获取权限列表
        # 如果不存在 permissions 字段，则默认返回空列表
        permissions = auth_context.payload.get("permissions", [])
        # 判断是否具有权限
        # "*" 表示超级管理员，拥有所有权限
        # 否则必须拥有指定 permission 才允许访问
        if "*" not in permissions and permission not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return auth_context.user

    return dependency

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

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from config.constants import UserRole
from core.security import decode_token, get_current_user
from database.db import get_db
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User

bearer_scheme = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class AuthContext:
    user: User
    token: str
    payload: dict


def get_role_permissions(role: str) -> list[str]:
    role_value = role.value if hasattr(role, "value") else role
    if role_value == UserRole.SUPER_ADMIN.value:
        return ["*"]
    if role_value == UserRole.ADMIN.value:
        return ["task:read:admin", "task:delete:admin", "user:manage"]
    return ["task:create", "task:read:self"]


def get_auth_context(
    auth_info: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    try:
        payload = decode_token(auth_info.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")

    revoked = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.jti == payload.get("jti"), TokenBlacklist.token_type == "access")
        .first()
    )
    if revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="access token revoked")

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is disabled")

    return AuthContext(user=user, token=auth_info.credentials, payload=payload)



def require_permission(permission: str):
    def dependency(auth_context: AuthContext = Depends(get_auth_context)) -> User:
        permissions = auth_context.payload.get("permissions", [])
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

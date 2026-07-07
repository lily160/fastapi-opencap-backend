from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional

from jose import jwt , JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config.settings import ACCESS_TOKEN_EXPIRE_SECONDS, ALGORITHM, REFRESH_TOKEN_DAYS, SECRET_KEY
from database.db import get_db
from database.models.sys_user import User
from database.models.sys_token_blacklist import TokenBlacklist
from config.constants import CODE_UNAUTH

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, role: str, permissions: list[str]) -> tuple[str, datetime]:
    expires_at = utc_now() + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)
    payload = {
        "sub": user_id,
        "role": role,
        "permissions": permissions,
        "type": "access",
        "exp": expires_at,
        "iat": utc_now(),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), expires_at


def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    expires_at = utc_now() + timedelta(days=REFRESH_TOKEN_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expires_at,
        "iat": utc_now(),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), expires_at


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> User:
    """
    全局登录鉴权依赖，所有需要登录的接口统一依赖此函数
    校验逻辑：Bearer Token提取 → JWT解析 → 黑名单校验 → 用户存在校验 → 账号激活校验
    """
    credentials_exception = HTTPException(
        status_code=CODE_UNAUTH,
        detail="未登录或Token无效/已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. 解析JWT载荷
        payload = decode_token(token)
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        jti: Optional[str] = payload.get("jti")
        if user_id is None or token_type != "access" or jti is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 2. 校验Token是否在黑名单（登出/改密后失效）
    black_token = db.query(TokenBlacklist).filter(
        TokenBlacklist.token == token,
        TokenBlacklist.expired_at > utc_now()
    ).first()
    if black_token:
        raise credentials_exception

    # 3. 查询数据库用户信息
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise credentials_exception

    # 4. 校验账号是否被封禁
    if user.is_active != 1:
        raise HTTPException(status_code=CODE_UNAUTH, detail="账号已被封禁，禁止登录")

    # 5. 权限版本校验（角色/权限变更后旧Token强制失效）
    token_perm_version = payload.get("perm_version", 1)
    if token_perm_version < user.permissions_version:
        raise HTTPException(status_code=CODE_UNAUTH, detail="用户权限已变更，请重新登录")

    # 6. 返回完整用户ORM对象，供后续RBAC、权限校验使用
    return user

def merge_user_permissions(db: Session, user: User) -> list[str]:
    """合并角色默认权限 + 用户自定义grant/revoke覆盖权限"""
    from database.models.sys_role_permission import RolePermission
    from database.models.sys_user_permission_override import UserPermissionOverride
    from config.constants import PERMISSION_LIST

    # 1. 获取角色基础权限（修复原代码db.query写法语法错误，补充遍历变量op）
    base_rp_list = db.query(RolePermission).filter(RolePermission.role == user.role).all()
    base_perms = [op.permission_code for op in base_rp_list]

    # 2. 获取用户授予权限（user_id从入参user对象取 user.user_id）
    grant_op_list = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user.user_id,
        UserPermissionOverride.effect == "grant"
    ).all()
    grant_codes = [op.permission_code for op in grant_op_list]

    # 3. 获取用户撤销权限
    revoke_op_list = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user.user_id,
        UserPermissionOverride.effect == "revoke"
    ).all()
    revoke_codes = [op.permission_code for op in revoke_op_list]

    # 合并并去重，移除撤销项
    full = list(set(base_perms + grant_codes))
    final = [p for p in full if p not in revoke_codes]
    return final

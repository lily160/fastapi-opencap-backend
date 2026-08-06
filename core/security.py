from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config.constants import CODE_UNAUTH
from config.settings import ACCESS_TOKEN_EXPIRE_SECONDS, ALGORITHM, REFRESH_TOKEN_DAYS, SECRET_KEY
from database.db import get_db
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User

# ===================== 基础密码工具 =====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# 全局唯一的鉴权 Scheme（确保 Swagger 统一加锁）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ===================== JWT 生成与解码 =====================
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


# ===================== 统一认证上下文、全局鉴权依赖 =====================
@dataclass(frozen=True)
class AuthContext:
    user: User
    token: str
    payload: dict


def get_auth_context(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db),
) -> AuthContext:
    """
    全局核心鉴权依赖。
    统一校验：Bearer Token提取 → JWT解析 → 黑名单(jti)校验 → 封禁校验 → 权限版本校验
    """
    credentials_exception = HTTPException(
        status_code=CODE_UNAUTH,
        detail="未登录或Token无效/已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 解析JWT载荷
        payload = decode_token(token)
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        jti: Optional[str] = payload.get("jti")

        if not user_id or token_type != "access" or not jti:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 黑名单校验：统一使用 jti 进行比对
    revoked = db.query(TokenBlacklist).filter(
        TokenBlacklist.jti == jti,
        TokenBlacklist.token_type == "access"
    ).first()

    if revoked:
        raise HTTPException(status_code=CODE_UNAUTH, detail="登录已失效，请重新登录")

    # 查询数据库用户信息
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise credentials_exception

    # 校验账号是否被封禁
    if user.is_active != 1:
        raise HTTPException(status_code=CODE_UNAUTH, detail="账号已被封禁，禁止登录")

    # 权限版本校验（角色/权限变更后旧Token强制失效）
    token_perm_version = payload.get("perm_version", 1)
    if token_perm_version < getattr(user, "permissions_version", 1):
        raise HTTPException(status_code=CODE_UNAUTH, detail="用户权限已变更，请重新登录")

    return AuthContext(user=user, token=token, payload=payload)


def get_current_user(auth_context: AuthContext = Depends(get_auth_context)) -> User:
    """
    简化版依赖。如果接口只需要 User 对象，可以直接依赖此函数。
    会自动继承 get_auth_context 的所有安全校验。
    """
    return auth_context.user


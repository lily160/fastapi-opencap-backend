from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from jose import JWTError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from config.constants import CODE_CREATE, CODE_NO_CONTENT, CODE_SUCCESS, UserRole
from config.settings import ACCESS_TOKEN_EXPIRE_SECONDS
from core.rbac_permission import AuthContext, get_auth_context
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    utc_now,
    verify_password,
    merge_user_permissions
)
from database.db import get_db
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User
from schemas.auth.auth_schema import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

router = APIRouter()


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def register_user(db: Session, payload: RegisterRequest) -> User:
    filters = [User.username == payload.username.strip()]
    if payload.email:
        filters.append(User.email == payload.email)
    if payload.phone:
        filters.append(User.phone == payload.phone.strip())

    existing = db.query(User).filter(or_(*filters)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username, email, or phone already exists")

    user = User(
        user_id=str(uuid4()),
        username=payload.username.strip(),
        password_hash=get_password_hash(payload.password),
        email=payload.email,
        phone=payload.phone.strip() if payload.phone else None,
        role=UserRole.USER.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is disabled")

    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_tokens(db: Session, user: User) -> TokenResponse:
    # ✅ 核心修复：直接调用你之前写好的、连接数据库的动态权限结算函数
    permissions = merge_user_permissions(db, user)

    access_token, _ = create_access_token(user.user_id, user.role, permissions)
    refresh_token, refresh_expires_at = create_refresh_token(user.user_id)

    db.add(
        TokenBlacklist(
            user_id=user.user_id,
            token_hash=token_hash(refresh_token),
            token_type="refresh",
            expires_at=refresh_expires_at.replace(tzinfo=None),
        )
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS,
        role=user.role,
        permissions=permissions,
    )


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    stored_token = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.token_hash == token_hash(refresh_token), TokenBlacklist.token_type == "refresh")
        .first()
    )
    if not stored_token or stored_token.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token revoked")
    if normalize_datetime(stored_token.expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token expired")

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is disabled")

    stored_token.revoked_at = datetime.utcnow()
    db.add(stored_token)
    db.commit()
    return issue_tokens(db, user)


def revoke_refresh_token(db: Session, refresh_token: str) -> None:
    stored_token = (
        db.query(TokenBlacklist)
        .filter(
            TokenBlacklist.token_hash == token_hash(refresh_token),
            TokenBlacklist.token_type == "refresh",
            TokenBlacklist.revoked_at.is_(None),
        )
        .first()
    )
    if stored_token:
        stored_token.revoked_at = datetime.utcnow()
        db.add(stored_token)
        db.commit()


def revoke_all_user_refresh_tokens(db: Session, user_id: str) -> None:
    tokens = (
        db.query(TokenBlacklist)
        .filter(
            TokenBlacklist.user_id == user_id,
            TokenBlacklist.token_type == "refresh",
            TokenBlacklist.revoked_at.is_(None),
        )
        .all()
    )
    for token in tokens:
        token.revoked_at = datetime.utcnow()
        db.add(token)
    db.commit()


def revoke_access_token(db: Session, user_id: str, payload: dict) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return

    existing = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
    if existing:
        return

    db.add(
        TokenBlacklist(
            user_id=user_id,
            jti=jti,
            token_type="access",
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None),
            revoked_at=datetime.utcnow(),
        )
    )
    db.commit()


@router.post("/register", response_model=RegisterResponse, status_code=CODE_CREATE)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    user = register_user(db, payload)
    return RegisterResponse(user_id=user.user_id, username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.username, payload.password)
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_access_token(db, payload.refresh_token)


@router.post("/logout", status_code=CODE_NO_CONTENT)
def logout(
    payload: RefreshRequest | None = None,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    if payload and payload.refresh_token:
        revoke_refresh_token(db, payload.refresh_token)
    else:
        revoke_all_user_refresh_tokens(db, auth_context.user.user_id)
    revoke_access_token(db, auth_context.user.user_id, auth_context.payload)
    return Response(status_code=CODE_NO_CONTENT)


@router.put("/password", status_code=CODE_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    user = auth_context.user
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="old password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="new password must be different")

    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    revoke_all_user_refresh_tokens(db, user.user_id)
    revoke_access_token(db, user.user_id, auth_context.payload)
    db.commit()
    return Response(status_code=CODE_NO_CONTENT)


@router.post("/forgot/lookup", status_code=CODE_SUCCESS)
def forgot_lookup():
    return {"msg": "forgot password lookup is not implemented yet"}


@router.post("/forgot/send-code", status_code=CODE_SUCCESS)
def forgot_send_code():
    return {"msg": "forgot password code sending is not implemented yet"}


@router.post("/forgot/reset", status_code=CODE_SUCCESS)
def forgot_reset():
    return {"msg": "forgot password reset is not implemented yet"}

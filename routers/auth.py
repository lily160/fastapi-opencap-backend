import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from jose import JWTError
from sqlalchemy import or_
from sqlalchemy.orm import Session

# --- 补充合并第二段所需的常量和配置导入 ---
from config.constants import (
    CODE_CREATE, CODE_NO_CONTENT, CODE_SUCCESS, UserRole,
    FORGOT_CONTACT_EMAIL, FORGOT_CONTACT_PHONE
)
from config.settings import (
    ACCESS_TOKEN_EXPIRE_SECONDS, FORGOT_CODE_EXPIRE, FORGOT_CODE_INTERVAL,
    FORGOT_LOOKUP_EXPIRE, FORGOT_MAX_RETRY, KAFKA_FORGOT_PASSWORD_TOPIC
)
from core.rbac_permission import AuthContext, get_auth_context
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    utc_now,
    verify_password,
    merge_user_permissions  # 保留了你第一段修复的核心函数
)
from database.db import get_db
from database.models.sys_forgot_password import ForgotPasswordSession # 新增找回密码会话表
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User
from kafka.producer import send_message # 新增 Kafka 发送
from schemas.auth.auth_schema import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    # 新增找回密码相关的 Schema
    ForgotLookupResponse,
    ForgotPasswordRequest,
    ForgotResetRequest,
    ForgotSendCodeRequest,
    ForgotSendCodeResponse,
    MaskedContact
)
from services.sms_service import sms_service # 新增短信服务

router = APIRouter()


# ================= 工具函数 =================
def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()

def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

# --- 以下为新增的找回密码辅助函数 ---
def code_hash(forgot_id: str, code: str) -> str:
    return sha256(f"{forgot_id}:{code}".encode("utf-8")).hexdigest()

def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    masked = f"{local[0]}***" if len(local) <= 2 and local else "***" if not local else f"{local[0]}***{local[-1]}"
    return f"{masked}@{domain}"

def mask_phone(phone: str) -> str:
    value = phone.strip()
    return "*" * len(value) if len(value) <= 4 else f"{value[:3]}****{value[-4:]}"

def user_forgot_contacts(user: User) -> list[MaskedContact]:
    contacts = []
    if user.email:
        contacts.append(MaskedContact(contact_type=FORGOT_CONTACT_EMAIL, masked_value=mask_email(user.email)))
    if user.phone:
        contacts.append(MaskedContact(contact_type=FORGOT_CONTACT_PHONE, masked_value=mask_phone(user.phone)))
    return contacts


# ================= 认证核心业务 (完全保留第一段逻辑) =================
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
    # ✅ 核心修复：直接调用你之前写好的、连接数据库的动态权限结算函数 (完全保留)
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


# ================= 找回密码业务 (第二段功能，转为同步查询) =================
def get_valid_forgot_session(db: Session, forgot_id: str) -> ForgotPasswordSession:
    session = db.get(ForgotPasswordSession, forgot_id)
    if not session or session.used_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="forgot password session not found")
    if normalize_datetime(session.lookup_expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="forgot password session expired")
    return session

def lookup(request: ForgotPasswordRequest, db: Session) -> ForgotLookupResponse:
    user = db.query(User).filter(User.username == request.username.strip()).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    contacts = user_forgot_contacts(user)
    if not contacts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user has no email or phone")

    forgot_session = ForgotPasswordSession(
        forgot_id=str(uuid4()), user_id=user.user_id,
        lookup_expires_at=(utc_now() + timedelta(seconds=FORGOT_LOOKUP_EXPIRE)).replace(tzinfo=None),
    )
    db.add(forgot_session)
    db.commit()

    return ForgotLookupResponse(
        forgot_id=forgot_session.forgot_id, username=user.username,
        masked_contacts=contacts, expire_seconds=FORGOT_LOOKUP_EXPIRE,
    )

def send_forgot_code(payload: ForgotSendCodeRequest, db: Session) -> ForgotSendCodeResponse:
    forgot_session = get_valid_forgot_session(db, payload.forgot_id)
    user = db.get(User, forgot_session.user_id)

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.contact_type not in {c.contact_type for c in user_forgot_contacts(user)}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact type is not available")

    if forgot_session.last_sent_at:
        elapsed = (utc_now() - normalize_datetime(forgot_session.last_sent_at)).total_seconds()
        if elapsed < FORGOT_CODE_INTERVAL:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"please retry after {int(FORGOT_CODE_INTERVAL - elapsed)} seconds")

    code = f"{secrets.randbelow(1_000_000):06d}"

    forgot_session.contact_type = payload.contact_type
    forgot_session.code_hash = code_hash(forgot_session.forgot_id, code)
    forgot_session.code_expires_at = (utc_now() + timedelta(seconds=FORGOT_CODE_EXPIRE)).replace(tzinfo=None)
    forgot_session.last_sent_at = datetime.utcnow()
    forgot_session.retry_count = 0

    if payload.contact_type == "email":
        # 注意：此处适配同步架构，去掉了 await
        send_message(
            topic=KAFKA_FORGOT_PASSWORD_TOPIC,
            data={
                "event": "forgot_password_code",
                "contact_type": payload.contact_type,
                "email": user.email,
                "phone": user.phone,
                "code": code,
                "username": user.username,
            }
        )
    elif payload.contact_type == "phone":
        try:
            # 注意：此处适配同步架构，去掉了 await
            sms_service.send_sms(user.phone, code)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.add(forgot_session)
    db.commit()
    return ForgotSendCodeResponse(expire_seconds=FORGOT_CODE_EXPIRE)

def reset_forgot_password(payload: ForgotResetRequest, db: Session) -> None:
    session = get_valid_forgot_session(db, payload.forgot_id)

    if not session.code_hash or not session.code_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code was not sent")

    if normalize_datetime(session.code_expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code expired")

    if session.retry_count >= FORGOT_MAX_RETRY:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many verification attempts")

    if session.code_hash != code_hash(session.forgot_id, payload.code.strip()):
        session.retry_count += 1
        db.add(session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="verification code is incorrect")

    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="new password must be different")

    user.password_hash = get_password_hash(payload.new_password)
    session.used_at = datetime.utcnow()

    db.add(user)
    db.add(session)
    # 复用上面已有的同步撤销函数，确保重置密码后踢掉所有登录设备
    revoke_all_user_refresh_tokens(db, user.user_id)  
    db.commit()


# ================= 路由端点 =================

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

# ================= 以下是将占位符替换为真实的同步实现 =================

@router.post("/forgot/lookup", response_model=ForgotLookupResponse, status_code=CODE_SUCCESS)
def forgot_lookup(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotLookupResponse:
    return lookup(payload, db)

@router.post("/forgot/send-code", response_model=ForgotSendCodeResponse, status_code=CODE_SUCCESS)
def forgot_send_code(payload: ForgotSendCodeRequest, db: Session = Depends(get_db)) -> ForgotSendCodeResponse:
    return send_forgot_code(payload, db)

@router.post("/forgot/reset", status_code=CODE_SUCCESS)
def forgot_reset(payload: ForgotResetRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    reset_forgot_password(payload, db)
    return {"message": "Password reset successfully"}
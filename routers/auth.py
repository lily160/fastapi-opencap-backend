import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, HTTPException, Response, status
from jose import JWTError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from config.constants import (
    CODE_CREATE, CODE_NO_CONTENT, CODE_SUCCESS, FORGOT_CONTACT_EMAIL,
    FORGOT_CONTACT_PHONE, UserRole,
)
from config.settings import (
    ACCESS_TOKEN_EXPIRE_SECONDS, FORGOT_CODE_EXPIRE, FORGOT_CODE_INTERVAL,
    FORGOT_LOOKUP_EXPIRE, FORGOT_MAX_RETRY, KAFKA_FORGOT_PASSWORD_TOPIC,
)
from core.security import AuthContext, get_auth_context
from core.rbac_permission import get_role_permissions
from core.security import (
    create_access_token, create_refresh_token, decode_token, get_password_hash,
    utc_now, verify_password,
)
from database.db import get_db
from database.models.sys_forgot_password import ForgotPasswordSession
from database.models.sys_token_blacklist import TokenBlacklist
from database.models.sys_user import User
from kafka.producer import send_message
from schemas.auth.auth_schema import (
    ForgotLookupResponse, ForgotPasswordRequest, ForgotResetRequest,
    ForgotSendCodeRequest, ForgotSendCodeResponse, LoginRequest, MaskedContact,
    PasswordChangeRequest, RefreshRequest, RegisterRequest, RegisterResponse,
    TokenResponse,
)
from services.sms_service import sms_service
router = APIRouter()


# 转换成hash值
def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


# 把任意 datetime 对象统一转换成 UTC 时区的时间。
def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def register_user(db: Session, payload: RegisterRequest) -> User:
    # 检查用户名、邮箱、手机号是否已存在
    filters = [User.username == payload.username.strip()]
    if payload.email:
        filters.append(User.email == payload.email)
    if payload.phone:
        filters.append(User.phone == payload.phone.strip())
    if db.query(User).filter(or_(*filters)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username, email, or phone already exists")
    #创建新用户
    user = User(
        user_id=str(uuid4()), username=payload.username.strip(),
        password_hash=get_password_hash(payload.password), email=payload.email,
        phone=payload.phone.strip() if payload.phone else None, role=UserRole.USER.value,
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
    return user


def issue_tokens(db: Session, user: User) -> TokenResponse:
    permissions = get_role_permissions(user.role)
    # 生成 Access Token
    # 第二个返回值（过期时间）当前不需要，因此使用 "_" 忽略
    access_token, _ = create_access_token(user.user_id, user.role, permissions)
    # 生成 Refresh Token，并获取过期时间
    refresh_token, refresh_expires_at = create_refresh_token(user.user_id)
    # 将 Refresh Token 的哈希值保存到数据库
    # 不直接保存原始 Token，提高安全性
    db.add(TokenBlacklist(
        user_id=user.user_id, token_hash=token_hash(refresh_token), token_type="refresh",
        expires_at=refresh_expires_at.replace(tzinfo=None),
    ))
    db.commit()
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS, role=user.role, permissions=permissions,
    )


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    # 解析并验证 JWT
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token") from exc
    # 验证 refresh token 的类型，防止使用access刷新
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")
    # 查询数据库中保存的 Refresh Token
    stored_token = (
        db.query(TokenBlacklist)
        .filter(
            TokenBlacklist.token_hash == token_hash(refresh_token),
            TokenBlacklist.token_type == "refresh",
        )
        .first()
    )
    # Token 不存在或已被撤销
    if not stored_token or stored_token.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token revoked")
    # 判断是否已经过期
    if normalize_datetime(stored_token.expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token expired")
    user = db.get(User, payload.get("sub"))
    # 用户不存在或账号已被禁用
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is disabled")
    # 当前 Refresh Token 设置为已撤销（一次性使用）
    stored_token.revoked_at = datetime.utcnow()
    db.commit()
    return issue_tokens(db, user)


# 退出登录时标记token为失效
def revoke_refresh_token(db: Session, refresh_token: str) -> None:
    # 查询数据库中仍然有效的 Refresh Token
    stored_token = (
        db.query(TokenBlacklist)
        .filter(
            TokenBlacklist.token_hash == token_hash(refresh_token),
            TokenBlacklist.token_type == "refresh",
            TokenBlacklist.revoked_at.is_(None),
        )
        .first()
    )
    # 如果 Token 存在，则标记为已撤销
    if stored_token:
        stored_token.revoked_at = datetime.utcnow()
        db.commit()


# 让某个用户的所有 Refresh Token 全部失效。
def revoke_all_user_refresh_tokens(db: Session, user_id: str) -> None:
    # 查询该用户所有未撤销的 Refresh Token
    tokens = (
        db.query(TokenBlacklist)
        .filter(
            TokenBlacklist.user_id == user_id,
            TokenBlacklist.token_type == "refresh",
            TokenBlacklist.revoked_at.is_(None),
        )
        .all()
    )
    # 将所有 Token 标记为已撤销
    for token in tokens:
        token.revoked_at = datetime.utcnow()
    db.commit()


# 把当前 Access Token 加入黑名单，以后即使 Token 没过期，也不能再使用。
def revoke_access_token(db: Session, user_id: str, payload: dict) -> None:
    # 获取 JWT 唯一标识（jti）和过期时间（exp）
    jti, exp = payload.get("jti"), payload.get("exp")
    # 缺少必要字段，无法加入黑名单
    if not jti or not exp:
        return
    # 判断该 Access Token 是否已经在黑名单中
    if db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first():
        return
    # 将 Access Token 加入黑名单
    db.add(TokenBlacklist(
        user_id=user_id, jti=jti, token_type="access",
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None),
        revoked_at=datetime.utcnow(),
    ))
    db.commit()


# 对找回密码进行hash加密
def code_hash(forgot_id: str, code: str) -> str:
    return sha256(f"{forgot_id}:{code}".encode("utf-8")).hexdigest()


# 邮箱脱敏
def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    masked = f"{local[0]}***" if len(local) <= 2 and local else "***" if not local else f"{local[0]}***{local[-1]}"
    return f"{masked}@{domain}"


# 手机号脱敏
def mask_phone(phone: str) -> str:
    value = phone.strip()
    return "*" * len(value) if len(value) <= 4 else f"{value[:3]}****{value[-4:]}"


# 根据用户绑定的邮箱和手机号，生成一个"脱敏联系方式列表"，返回给前端。
def user_forgot_contacts(user: User) -> list[MaskedContact]:
    contacts = []
    if user.email:
        contacts.append(MaskedContact(contact_type=FORGOT_CONTACT_EMAIL, masked_value=mask_email(user.email)))
    if user.phone:
        contacts.append(MaskedContact(contact_type=FORGOT_CONTACT_PHONE, masked_value=mask_phone(user.phone)))
    return contacts


def get_valid_forgot_session(db: Session, forgot_id: str) -> ForgotPasswordSession:
    # 根据 forgot_id 查询找回密码会话
    session = db.get(ForgotPasswordSession, forgot_id)
    # 会话不存在或已被使用
    if not session or session.used_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="forgot password session not found")
    # 会话已过期
    if normalize_datetime(session.lookup_expires_at) < utc_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="forgot password session expired")
    return session


def lookup(request: ForgotPasswordRequest, db: Session) -> ForgotLookupResponse:
    user = db.query(User).filter(User.username == request.username.strip()).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # 获取脱敏后的联系方式（邮箱、手机号）
    contacts = user_forgot_contacts(user)
    # 用户没有绑定任何找回方式
    if not contacts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user has no email or phone")
    # 创建找回密码会话
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
    # 获取有效的找回密码会话
    forgot_session = get_valid_forgot_session(db, payload.forgot_id)
    # 查询用户
    user = db.get(User, forgot_session.user_id)
    # 用户不存在或已禁用
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    # 校验用户是否绑定了所选择的联系方式
    if payload.contact_type not in {
        c.contact_type for c in user_forgot_contacts(user)
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="contact type is not available"
        )
    # 判断是否发送过验证码，限制发送频率
    if forgot_session.last_sent_at:
        elapsed = (
                utc_now() - normalize_datetime(forgot_session.last_sent_at)
        ).total_seconds()

        if elapsed < FORGOT_CODE_INTERVAL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"please retry after {int(FORGOT_CODE_INTERVAL - elapsed)} seconds"
            )
    # 生成 6 位随机验证码
    code = f"{secrets.randbelow(1_000_000):06d}"
    # 保存验证码信息
    forgot_session.contact_type = payload.contact_type
    forgot_session.code_hash = code_hash(
        forgot_session.forgot_id,
        code
    )
    forgot_session.code_expires_at = (
            utc_now() + timedelta(seconds=FORGOT_CODE_EXPIRE)
    ).replace(tzinfo=None)
    forgot_session.last_sent_at = datetime.utcnow()
    forgot_session.retry_count = 0

    # 邮箱发送验证码（通过 Kafka）
    if payload.contact_type == "email":
        anyio.from_thread.run(
            send_message,
            KAFKA_FORGOT_PASSWORD_TOPIC,
            {
                "event": "forgot_password_code",
                "contact_type": payload.contact_type,
                "email": user.email,
                "phone": user.phone,
                "code": code,
                "username": user.username,
            }
        )

    # 短信发送验证码
    elif payload.contact_type == "phone":
        try:
            anyio.from_thread.run(
                sms_service.send_sms,
                user.phone,
                code,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    # 保存验证码信息
    db.commit()

    # 返回验证码有效时间
    return ForgotSendCodeResponse(
        expire_seconds=FORGOT_CODE_EXPIRE
    )


def reset_forgot_password(payload: ForgotResetRequest, db: Session) -> None:
    # 获取有效的找回密码会话
    session = get_valid_forgot_session(
        db,
        payload.forgot_id
    )
    # 检查验证码是否已经发送
    if not session.code_hash or not session.code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="verification code was not sent"
        )
    # 检查验证码是否过期
    if normalize_datetime(session.code_expires_at) < utc_now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="verification code expired"
        )
    # 检查验证码错误次数是否超过限制
    if session.retry_count >= FORGOT_MAX_RETRY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many verification attempts"
        )
    # 校验用户输入验证码
    # 将用户输入验证码重新 hash，与数据库保存的 hash 比较
    if session.code_hash != code_hash(
            session.forgot_id,
            payload.code.strip()
    ):
        # 验证失败，增加错误次数
        session.retry_count += 1
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="verification code is incorrect"
        )
    # 根据 session 查询用户
    user = db.get(
        User,
        session.user_id
    )
    # 用户不存在或已禁用
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    # 检查新密码是否和旧密码一样
    if verify_password(
            payload.new_password,
            user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new password must be different"
        )
    # 更新密码
    user.password_hash = get_password_hash(
        payload.new_password
    )
    # 标记该找回密码流程已经完成
    session.used_at = datetime.utcnow()
    # 让用户之前所有登录设备退出
    revoke_all_user_refresh_tokens(
        db,
        user.user_id
    )
    db.commit()


@router.post("/register", response_model=RegisterResponse, status_code=CODE_CREATE)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    user = register_user(db, payload)
    return RegisterResponse(user_id=user.user_id, username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return issue_tokens(db, authenticate_user(db, payload.username, payload.password))


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_access_token(db, payload.refresh_token)


@router.post("/logout", status_code=CODE_NO_CONTENT)
def logout(payload: RefreshRequest | None = None, auth_context: AuthContext = Depends(get_auth_context),
           db: Session = Depends(get_db)) -> Response:
    if payload and payload.refresh_token:
        revoke_refresh_token(db, payload.refresh_token)
    else:
        revoke_all_user_refresh_tokens(db, auth_context.user.user_id)
    revoke_access_token(db, auth_context.user.user_id, auth_context.payload)
    return Response(status_code=CODE_NO_CONTENT)


@router.put("/password", status_code=CODE_NO_CONTENT)
def change_password(payload: PasswordChangeRequest, auth_context: AuthContext = Depends(get_auth_context),
                    db: Session = Depends(get_db)) -> Response:
    user = auth_context.user
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="old password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="new password must be different")
    user.password_hash = get_password_hash(payload.new_password)
    revoke_all_user_refresh_tokens(db, user.user_id)
    revoke_access_token(db, user.user_id, auth_context.payload)
    db.commit()
    return Response(status_code=CODE_NO_CONTENT)


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

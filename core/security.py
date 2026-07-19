from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt
from passlib.context import CryptContext

from config.settings import ACCESS_TOKEN_EXPIRE_SECONDS, ALGORITHM, REFRESH_TOKEN_DAYS, SECRET_KEY

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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

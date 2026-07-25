from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=32)
    confirm_password: str = Field(min_length=8, max_length=32)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value: str, info) -> str:
        if value != info.data.get("password"):
            raise ValueError("confirm_password must match password")
        return value

    @field_validator("password")
    @classmethod
    def password_bytes_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password cannot be longer than 72 bytes")
        return value


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    message: str = "User registered successfully"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    permissions: list[str]


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=32)
    confirm_password: str = Field(min_length=8, max_length=32)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value: str, info) -> str:
        if value != info.data.get("new_password"):
            raise ValueError("confirm_password must match new_password")
        return value

    @field_validator("new_password")
    @classmethod
    def password_bytes_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("new_password cannot be longer than 72 bytes")
        return value

class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=4, max_length=32)


class MaskedContact(BaseModel):
    contact_type: str
    masked_value: str


class ForgotLookupResponse(BaseModel):
    forgot_id: str
    username: str
    masked_contacts: list[MaskedContact]
    expire_seconds: int


class ForgotSendCodeRequest(BaseModel):
    forgot_id: str
    contact_type: str


class ForgotSendCodeResponse(BaseModel):
    message: str = "Verification code sent successfully"
    expire_seconds: int
    debug_code: str | None = None


class ForgotResetRequest(BaseModel):
    forgot_id: str
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=32)
    confirm_password: str = Field(min_length=8, max_length=32)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value: str, info) -> str:
        if value != info.data.get("new_password"):
            raise ValueError("confirm_password must match new_password")
        return value

    @field_validator("new_password")
    @classmethod
    def password_bytes_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("new_password cannot be longer than 72 bytes")
        return value


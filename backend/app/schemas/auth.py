from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=4, max_length=128)


class AuthUserRead(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    is_active: bool
    mfa_enabled: bool = False
    mfa_required: bool = False

    model_config = {"from_attributes": True}


class MfaSetupRead(BaseModel):
    secret: str
    provisioning_uri: str
    issuer: str
    account_name: str


class LoginResponse(BaseModel):
    status: Literal["authenticated", "mfa_required", "mfa_setup_required"]
    token: str | None = None
    trusted_device_token: str | None = None
    expires_at: datetime | None = None
    trusted_device_expires_at: datetime | None = None
    pending_token: str | None = None
    user: AuthUserRead
    mfa_setup: MfaSetupRead | None = None


class MfaVerifyRequest(BaseModel):
    pending_token: str = Field(min_length=20, max_length=4000)
    code: str = Field(min_length=6, max_length=12)
    remember_device: bool = False


class MfaEnrollConfirmRequest(BaseModel):
    pending_token: str | None = Field(default=None, min_length=20, max_length=4000)
    code: str = Field(min_length=6, max_length=12)
    remember_device: bool = False


class MfaStatusRead(BaseModel):
    enabled: bool
    required: bool
    setup_pending: bool
    issuer: str
    mode: str


class MfaResetRequest(BaseModel):
    user_id: str


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="operador", max_length=50)


class UserCredentialsUpdate(BaseModel):
    email: str = Field(min_length=5, max_length=150)
    password: str | None = Field(default=None, min_length=6, max_length=128)

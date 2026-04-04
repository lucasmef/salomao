from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, IdMixin, TimestampMixin


class Company(Base, IdMixin, TimestampMixin):
    __tablename__ = "companies"

    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str] = mapped_column(String(200))
    document: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(3), default="BRL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    linx_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linx_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    linx_password_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    linx_sales_view_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    linx_receivables_view_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    users = relationship("User", back_populates="company")


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="users")
    trusted_devices = relationship("MfaTrustedDevice", back_populates="user")


class AuthSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user = relationship("User")


class MfaTrustedDevice(Base, IdMixin, TimestampMixin):
    __tablename__ = "mfa_trusted_devices"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user = relationship("User", back_populates="trusted_devices")

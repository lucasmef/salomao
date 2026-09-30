from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class EmailSettings(Base, TimestampMixin):
    __tablename__ = "system_email_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_system_email_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    encryption: Mapped[str] = mapped_column(String(20))
    username: Mapped[str] = mapped_column(String(255))
    sender: Mapped[str] = mapped_column(String(255))
    recipients: Mapped[str] = mapped_column(Text, default="")
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

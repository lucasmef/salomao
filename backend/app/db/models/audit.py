from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, IdMixin, TimestampMixin


class AuditLog(Base, IdMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_name: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)

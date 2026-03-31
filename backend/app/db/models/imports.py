from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, IdMixin, TimestampMixin


class ImportBatch(Base, IdMixin, TimestampMixin):
    __tablename__ = "import_batches"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    fingerprint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    records_total: Mapped[int] = mapped_column(Integer, default=0)
    records_valid: Mapped[int] = mapped_column(Integer, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

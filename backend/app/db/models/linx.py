from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, IdMixin, TimestampMixin


class SalesSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "sales_snapshots"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    gross_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cash_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    check_sight_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    check_term_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    inhouse_credit_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    card_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    convenio_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    pix_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    financing_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    markup: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    discount_or_surcharge: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class ReceivableTitle(Base, IdMixin, TimestampMixin):
    __tablename__ = "receivable_titles"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    company_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    installment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_with_interest: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(200))
    document_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    seller_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

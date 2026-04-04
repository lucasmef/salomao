from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class PurchasePayableTitle(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_payable_titles"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    last_seen_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(120), index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    payable_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    company_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    installment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    installment_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installments_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_with_charges: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    supplier_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    document_series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    purchase_invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_invoices.id"),
        nullable=True,
        index=True,
    )
    purchase_installment_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_installments.id"),
        nullable=True,
        index=True,
    )
    financial_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_entries.id"),
        nullable=True,
        index=True,
    )

    purchase_invoice = relationship("PurchaseInvoice", foreign_keys=[purchase_invoice_id])
    purchase_installment = relationship("PurchaseInstallment", foreign_keys=[purchase_installment_id])
    financial_entry = relationship("FinancialEntry", foreign_keys=[financial_entry_id])

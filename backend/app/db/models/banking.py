from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Float, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, IdMixin, TimestampMixin


class BankTransaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("account_id", "fit_id", name="uq_bank_transaction_fitid"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    posted_at: Mapped[date] = mapped_column(Date, index=True)
    trn_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fit_id: Mapped[str] = mapped_column(String(80))
    check_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    account = relationship("Account")


class Reconciliation(Base, IdMixin, TimestampMixin):
    __tablename__ = "reconciliations"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    bank_transaction_id: Mapped[str] = mapped_column(
        ForeignKey("bank_transactions.id"),
        unique=True,
        index=True,
    )
    financial_entry_id: Mapped[str] = mapped_column(
        ForeignKey("financial_entries.id"),
        index=True,
    )
    match_type: Mapped[str] = mapped_column(String(20), default="manual")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    bank_transaction = relationship("BankTransaction")
    financial_entry = relationship("FinancialEntry")


class ReconciliationRule(Base, IdMixin, TimestampMixin):
    __tablename__ = "reconciliation_rules"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    pattern: Mapped[str] = mapped_column(String(180))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), default="suggest")
    counterparty_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category = relationship("Category")
    account = relationship("Account")


class ReconciliationGroup(Base, IdMixin, TimestampMixin):
    __tablename__ = "reconciliation_groups"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    match_type: Mapped[str] = mapped_column(String(20), default="manual")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    reconciliation_lines = relationship("ReconciliationLine", back_populates="reconciliation_group")


class ReconciliationLine(Base, IdMixin, TimestampMixin):
    __tablename__ = "reconciliation_lines"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    reconciliation_group_id: Mapped[str] = mapped_column(
        ForeignKey("reconciliation_groups.id"),
        index=True,
    )
    bank_transaction_id: Mapped[str] = mapped_column(ForeignKey("bank_transactions.id"), index=True)
    financial_entry_id: Mapped[str] = mapped_column(ForeignKey("financial_entries.id"), index=True)
    amount_applied: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    reconciliation_group = relationship("ReconciliationGroup", back_populates="reconciliation_lines")
    bank_transaction = relationship("BankTransaction")
    financial_entry = relationship("FinancialEntry")

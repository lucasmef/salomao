from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, IdMixin, TimestampMixin


class Account(Base, IdMixin, TimestampMixin):
    __tablename__ = "accounts"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(40))
    bank_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    branch_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    import_ofx_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Category(Base, IdMixin, TimestampMixin):
    __tablename__ = "categories"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    entry_kind: Mapped[str] = mapped_column(String(20), default="expense")
    report_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    report_subgroup: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_financial_expense: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RecurrenceRule(Base, IdMixin, TimestampMixin):
    __tablename__ = "recurrence_rules"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    entry_type: Mapped[str] = mapped_column(String(40))
    frequency: Mapped[str] = mapped_column(String(20))
    interval_value: Mapped[int] = mapped_column(default=1)
    day_of_month: Mapped[int | None] = mapped_column(nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_run_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    title_template: Mapped[str | None] = mapped_column(String(160), nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    interest_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FinancialEntry(Base, IdMixin, TimestampMixin):
    __tablename__ = "financial_entries"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )
    interest_category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True,
    )
    recurrence_rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("recurrence_rules.id"),
        nullable=True,
    )
    transfer_id: Mapped[str | None] = mapped_column(
        ForeignKey("transfers.id"),
        nullable=True,
        index=True,
    )
    loan_installment_id: Mapped[str | None] = mapped_column(
        ForeignKey("loan_installments.id"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable=True,
        index=True,
    )
    collection_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_seasons.id"),
        nullable=True,
        index=True,
    )
    season_phase: Mapped[str] = mapped_column(String(20), default="main")
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
    entry_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    competence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    external_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_recurring_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    account = relationship("Account")
    category = relationship("Category", foreign_keys=[category_id])
    interest_category = relationship("Category", foreign_keys=[interest_category_id])
    transfer = relationship("Transfer", foreign_keys=[transfer_id])
    recurrence_rule = relationship("RecurrenceRule")
    supplier = relationship("Supplier")
    collection = relationship("CollectionSeason")
    purchase_invoice = relationship("PurchaseInvoice", foreign_keys=[purchase_invoice_id])
    purchase_installment = relationship("PurchaseInstallment", foreign_keys=[purchase_installment_id])


class Transfer(Base, IdMixin, TimestampMixin):
    __tablename__ = "transfers"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    destination_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    transfer_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_entries.id"),
        nullable=True,
    )
    destination_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_entries.id"),
        nullable=True,
    )

    source_account = relationship("Account", foreign_keys=[source_account_id])
    destination_account = relationship("Account", foreign_keys=[destination_account_id])


class LoanContract(Base, IdMixin, TimestampMixin):
    __tablename__ = "loan_contracts"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    interest_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    lender_name: Mapped[str] = mapped_column(String(180))
    contract_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    first_due_date: Mapped[date] = mapped_column(Date)
    installments_count: Mapped[int] = mapped_column(Integer)
    principal_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    interest_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    installment_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    account = relationship("Account")
    category = relationship("Category", foreign_keys=[category_id])
    interest_category = relationship("Category", foreign_keys=[interest_category_id])
    installments = relationship(
        "LoanInstallment",
        order_by="LoanInstallment.installment_number",
        back_populates="contract",
    )


class LoanInstallment(Base, IdMixin, TimestampMixin):
    __tablename__ = "loan_installments"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("loan_contracts.id"), index=True)
    installment_number: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    financial_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_entries.id"),
        nullable=True,
        index=True,
    )

    contract = relationship("LoanContract", back_populates="installments")
    financial_entry = relationship("FinancialEntry", foreign_keys=[financial_entry_id])

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, IdMixin, TimestampMixin


class Supplier(Base, IdMixin, TimestampMixin):
    __tablename__ = "suppliers"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    document_number: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    default_payment_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_basis: Mapped[str] = mapped_column(String(20), default="delivery")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_purchase_invoices: Mapped[bool] = mapped_column(Boolean, default=False)
    ignore_in_purchase_planning: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseBrand(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_brands"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    default_payment_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseBrandSupplier(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_brand_suppliers"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("purchase_brands.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)

    brand = relationship("PurchaseBrand")
    supplier = relationship("Supplier")


class PurchasePlanSupplier(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_plan_suppliers"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("purchase_plans.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)

    plan = relationship("PurchasePlan", back_populates="plan_suppliers")
    supplier = relationship("Supplier")


class CollectionSeason(Base, IdMixin, TimestampMixin):
    __tablename__ = "collection_seasons"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    season_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    season_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchasePlan(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_plans"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_brands.id"), nullable=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collection_seasons.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    purchased_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payment_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_basis: Mapped[str] = mapped_column(String(20), default="delivery")
    season_phase: Mapped[str] = mapped_column(String(20), default="main")
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand = relationship("PurchaseBrand")
    supplier = relationship("Supplier")
    collection = relationship("CollectionSeason")
    plan_suppliers = relationship(
        "PurchasePlanSupplier",
        order_by="PurchasePlanSupplier.created_at",
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class PurchaseInvoice(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_invoices"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_brands.id"), nullable=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collection_seasons.id"), nullable=True, index=True)
    purchase_plan_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_plans.id"), nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nfe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payment_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payment_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_basis: Mapped[str] = mapped_column(String(20), default="delivery")
    season_phase: Mapped[str] = mapped_column(String(20), default="main")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="text")
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand = relationship("PurchaseBrand")
    supplier = relationship("Supplier")
    collection = relationship("CollectionSeason")
    purchase_plan = relationship("PurchasePlan")
    installments = relationship(
        "PurchaseInstallment",
        order_by="PurchaseInstallment.installment_number",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class PurchaseInstallment(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_installments"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    purchase_invoice_id: Mapped[str] = mapped_column(ForeignKey("purchase_invoices.id"), index=True)
    installment_number: Mapped[int] = mapped_column(index=True)
    installment_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    financial_entry_id: Mapped[str | None] = mapped_column(ForeignKey("financial_entries.id"), nullable=True, index=True)

    invoice = relationship("PurchaseInvoice", back_populates="installments")
    financial_entry = relationship("FinancialEntry", foreign_keys=[financial_entry_id])


class PurchaseDelivery(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_deliveries"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_brands.id"), nullable=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collection_seasons.id"), nullable=True, index=True)
    purchase_plan_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_plans.id"), nullable=True, index=True)
    purchase_invoice_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_invoices.id"), nullable=True, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    season_phase: Mapped[str] = mapped_column(String(20), default="main")
    source_type: Mapped[str] = mapped_column(String(20), default="invoice")
    source_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand = relationship("PurchaseBrand")
    supplier = relationship("Supplier")
    collection = relationship("CollectionSeason")
    purchase_plan = relationship("PurchasePlan")
    purchase_invoice = relationship("PurchaseInvoice")


class PurchaseReturn(Base, IdMixin, TimestampMixin):
    __tablename__ = "purchase_returns"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)
    return_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    invoice_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="request_open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_entry_id: Mapped[str | None] = mapped_column(ForeignKey("financial_entries.id"), nullable=True, index=True)

    supplier = relationship("Supplier")
    refund_entry = relationship("FinancialEntry")

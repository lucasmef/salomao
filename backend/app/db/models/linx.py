from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
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
    linx_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
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


class LinxCustomer(Base, IdMixin, TimestampMixin):
    __tablename__ = "linx_customers"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    last_seen_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    portal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    linx_code: Mapped[int] = mapped_column(Integer, index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    person_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    registration_type: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    address_street: Mapped[str | None] = mapped_column(String(250), nullable=True)
    address_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_complement: Mapped[str | None] = mapped_column(String(160), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone_primary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    municipal_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    loyalty_card_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    convenio_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    anonymous_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_limit_inhouse: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    credit_limit_cash_card: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    class_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_code_ws: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linx_created_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    linx_updated_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    linx_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class LinxProduct(Base, IdMixin, TimestampMixin):
    __tablename__ = "linx_products"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    last_seen_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    portal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    linx_code: Mapped[int] = mapped_column(BigInteger, index=True)
    barcode: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(250))
    reference: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sector_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    supplier_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    collection_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    collection_name_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    collection_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ncm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cest: Mapped[str | None] = mapped_column(String(10), nullable=True)
    auxiliary_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    price_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    price_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    stock_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    detail_company_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_location: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linx_created_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    linx_updated_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    linx_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    linx_detail_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class LinxOpenReceivable(Base, IdMixin, TimestampMixin):
    __tablename__ = "linx_open_receivables"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    last_seen_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    portal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    company_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    linx_code: Mapped[int] = mapped_column(BigInteger, index=True)
    customer_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(200))
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    interest_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    document_series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    installment_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identifier: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    payment_method_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payment_plan_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    linx_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class LinxMovement(Base, IdMixin, TimestampMixin):
    __tablename__ = "linx_movements"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    last_seen_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    portal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    company_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    linx_transaction: Mapped[int] = mapped_column(BigInteger, index=True)
    document_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    document_series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    identifier: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    movement_group: Mapped[str] = mapped_column(String(20), index=True)
    movement_type: Mapped[str] = mapped_column(String(30), index=True)
    operation_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    transaction_type_code: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    nature_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    nature_description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cfop_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cfop_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    launch_date: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    linx_updated_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    customer_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    seller_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_code: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    product_barcode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    item_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    line_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    linx_row_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

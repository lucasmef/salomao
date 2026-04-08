from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, IdMixin, TimestampMixin


class BoletoCustomerConfig(Base, IdMixin, TimestampMixin):
    __tablename__ = "boleto_customer_configs"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    client_key: Mapped[str] = mapped_column(String(200), index=True)
    client_name: Mapped[str] = mapped_column(String(200))
    client_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    uses_boleto: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(20), default="individual")
    boleto_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    include_interest: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_complement: Mapped[str | None] = mapped_column(String(160), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_primary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_secondary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)


class BoletoRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "boleto_records"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    bank: Mapped[str] = mapped_column(String(20), index=True)
    client_key: Mapped[str] = mapped_column(String(200), index=True)
    client_name: Mapped[str] = mapped_column(String(200))
    document_id: Mapped[str] = mapped_column(String(80), index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(60), default="")
    barcode: Mapped[str | None] = mapped_column(String(160), nullable=True)
    inter_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    inter_codigo_solicitacao: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    inter_seu_numero: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    inter_nosso_numero: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linha_digitavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pix_copia_e_cola: Mapped[str | None] = mapped_column(Text, nullable=True)
    inter_txid: Mapped[str | None] = mapped_column(String(120), nullable=True)


class StandaloneBoletoRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "standalone_boleto_records"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    bank: Mapped[str] = mapped_column(String(20), default="INTER", index=True)
    client_key: Mapped[str] = mapped_column(String(200), index=True)
    client_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    document_id: Mapped[str] = mapped_column(String(80), index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(60), default="")
    local_status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(160), nullable=True)
    inter_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    inter_codigo_solicitacao: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    inter_seu_numero: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    inter_nosso_numero: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linha_digitavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pix_copia_e_cola: Mapped[str | None] = mapped_column(Text, nullable=True)
    inter_txid: Mapped[str | None] = mapped_column(String(120), nullable=True)

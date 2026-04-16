from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class BoletoClientConfigPayload(BaseModel):
    client_key: str = Field(min_length=1, max_length=200)
    uses_boleto: bool = False
    mode: str = Field(default="individual", max_length=20)
    boleto_due_day: int | None = Field(default=None, ge=1, le=31)
    include_interest: bool = False
    notes: str | None = None


class BoletoClientConfigBulkUpdate(BaseModel):
    clients: list[BoletoClientConfigPayload]


class BoletoMissingExportRequest(BaseModel):
    selection_keys: list[str] = Field(default_factory=list)


class BoletoPdfBatchRequest(BaseModel):
    boleto_ids: list[str] = Field(default_factory=list)


class BoletoInterCancelRequest(BaseModel):
    motivo_cancelamento: str = Field(default="Cancelado pelo ERP", min_length=3, max_length=50)


class BoletoInterReceiveRequest(BaseModel):
    pagar_com: str = Field(default="BOLETO", pattern="^(BOLETO|PIX)$")


class StandaloneBoletoCreateRequest(BaseModel):
    account_id: str | None = Field(default=None, min_length=1)
    client_name: str = Field(min_length=3, max_length=200)
    amount: Decimal = Field(gt=0)
    due_date: date
    notes: str | None = None


class StandaloneBoletoStatusRequest(BaseModel):
    local_status: str = Field(pattern="^(open|downloaded)$")


class BoletoFileRead(BaseModel):
    source_type: str
    name: str
    updated_at: str


class BoletoSummaryRead(BaseModel):
    receivable_count: int
    receivable_total: Decimal
    boleto_count: int
    overdue_boleto_count: int
    overdue_invoice_client_count: int
    paid_pending_count: int
    missing_boleto_count: int
    excess_boleto_count: int
    boleto_clients_count: int


class BoletoClientRead(BaseModel):
    client_key: str
    client_name: str
    client_code: str | None = None
    uses_boleto: bool
    mode: str
    boleto_due_day: int | None = None
    include_interest: bool = False
    notes: str | None = None
    auto_uses_boleto: bool = False
    receivable_count: int
    overdue_boleto_count: int
    total_amount: Decimal
    matched_paid_count: int
    address_street: str | None = None
    address_number: str | None = None
    address_complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    tax_id: str | None = None
    state_registration: str | None = None
    phone_primary: str | None = None
    phone_secondary: str | None = None
    mobile: str | None = None


class BoletoReceivableRead(BaseModel):
    client_name: str
    client_code: str | None = None
    invoice_number: str
    installment: str
    issue_date: date | None = None
    due_date: date | None = None
    amount: Decimal
    corrected_amount: Decimal
    document: str
    status: str
    status_bucket: str = "open"


class BoletoRecordRead(BaseModel):
    id: str
    bank: str
    client_name: str
    document_id: str
    issue_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    amount: Decimal
    paid_amount: Decimal
    status: str
    status_bucket: str = "open"
    barcode: str | None = None
    linha_digitavel: str | None = None
    pix_copia_e_cola: str | None = None
    inter_codigo_solicitacao: str | None = None
    inter_account_id: str | None = None
    pdf_available: bool = False


class StandaloneBoletoRead(BaseModel):
    id: str
    bank: str
    client_name: str
    document_id: str
    issue_date: date | None = None
    due_date: date | None = None
    amount: Decimal
    paid_amount: Decimal
    status: str
    status_bucket: str = "open"
    local_status: str
    description: str | None = None
    notes: str | None = None
    tax_id: str | None = None
    email: str | None = None
    barcode: str | None = None
    linha_digitavel: str | None = None
    pix_copia_e_cola: str | None = None
    inter_codigo_solicitacao: str | None = None
    inter_account_id: str | None = None
    pdf_available: bool = False
    downloaded_at: str | None = None


class BoletoMatchItem(BaseModel):
    selection_key: str
    client_key: str
    type: str
    client_name: str
    mode: str | None = None
    due_date: date | None = None
    days_overdue: int = 0
    status: str
    amount: Decimal
    reason: str
    receivable_count: int
    bank: str | None = None
    competence: str | None = None
    receivables: list[BoletoReceivableRead] = []
    boletos: list[BoletoRecordRead] = []


class BoletoOverdueInvoiceSummaryRead(BaseModel):
    client_name: str
    invoice_count: int
    days_overdue: int
    overdue_amount: Decimal
    oldest_due_date: date | None = None


class BoletoDashboardRead(BaseModel):
    generated_at: str
    files: list[BoletoFileRead]
    summary: BoletoSummaryRead
    clients: list[BoletoClientRead]
    receivables: list[BoletoReceivableRead]
    invoice_items: list[BoletoReceivableRead] = []
    open_boletos: list[BoletoRecordRead]
    all_boletos: list[BoletoRecordRead] = []
    overdue_boletos: list[BoletoMatchItem]
    overdue_invoices: list[BoletoOverdueInvoiceSummaryRead]
    paid_pending: list[BoletoMatchItem]
    missing_boletos: list[BoletoMatchItem]
    excess_boletos: list[BoletoMatchItem]
    standalone_boletos: list[StandaloneBoletoRead] = []

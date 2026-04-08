from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


SeasonType = Literal["summer", "winter"]
SeasonPhase = Literal["main", "high"]


class SupplierBase(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    default_payment_term: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    ignore_in_purchase_planning: bool = False
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(SupplierBase):
    pass


class SupplierRead(SupplierBase):
    id: str
    has_purchase_invoices: bool = False

    model_config = {"from_attributes": True}


class PurchaseBrandBase(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    supplier_ids: list[str] = Field(default_factory=list)
    default_payment_term: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    is_active: bool = True


class PurchaseBrandCreate(PurchaseBrandBase):
    pass


class PurchaseBrandUpdate(PurchaseBrandBase):
    pass


class PurchaseBrandRead(PurchaseBrandBase):
    id: str
    suppliers: list[SupplierRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CollectionSeasonBase(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    season_year: int = Field(ge=2000, le=2100)
    season_type: SeasonType
    start_date: date
    end_date: date
    notes: str | None = None
    is_active: bool = True


class CollectionSeasonCreate(CollectionSeasonBase):
    pass


class CollectionSeasonUpdate(CollectionSeasonBase):
    pass


class CollectionSeasonRead(CollectionSeasonBase):
    id: str
    season_label: str

    model_config = {"from_attributes": True}


class PurchaseInstallmentDraft(BaseModel):
    installment_number: int = Field(ge=1)
    installment_label: str | None = Field(default=None, max_length=40)
    due_date: date | None = None
    amount: Decimal


class PurchaseInvoiceDraft(BaseModel):
    brand_id: str | None = None
    supplier_id: str | None = None
    supplier_name: str = Field(min_length=2, max_length=180)
    collection_id: str | None = None
    season_phase: SeasonPhase = "main"
    invoice_number: str | None = Field(default=None, max_length=40)
    series: str | None = Field(default=None, max_length=20)
    nfe_key: str | None = Field(default=None, max_length=64)
    issue_date: date | None = None
    entry_date: date | None = None
    total_amount: Decimal
    payment_description: str | None = Field(default=None, max_length=160)
    payment_term: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    raw_text: str | None = None
    raw_xml: str | None = None
    installments: list[PurchaseInstallmentDraft] = Field(default_factory=list)


class PurchaseInvoiceImportTextRequest(BaseModel):
    raw_text: str = Field(min_length=20)


class PurchaseInvoiceCreate(PurchaseInvoiceDraft):
    purchase_plan_id: str | None = None
    create_plan: bool = True


class PurchaseInvoiceUpdate(PurchaseInvoiceDraft):
    purchase_plan_id: str | None = None


class PurchasePlanBase(BaseModel):
    brand_id: str | None = None
    supplier_id: str | None = None
    supplier_ids: list[str] = Field(default_factory=list)
    collection_id: str | None = None
    season_phase: SeasonPhase = "main"
    title: str = Field(min_length=2, max_length=160)
    order_date: date | None = None
    expected_delivery_date: date | None = None
    purchased_amount: Decimal
    payment_term: str | None = Field(default=None, max_length=120)
    status: str = Field(default="planned", max_length=20)
    notes: str | None = None


class PurchasePlanCreate(PurchasePlanBase):
    pass


class PurchasePlanUpdate(PurchasePlanBase):
    pass


class PurchasePlanRead(PurchasePlanBase):
    id: str
    brand_name: str | None = None
    supplier_name: str | None = None
    supplier_names: list[str] = Field(default_factory=list)
    collection_name: str | None = None
    season_year: int | None = None
    season_type: SeasonType | None = None
    season_label: str | None = None
    season_phase_label: str | None = None
    billing_deadline: date | None = None
    received_amount: Decimal = Decimal("0.00")
    amount_to_receive: Decimal = Decimal("0.00")
    prior_year_same_season_amount: Decimal = Decimal("0.00")
    current_year_same_season_amount: Decimal = Decimal("0.00")
    current_year_other_seasons_amount: Decimal = Decimal("0.00")
    suggested_remaining_amount: Decimal = Decimal("0.00")

    model_config = {"from_attributes": True}


class PurchaseReturnBase(BaseModel):
    supplier_id: str
    return_date: date
    amount: Decimal
    invoice_number: str | None = None
    status: str = "request_open"
    notes: str | None = None


class PurchaseReturnCreate(PurchaseReturnBase):
    pass


class PurchaseReturnUpdate(PurchaseReturnBase):
    pass


class PurchaseReturnRead(PurchaseReturnBase):
    id: str
    supplier_name: str | None = None
    refund_entry_id: str | None = None

    model_config = {"from_attributes": True}


class PurchaseInstallmentCandidate(BaseModel):
    entry_id: str
    title: str
    due_date: date | None = None
    total_amount: Decimal
    paid_amount: Decimal
    status: str
    counterparty_name: str | None = None


class PurchaseInstallmentRead(BaseModel):
    id: str
    purchase_invoice_id: str
    installment_number: int
    installment_label: str | None = None
    due_date: date | None = None
    amount: Decimal
    status: str
    financial_entry_id: str | None = None
    brand_name: str | None = None
    supplier_name: str | None = None
    collection_name: str | None = None
    invoice_number: str | None = None
    candidates: list[PurchaseInstallmentCandidate] = Field(default_factory=list)


class PurchaseInvoiceRead(BaseModel):
    id: str
    brand_id: str | None = None
    brand_name: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None
    collection_id: str | None = None
    collection_name: str | None = None
    season_phase: SeasonPhase = "main"
    season_phase_label: str | None = None
    purchase_plan_id: str | None = None
    invoice_number: str | None = None
    series: str | None = None
    nfe_key: str | None = None
    issue_date: date | None = None
    entry_date: date | None = None
    total_amount: Decimal
    payment_description: str | None = None
    payment_term: str | None = None
    source_type: str
    status: str
    notes: str | None = None
    installments: list[PurchaseInstallmentRead] = Field(default_factory=list)


class PurchasePlanningRow(BaseModel):
    plan_id: str | None = None
    brand_id: str | None = None
    brand_name: str
    supplier_ids: list[str] = Field(default_factory=list)
    supplier_names: list[str] = Field(default_factory=list)
    collection_id: str | None = None
    collection_name: str
    season_year: int | None = None
    season_type: SeasonType | None = None
    season_label: str | None = None
    billing_deadline: date | None = None
    payment_term: str | None = None
    status: str | None = None
    order_date: date | None = None
    expected_delivery_date: date | None = None
    purchased_total: Decimal
    returns_total: Decimal = Decimal("0.00")
    received_total: Decimal = Decimal("0.00")
    delivered_total: Decimal
    launched_financial_total: Decimal
    paid_total: Decimal
    outstanding_goods_total: Decimal
    delivered_not_recorded_total: Decimal
    outstanding_payable_total: Decimal


class PurchasePlanningSummary(BaseModel):
    purchased_total: Decimal
    delivered_total: Decimal
    launched_financial_total: Decimal
    paid_total: Decimal
    outstanding_goods_total: Decimal
    delivered_not_recorded_total: Decimal
    outstanding_payable_total: Decimal


class PurchasePlanningMonthlyProjection(BaseModel):
    reference: str
    planned_outflows: Decimal
    linked_payments: Decimal
    open_balance: Decimal


class PurchasePlanningUngroupedSupplier(BaseModel):
    supplier_label: str
    collection_name: str | None = None
    season_label: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    entry_count: int = 0
    total_amount: Decimal


class PurchasePlanningCostRow(BaseModel):
    collection_name: str
    supplier_name: str
    purchase_cost_total: Decimal
    purchase_return_cost_total: Decimal = Decimal("0.00")
    net_cost_total: Decimal


class PurchasePlanningOverview(BaseModel):
    summary: PurchasePlanningSummary
    rows: list[PurchasePlanningRow]
    cost_totals: list[PurchasePlanningCostRow] = Field(default_factory=list)
    monthly_projection: list[PurchasePlanningMonthlyProjection]
    invoices: list[PurchaseInvoiceRead]
    open_installments: list[PurchaseInstallmentRead]
    plans: list[PurchasePlanRead]
    ungrouped_suppliers: list[PurchasePlanningUngroupedSupplier] = Field(default_factory=list)


class PurchaseInstallmentLinkRequest(BaseModel):
    financial_entry_id: str | None = None

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FinancialEntryBase(BaseModel):
    account_id: str | None = None
    category_id: str | None = None
    interest_category_id: str | None = None
    transfer_id: str | None = None
    loan_installment_id: str | None = None
    supplier_id: str | None = None
    collection_id: str | None = None
    purchase_invoice_id: str | None = None
    purchase_installment_id: str | None = None
    entry_type: str = Field(max_length=20)
    status: str = Field(default="planned", max_length=20)
    title: str = Field(min_length=2, max_length=160)
    description: str | None = None
    notes: str | None = None
    counterparty_name: str | None = Field(default=None, max_length=180)
    document_number: str | None = Field(default=None, max_length=80)
    issue_date: date | None = None
    competence_date: date | None = None
    due_date: date | None = None
    settled_at: datetime | None = None
    principal_amount: Decimal = Decimal("0.00")
    interest_amount: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    penalty_amount: Decimal = Decimal("0.00")
    total_amount: Decimal | None = None
    paid_amount: Decimal = Decimal("0.00")
    expected_amount: Decimal | None = None
    external_source: str | None = Field(default=None, max_length=50)
    source_system: str | None = Field(default=None, max_length=50)
    source_reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_totals(self) -> "FinancialEntryBase":
        calculated_total = (
            self.principal_amount
            + self.interest_amount
            + self.penalty_amount
            - self.discount_amount
        )
        if self.total_amount is None:
            self.total_amount = calculated_total
        if self.total_amount != calculated_total:
            raise ValueError(
                "total_amount must equal principal_amount + interest_amount + penalty_amount - discount_amount"
            )
        if self.paid_amount < Decimal("0.00"):
            raise ValueError("paid_amount cannot be negative")
        return self


class FinancialEntryCreate(FinancialEntryBase):
    pass


class FinancialEntryUpdate(FinancialEntryBase):
    pass


class EntrySettlementRequest(BaseModel):
    account_id: str | None = None
    settled_at: datetime | None = None
    paid_amount: Decimal | None = None
    principal_amount: Decimal | None = None
    interest_amount: Decimal | None = None
    penalty_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    notes: str | None = None


class EntryStatusRequest(BaseModel):
    notes: str | None = None


class FinancialEntryBulkCategoryUpdateRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=500)
    category_id: str = Field(min_length=1)


class FinancialEntryBulkCategoryUpdateResponse(BaseModel):
    updated_count: int
    category_id: str
    category_name: str
    entry_ids: list[str]


class FinancialEntryBulkDeleteRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=500)


class FinancialEntryBulkDeleteResponse(BaseModel):
    deleted_count: int
    entry_ids: list[str]


class FinancialEntryFilter(BaseModel):
    status: str | None = None
    statuses: list[str] | None = None
    account_id: str | None = None
    category_id: str | None = None
    report_group: str | None = None
    report_subgroup: str | None = None
    entry_type: str | None = None
    entry_types: list[str] | None = None
    reconciled: bool | None = None
    source_system: str | None = None
    counterparty_name: str | None = None
    document_number: str | None = None
    search: str | None = None
    include_legacy: bool = False
    date_field: Literal["due_date", "issue_date"] = "due_date"
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=50, ge=1, le=100000)


class FinancialEntryRead(FinancialEntryBase):
    id: str
    company_id: str
    is_recurring_generated: bool
    is_deleted: bool
    transfer_direction: str | None = None
    account_name: str | None = None
    category_name: str | None = None
    category_group: str | None = None
    category_subgroup: str | None = None
    interest_category_name: str | None = None
    supplier_name: str | None = None
    collection_name: str | None = None
    is_legacy: bool = False

    model_config = {"from_attributes": True}


class FinancialEntryListResponse(BaseModel):
    items: list[FinancialEntryRead]
    total: int
    page: int
    page_size: int
    total_amount: Decimal
    paid_amount: Decimal

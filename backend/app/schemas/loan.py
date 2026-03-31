from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LoanContractCreate(BaseModel):
    account_id: str | None = None
    category_id: str | None = None
    interest_category_id: str | None = None
    lender_name: str = Field(min_length=2, max_length=180)
    contract_number: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    start_date: date
    first_due_date: date
    installments_count: int = Field(ge=1, le=360)
    principal_total: Decimal = Field(gt=0)
    interest_total: Decimal = Decimal("0.00")
    notes: str | None = None


class LoanInstallmentRead(BaseModel):
    id: str
    contract_id: str
    installment_number: int
    due_date: date
    principal_amount: Decimal
    interest_amount: Decimal
    total_amount: Decimal
    status: str
    financial_entry_id: str | None

    model_config = {"from_attributes": True}


class LoanContractRead(BaseModel):
    id: str
    company_id: str
    account_id: str | None
    lender_name: str
    contract_number: str | None
    title: str
    start_date: date
    first_due_date: date
    installments_count: int
    principal_total: Decimal
    interest_total: Decimal
    installment_amount: Decimal
    notes: str | None
    is_active: bool
    installments: list[LoanInstallmentRead]

    model_config = {"from_attributes": True}

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class RecurrenceRuleBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    title_template: str | None = Field(default=None, max_length=160)
    entry_type: str = Field(max_length=20)
    frequency: str = Field(max_length=20)
    interval_value: int = Field(default=1, ge=1, le=36)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    start_date: date
    end_date: date | None = None
    next_run_date: date | None = None
    amount: Decimal = Decimal("0.00")
    principal_amount: Decimal = Decimal("0.00")
    interest_amount: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    penalty_amount: Decimal = Decimal("0.00")
    account_id: str | None = None
    category_id: str | None = None
    interest_category_id: str | None = None
    counterparty_name: str | None = None
    document_number: str | None = None
    description: str | None = None
    notes: str | None = None
    is_active: bool = True


class RecurrenceRuleCreate(RecurrenceRuleBase):
    pass


class RecurrenceRuleUpdate(RecurrenceRuleBase):
    pass


class RecurrenceGenerationRequest(BaseModel):
    until_date: date


class RecurrenceRuleRead(RecurrenceRuleBase):
    id: str
    company_id: str

    model_config = {"from_attributes": True}

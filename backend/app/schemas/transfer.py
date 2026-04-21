from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.core.statuses import OPEN_STATUS, normalize_open_alias


class TransferBase(BaseModel):
    source_account_id: str
    destination_account_id: str
    transfer_date: date
    amount: Decimal = Field(gt=0)
    status: str = Field(default=OPEN_STATUS, max_length=20)
    description: str | None = None
    notes: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str | None) -> str:
        return normalize_open_alias(value, default=OPEN_STATUS) or OPEN_STATUS


class TransferCreate(TransferBase):
    pass


class TransferRead(TransferBase):
    id: str
    company_id: str
    source_entry_id: str | None = None
    destination_entry_id: str | None = None
    source_account_name: str | None = None
    destination_account_name: str | None = None

    model_config = {"from_attributes": True}

from decimal import Decimal

from pydantic import BaseModel, Field


class AccountBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    account_type: str = Field(min_length=2, max_length=40)
    bank_code: str | None = Field(default=None, max_length=10)
    branch_number: str | None = Field(default=None, max_length=20)
    account_number: str | None = Field(default=None, max_length=30)
    opening_balance: Decimal = Decimal("0.00")
    is_active: bool = True
    import_ofx_enabled: bool = False


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    id: str
    company_id: str

    model_config = {"from_attributes": True}

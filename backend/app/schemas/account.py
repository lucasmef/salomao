from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AccountBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    account_type: str = Field(min_length=2, max_length=40)
    bank_code: str | None = Field(default=None, max_length=10)
    branch_number: str | None = Field(default=None, max_length=20)
    account_number: str | None = Field(default=None, max_length=30)
    opening_balance: Decimal = Decimal("0.00")
    is_active: bool = True
    import_ofx_enabled: bool = False
    exclude_from_balance: bool = False
    inter_api_enabled: bool = False
    inter_environment: str = Field(default="production", max_length=20)
    inter_api_base_url: str | None = Field(default=None, max_length=255)
    inter_api_key: str | None = Field(default=None, max_length=160)
    inter_account_number: str | None = Field(default=None, max_length=30)

    @field_validator("inter_environment")
    @classmethod
    def validate_inter_environment(cls, value: str) -> str:
        normalized = (value or "production").strip().lower()
        if normalized not in {"production", "sandbox"}:
            raise ValueError("Ambiente Inter invalido")
        return normalized


class AccountCreate(AccountBase):
    inter_client_secret: str | None = None
    inter_certificate_pem: str | None = None
    inter_private_key_pem: str | None = None


class AccountRead(AccountBase):
    id: str
    company_id: str
    has_inter_client_secret: bool = False
    has_inter_certificate: bool = False
    has_inter_private_key: bool = False

    model_config = {"from_attributes": True}

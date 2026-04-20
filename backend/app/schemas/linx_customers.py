from datetime import date, datetime

from pydantic import BaseModel


class LinxCustomerDirectorySummaryRead(BaseModel):
    total_count: int
    client_count: int
    supplier_count: int
    transporter_count: int
    active_count: int
    boleto_enabled_count: int


class LinxCustomerDirectoryItemRead(BaseModel):
    id: str
    linx_code: int
    legal_name: str
    display_name: str | None = None
    document_number: str | None = None
    birth_date: date | None = None
    registration_type: str | None = None
    registration_type_label: str
    person_type: str | None = None
    person_type_label: str
    is_active: bool
    city: str | None = None
    state: str | None = None
    email: str | None = None
    phone_primary: str | None = None
    mobile: str | None = None
    uses_boleto: bool
    mode: str
    boleto_due_day: int | None = None
    include_interest: bool
    notes: str | None = None
    supports_boleto_config: bool
    has_boleto_config: bool
    missing_boleto_fields: list[str] = []
    linx_updated_at: datetime | None = None


class LinxCustomerDirectoryRead(BaseModel):
    generated_at: datetime
    summary: LinxCustomerDirectorySummaryRead
    items: list[LinxCustomerDirectoryItemRead]

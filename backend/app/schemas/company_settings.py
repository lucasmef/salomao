from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LinxSettingsRead(BaseModel):
    base_url: str
    username: str
    api_base_url: str
    api_cnpj: str | None = None
    sales_view_name: str
    receivables_view_name: str
    payables_view_name: str
    has_password: bool = False
    has_api_key: bool = False
    auto_sync_enabled: bool = False
    auto_sync_alert_email: str | None = None
    auto_sync_last_run_at: datetime | None = None
    auto_sync_last_status: str | None = None
    auto_sync_last_error: str | None = None


class LinxSettingsUpdate(BaseModel):
    base_url: str = Field(min_length=8, max_length=255)
    username: str = Field(min_length=1, max_length=160)
    password: str | None = Field(default=None, max_length=255)
    api_base_url: str | None = Field(default=None, min_length=8, max_length=255)
    api_cnpj: str | None = Field(default=None, max_length=20)
    api_key: str | None = Field(default=None, max_length=255)
    sales_view_name: str = Field(min_length=1, max_length=160)
    receivables_view_name: str = Field(min_length=1, max_length=160)
    payables_view_name: str = Field(min_length=1, max_length=160)
    auto_sync_enabled: bool = False
    auto_sync_alert_email: str | None = Field(default=None, max_length=255)

    @field_validator(
        "base_url",
        "username",
        "password",
        "api_base_url",
        "api_cnpj",
        "api_key",
        "sales_view_name",
        "receivables_view_name",
        "payables_view_name",
        "auto_sync_alert_email",
    )
    @classmethod
    def strip_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

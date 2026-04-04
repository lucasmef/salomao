from pydantic import BaseModel, Field, field_validator


class LinxSettingsRead(BaseModel):
    base_url: str
    username: str
    sales_view_name: str
    receivables_view_name: str
    has_password: bool = False


class LinxSettingsUpdate(BaseModel):
    base_url: str = Field(min_length=8, max_length=255)
    username: str = Field(min_length=1, max_length=160)
    password: str | None = Field(default=None, max_length=255)
    sales_view_name: str = Field(min_length=1, max_length=160)
    receivables_view_name: str = Field(min_length=1, max_length=160)

    @field_validator("base_url", "username", "password", "sales_view_name", "receivables_view_name")
    @classmethod
    def strip_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

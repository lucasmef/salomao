import re
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


def validate_email(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", value):
        raise ValueError("Informe um endereco de e-mail valido")
    return value


class SmtpSettingsRead(BaseModel):
    enabled: bool
    host: str
    port: int
    encryption: Literal["ssl", "starttls", "none"]
    username: str
    sender: str
    recipients: str
    has_password: bool
    source: Literal["environment", "database"]


class SmtpSettingsUpdate(BaseModel):
    enabled: bool = False
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    encryption: Literal["ssl", "starttls"]
    username: str = Field(min_length=1, max_length=255)
    sender: str = Field(max_length=255)
    recipients: str = Field(default="", max_length=4000)
    password: SecretStr | None = None

    @field_validator("host", "username")
    @classmethod
    def validate_connection_field(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError("Informe o valor sem espacos ou quebras de linha")
        return value

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, value: str) -> str:
        return ", ".join(validate_email(item) for item in re.split(r"[,;]", value) if item.strip())


class SmtpTestRequest(SmtpSettingsUpdate):
    recipient: str = Field(max_length=255)

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        return validate_email(value)

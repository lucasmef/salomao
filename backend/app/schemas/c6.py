from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class C6AuthTestRequest(BaseModel):
    account_id: str | None = Field(default=None, min_length=1)


class C6AuthTestResponse(BaseModel):
    account_id: str
    environment: str
    token_type: str
    expires_in: int | None = None
    scope: str | None = None


class C6BankSlipLookupResponse(BaseModel):
    account_id: str
    environment: str
    bank_slip_id: str
    payload: dict[str, Any]

from datetime import date, timedelta

from pydantic import BaseModel, Field, model_validator


def _default_statement_start() -> date:
    return date.today() - timedelta(days=30)


def _default_charge_start() -> date:
    return date.today() - timedelta(days=90)


class InterStatementSyncRequest(BaseModel):
    account_id: str = Field(min_length=1)
    start_date: date = Field(default_factory=_default_statement_start)
    end_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_period(self) -> "InterStatementSyncRequest":
        if self.start_date > self.end_date:
            raise ValueError("Periodo do extrato invalido")
        return self


class InterChargeSyncRequest(BaseModel):
    account_id: str = Field(min_length=1)
    start_date: date = Field(default_factory=_default_charge_start)
    end_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_period(self) -> "InterChargeSyncRequest":
        if self.start_date > self.end_date:
            raise ValueError("Periodo da cobranca invalido")
        return self


class InterChargeIssueRequest(BaseModel):
    account_id: str = Field(min_length=1)
    selection_keys: list[str] = Field(default_factory=list)

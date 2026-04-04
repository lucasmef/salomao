from datetime import date, datetime

from pydantic import BaseModel, model_validator


class ImportBatchRead(BaseModel):
    id: str
    source_type: str
    filename: str
    status: str
    records_total: int
    records_valid: int
    records_invalid: int
    error_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportResult(BaseModel):
    batch: ImportBatchRead
    message: str


class ImportSummary(BaseModel):
    import_batches: list[ImportBatchRead]
    sales_snapshot_count: int
    receivable_title_count: int
    bank_transaction_count: int
    historical_cashbook_count: int
    latest_ofx_transaction_date: str | None = None


class LinxSyncRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "LinxSyncRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date nao pode ser maior que end_date")
        return self

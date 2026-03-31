from datetime import datetime

from pydantic import BaseModel


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

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LinxOpenReceivableDirectorySummaryRead(BaseModel):
    total_count: int
    overdue_count: int
    due_today_count: int
    total_amount: Decimal


class LinxOpenReceivableListItemRead(BaseModel):
    id: str
    linx_code: int
    customer_code: int | None = None
    customer_name: str
    issue_date: datetime | None = None
    due_date: datetime | None = None
    amount: Decimal | None = None
    paid_amount: Decimal | None = None
    document_number: str | None = None
    document_series: str | None = None
    installment_number: int | None = None
    installment_count: int | None = None
    identifier: str | None = None
    payment_method_name: str | None = None
    payment_plan_code: int | None = None
    linx_row_timestamp: int | None = None


class LinxOpenReceivableDirectoryRead(BaseModel):
    generated_at: datetime
    summary: LinxOpenReceivableDirectorySummaryRead
    items: list[LinxOpenReceivableListItemRead]
    total: int
    page: int
    page_size: int

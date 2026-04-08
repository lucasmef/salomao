from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LinxMovementDirectorySummaryRead(BaseModel):
    total_count: int
    sales_total_amount: Decimal
    sales_return_total_amount: Decimal
    purchases_total_amount: Decimal
    purchase_returns_total_amount: Decimal


class LinxMovementListItemRead(BaseModel):
    id: str
    linx_transaction: int
    movement_group: str
    movement_type: str
    document_number: str | None = None
    document_series: str | None = None
    identifier: str | None = None
    issue_date: datetime | None = None
    launch_date: datetime | None = None
    customer_code: int | None = None
    product_code: int | None = None
    product_description: str | None = None
    product_reference: str | None = None
    collection_name: str | None = None
    quantity: Decimal | None = None
    cost_price: Decimal | None = None
    unit_price: Decimal | None = None
    net_amount: Decimal | None = None
    total_amount: Decimal | None = None
    item_discount_amount: Decimal | None = None
    nature_code: str | None = None
    nature_description: str | None = None
    cfop_description: str | None = None
    linx_updated_at: datetime | None = None
    linx_row_timestamp: int | None = None


class LinxMovementDirectoryRead(BaseModel):
    generated_at: datetime
    summary: LinxMovementDirectorySummaryRead
    items: list[LinxMovementListItemRead]
    total: int
    page: int
    page_size: int

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LinxProductDirectorySummaryRead(BaseModel):
    total_count: int
    active_count: int
    inactive_count: int
    with_supplier_count: int
    with_collection_count: int


class LinxProductListItemRead(BaseModel):
    id: str
    linx_code: int
    description: str
    reference: str | None = None
    barcode: str | None = None
    unit: str | None = None
    brand_name: str | None = None
    line_name: str | None = None
    sector_name: str | None = None
    supplier_code: int | None = None
    supplier_name: str | None = None
    collection_id: int | None = None
    collection_name: str | None = None
    collection_name_raw: str | None = None
    price_cost: Decimal | None = None
    price_sale: Decimal | None = None
    stock_quantity: Decimal | None = None
    is_active: bool
    linx_updated_at: datetime | None = None


class LinxProductDirectoryRead(BaseModel):
    generated_at: datetime
    summary: LinxProductDirectorySummaryRead
    items: list[LinxProductListItemRead]
    total: int
    page: int
    page_size: int


class LinxProductSearchRead(BaseModel):
    generated_at: datetime
    query: str
    total: int
    items: list[LinxProductListItemRead]

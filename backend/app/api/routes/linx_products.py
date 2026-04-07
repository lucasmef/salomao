from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.linx_products import LinxProductDirectoryRead
from app.services.company_context import get_current_company
from app.services.linx_products import list_linx_products

router = APIRouter()


@router.get("", response_model=LinxProductDirectoryRead)
def get_linx_products(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    search: str | None = Query(default=None),
    status: str = Query(default="all"),
) -> LinxProductDirectoryRead:
    company = get_current_company(db)
    return list_linx_products(
        db,
        company,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
    )

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.linx_products import LinxProductDirectoryRead, LinxProductSearchRead
from app.services.company_context import get_current_company
from app.services.linx_products import list_linx_products, search_linx_products

router = APIRouter()


@router.get("/search", response_model=LinxProductSearchRead)
def search_products(
    db: DbSession,
    q: str = Query(min_length=2),
    limit: int = Query(default=20, ge=1, le=60),
) -> LinxProductSearchRead:
    company = get_current_company(db)
    return search_linx_products(db, company, query=q, limit=limit)


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

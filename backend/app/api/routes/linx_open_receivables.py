from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.linx_open_receivables import LinxOpenReceivableDirectoryRead
from app.services.company_context import get_current_company
from app.services.linx_open_receivables import list_linx_open_receivables

router = APIRouter()


@router.get("", response_model=LinxOpenReceivableDirectoryRead)
def get_linx_open_receivables(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    search: str | None = Query(default=None),
) -> LinxOpenReceivableDirectoryRead:
    company = get_current_company(db)
    return list_linx_open_receivables(
        db,
        company,
        page=page,
        page_size=page_size,
        search=search,
    )

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.linx_movements import (
    LinxMovementDirectoryRead,
    LinxMovementReversalDiagnosticRead,
)
from app.services.company_context import get_current_company
from app.services.linx_movements import (
    diagnose_purchase_return_reversal_candidates,
    list_linx_movements,
)

router = APIRouter()


@router.get("", response_model=LinxMovementDirectoryRead)
def get_linx_movements(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    search: str | None = Query(default=None),
    group: str = Query(default="all"),
    movement_type: str = Query(default="all"),
) -> LinxMovementDirectoryRead:
    company = get_current_company(db)
    return list_linx_movements(
        db,
        company,
        page=page,
        page_size=page_size,
        search=search,
        group=group,
        movement_type=movement_type,
    )


@router.get(
    "/purchase-return-reversal-diagnostics",
    response_model=LinxMovementReversalDiagnosticRead,
)
def get_purchase_return_reversal_diagnostics(
    db: DbSession,
    limit: int = Query(default=2000, ge=100, le=10000),
) -> LinxMovementReversalDiagnosticRead:
    company = get_current_company(db)
    return diagnose_purchase_return_reversal_candidates(db, company, limit=limit)

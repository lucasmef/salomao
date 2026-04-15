from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.cashflow import CashflowOverview
from app.services.cashflow import get_cached_cashflow_overview
from app.services.company_context import get_current_company

router = APIRouter()


@router.get("/overview", response_model=CashflowOverview)
def get_cashflow_overview(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    account_id: str | None = Query(default=None),
    include_purchase_planning: bool = Query(default=True),
    include_crediario_receivables: bool = Query(default=True),
    refresh: bool = Query(default=False),
) -> CashflowOverview:
    company = get_current_company(db)
    return get_cached_cashflow_overview(
        db,
        company,
        start_date=start,
        end_date=end,
        account_id=account_id,
        include_purchase_planning=include_purchase_planning,
        include_crediario_receivables=include_crediario_receivables,
        refresh=refresh,
    )

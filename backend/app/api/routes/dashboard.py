from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.dashboard import DashboardOverview
from app.services.company_context import get_current_company
from app.services.dashboard import build_dashboard_overview

router = APIRouter()


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> DashboardOverview:
    today = date.today()
    period_start = start or date(today.year, today.month, 1)
    period_end = end or (
        date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
        - timedelta(days=1)
    )
    company = get_current_company(db)
    return build_dashboard_overview(db, company, start=period_start, end=period_end)

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.schemas.dashboard import DashboardOverview
from app.services.cache_invalidation import refresh_finance_analytics_caches
from app.services.company_context import get_current_company
from app.services.dashboard import build_dashboard_week_birthdays, get_cached_dashboard_overview

router = APIRouter()


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> DashboardOverview:
    today = date.today()
    period_start = start or date(today.year, today.month, 1)
    period_end = end or (
        date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
        - timedelta(days=1)
    )
    company = get_current_company(db)
    overview = get_cached_dashboard_overview(db, company, start=period_start, end=period_end, refresh=refresh)
    return overview.model_copy(
        update={
            "week_birthdays": build_dashboard_week_birthdays(db, company),
        }
    )


@router.post("/analytics/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_dashboard_analytics(
    db: DbSession,
) -> dict[str, str]:
    company = get_current_company(db)
    refresh_finance_analytics_caches(db, company, include_sales_history=True)
    return {
        "status": "refresh_started",
        "refreshed_at": datetime.utcnow().isoformat(timespec="seconds"),
    }

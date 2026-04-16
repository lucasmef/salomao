from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.schemas.dashboard import DashboardOverview
from app.services.cache_invalidation import refresh_finance_analytics_caches
from app.services.company_context import get_current_company
from app.services.dashboard import get_cached_dashboard_overview

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
    return get_cached_dashboard_overview(db, company, start=period_start, end=period_end, refresh=refresh)


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
@router.get("/debug/revenue", include_in_schema=False)
def debug_revenue_data(db: DbSession):
    """Temporary debug endpoint - shows raw SalesSnapshot data for 2026."""
    from app.db.models.linx import SalesSnapshot
    from sqlalchemy import func, select, text

    # Monthly totals for 2026 - all companies
    monthly = db.execute(
        select(
            SalesSnapshot.company_id,
            func.extract("month", SalesSnapshot.snapshot_date).label("month"),
            func.sum(SalesSnapshot.gross_revenue).label("total"),
            func.count(SalesSnapshot.id).label("days"),
            func.min(SalesSnapshot.snapshot_date).label("first_day"),
            func.max(SalesSnapshot.snapshot_date).label("last_day"),
        )
        .where(SalesSnapshot.snapshot_date >= date(2026, 1, 1))
        .group_by(SalesSnapshot.company_id, text("2"))
        .order_by(SalesSnapshot.company_id, text("2"))
    ).all()

    return {
        "monthly_2026": [
            {
                "company_id": r[0],
                "month": int(r[1]),
                "total_revenue": str(r[2]),
                "days_count": r[3],
                "first_day": str(r[4]),
                "last_day": str(r[5]),
            }
            for r in monthly
        ]
    }

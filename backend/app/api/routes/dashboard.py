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
    from app.db.models.linx import SalesSnapshot
    from sqlalchemy import func, select
    
    # Summary for 2026
    summary = db.execute(
        select(
            func.count(SalesSnapshot.id),
            func.sum(SalesSnapshot.gross_revenue),
            func.min(SalesSnapshot.snapshot_date),
            func.max(SalesSnapshot.snapshot_date)
        ).where(SalesSnapshot.snapshot_date >= date(2026, 1, 1))
    ).one()
    
    # Detailed April 2026
    details = db.execute(
        select(
            SalesSnapshot.snapshot_date,
            SalesSnapshot.gross_revenue,
            SalesSnapshot.company_id
        ).where(
            SalesSnapshot.snapshot_date >= date(2026, 4, 1),
            SalesSnapshot.snapshot_date <= date(2026, 4, 30)
        ).order_by(SalesSnapshot.snapshot_date)
    ).all()
    
    return {
        "summary_2026": {
            "count": summary[0],
            "total_revenue": str(summary[1]),
            "min_date": str(summary[2]),
            "max_date": str(summary[3]),
        },
        "april_details": [
            {"date": str(d[0]), "revenue": str(d[1]), "company_id": d[2]}
            for d in details
        ]
    }

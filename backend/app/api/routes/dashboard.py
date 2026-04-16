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
    from app.services.company_context import get_current_company
    from sqlalchemy import func, select
    
    company = get_current_company(db)
    
    # Summary for 2026
    summary = db.execute(
        select(
            func.count(SalesSnapshot.id),
            func.sum(SalesSnapshot.gross_revenue),
            func.min(SalesSnapshot.snapshot_date),
            func.max(SalesSnapshot.snapshot_date)
        ).where(
            SalesSnapshot.company_id == company.id,
            SalesSnapshot.snapshot_date >= date(2026, 1, 1)
        )
    ).one()
    
    # Detailed April 2026
    details = db.execute(
        select(
            SalesSnapshot.snapshot_date,
            SalesSnapshot.gross_revenue
        ).where(
            SalesSnapshot.company_id == company.id,
            SalesSnapshot.snapshot_date >= date(2026, 4, 1),
            SalesSnapshot.snapshot_date <= date(2026, 4, 30)
        ).order_by(SalesSnapshot.snapshot_date)
    ).all()
    
    # LinxMovement totals for April 2026
    from app.db.models.linx import LinxMovement
    movement_summary = db.execute(
        select(
            func.count(LinxMovement.id),
            func.sum(case((LinxMovement.movement_type == "sale", LinxMovement.total_amount), else_=0)) -
            func.sum(case((LinxMovement.movement_type == "sale_return", LinxMovement.total_amount), else_=0))
        ).where(
            LinxMovement.company_id == company.id,
            LinxMovement.launch_date >= datetime(2026, 4, 1),
            LinxMovement.launch_date <= datetime(2026, 4, 30, 23, 59, 59)
        )
    ).one()
    
    return {
        "company": {
            "id": company.id,
            "name": company.trade_name,
            "linx_sync_enabled": company.linx_auto_sync_enabled,
            "linx_last_run": str(company.linx_auto_sync_last_run_at),
            "linx_last_status": company.linx_auto_sync_last_status,
            "linx_last_error": company.linx_auto_sync_last_error,
        },
        "movements_april_2026": {
            "count": movement_summary[0],
            "net_revenue": str(movement_summary[1]),
        },
        "summary_2026": {
            "count": summary[0],
            "total_revenue": str(summary[1]),
            "min_date": str(summary[2]),
            "max_date": str(summary[3]),
        },
        "april_details": [
            {"date": str(d[0]), "revenue": str(d[1])}
            for d in details
        ]
    }

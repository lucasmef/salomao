from datetime import date
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.analytics_hybrid import DEFAULT_ANALYTICS_KINDS, process_snapshot_rebuild_queue, queue_historical_rebuilds
from app.services.cashflow import clear_cashflow_overview_cache, get_cached_cashflow_overview
from app.services.dashboard import (
    clear_dashboard_overview_cache,
    clear_dashboard_revenue_comparison_cache,
    get_cached_dashboard_overview,
)
from app.services.reports import clear_reports_overview_cache, get_cached_reports_overview


def clear_finance_analytics_caches(
    company_id: str | None = None,
    *,
    include_sales_history: bool = False,
    db: Session | None = None,
    company: Company | None = None,
    affected_dates: Iterable[date] | None = None,
) -> None:
    clear_dashboard_overview_cache(company_id)
    clear_cashflow_overview_cache(company_id)
    clear_reports_overview_cache(company_id)
    if include_sales_history:
        clear_dashboard_revenue_comparison_cache(company_id)
    if db is None or company is None:
        return
    queued_months = queue_historical_rebuilds(
        db,
        company_id=company.id,
        affected_dates=affected_dates,
        kinds=DEFAULT_ANALYTICS_KINDS,
        reason="event_invalidation",
    )
    if queued_months and affected_dates is not None:
        process_snapshot_rebuild_queue(db, company, limit=max(len(queued_months) * len(DEFAULT_ANALYTICS_KINDS), 1))
    db.commit()


def refresh_finance_analytics_caches(
    db: Session | None,
    company: Company,
    *,
    include_sales_history: bool = False,
) -> None:
    clear_finance_analytics_caches(
        company.id,
        include_sales_history=include_sales_history,
        db=db,
        company=company,
    )
    today = date.today()
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - date.resolution
    else:
        month_end = date(today.year, today.month + 1, 1) - date.resolution
    get_cached_reports_overview(db, company, start=month_start, end=month_end)
    get_cached_cashflow_overview(db, company, start_date=month_start, end_date=month_end)
    get_cached_dashboard_overview(db, company, start=month_start, end=month_end)
    if db is None:
        return
    process_snapshot_rebuild_queue(db, company, limit=24)
    db.commit()

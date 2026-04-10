from datetime import date

from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.cashflow import clear_cashflow_overview_cache, get_cached_cashflow_overview
from app.services.dashboard import (
    clear_dashboard_overview_cache,
    clear_dashboard_revenue_comparison_cache,
    get_cached_dashboard_overview,
)
from app.services.reports import clear_reports_overview_cache, get_cached_reports_overview


def clear_finance_analytics_caches(company_id: str | None = None, *, include_sales_history: bool = False) -> None:
    clear_dashboard_overview_cache(company_id)
    clear_cashflow_overview_cache(company_id)
    clear_reports_overview_cache(company_id)
    if include_sales_history:
        clear_dashboard_revenue_comparison_cache(company_id)


def refresh_finance_analytics_caches(
    db: Session,
    company: Company,
    *,
    include_sales_history: bool = False,
) -> None:
    clear_finance_analytics_caches(company.id, include_sales_history=include_sales_history)
    today = date.today()
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - date.resolution
    else:
        month_end = date(today.year, today.month + 1, 1) - date.resolution
    get_cached_reports_overview(db, company, start=month_start, end=month_end)
    get_cached_cashflow_overview(db, company, start_date=month_start, end_date=month_end)
    get_cached_dashboard_overview(db, company, start=month_start, end=month_end)

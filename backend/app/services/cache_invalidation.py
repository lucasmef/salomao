from app.services.dashboard import clear_dashboard_overview_cache
from app.services.reports import clear_reports_overview_cache


def clear_finance_analytics_caches(company_id: str | None = None) -> None:
    clear_dashboard_overview_cache(company_id)
    clear_reports_overview_cache(company_id)

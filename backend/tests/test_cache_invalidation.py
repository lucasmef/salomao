from datetime import date
from types import SimpleNamespace

from app.services import cache_invalidation


class _FakeDate(date):
    @classmethod
    def today(cls) -> "_FakeDate":
        return cls(2026, 4, 10)


def test_refresh_finance_analytics_caches_clears_and_warms_current_month(monkeypatch) -> None:
    events: list[tuple[object, ...]] = []
    company = SimpleNamespace(id="company-1")

    monkeypatch.setattr(cache_invalidation, "date", _FakeDate)
    monkeypatch.setattr(
        cache_invalidation,
        "clear_finance_analytics_caches",
        lambda company_id, include_sales_history=False: events.append(("clear", company_id, include_sales_history)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "get_cached_reports_overview",
        lambda _db, current_company, *, start, end: events.append(("reports", current_company.id, start, end)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "get_cached_cashflow_overview",
        lambda _db, current_company, *, start_date, end_date: events.append(("cashflow", current_company.id, start_date, end_date)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "get_cached_dashboard_overview",
        lambda _db, current_company, *, start, end: events.append(("dashboard", current_company.id, start, end)),
    )

    cache_invalidation.refresh_finance_analytics_caches(None, company, include_sales_history=True)

    assert events == [
        ("clear", "company-1", True),
        ("reports", "company-1", date(2026, 4, 1), date(2026, 4, 30)),
        ("cashflow", "company-1", date(2026, 4, 1), date(2026, 4, 30)),
        ("dashboard", "company-1", date(2026, 4, 1), date(2026, 4, 30)),
    ]


def test_clear_finance_analytics_caches_clears_sales_history_only_when_requested(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        cache_invalidation,
        "clear_dashboard_overview_cache",
        lambda company_id=None: events.append(("dashboard", company_id)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "clear_cashflow_overview_cache",
        lambda company_id=None: events.append(("cashflow", company_id)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "clear_reports_overview_cache",
        lambda company_id=None: events.append(("reports", company_id)),
    )
    monkeypatch.setattr(
        cache_invalidation,
        "clear_dashboard_revenue_comparison_cache",
        lambda company_id=None: events.append(("sales-history", company_id)),
    )

    cache_invalidation.clear_finance_analytics_caches("company-1", include_sales_history=False)
    cache_invalidation.clear_finance_analytics_caches("company-1", include_sales_history=True)

    assert events == [
        ("dashboard", "company-1"),
        ("cashflow", "company-1"),
        ("reports", "company-1"),
        ("dashboard", "company-1"),
        ("cashflow", "company-1"),
        ("reports", "company-1"),
        ("sales-history", "company-1"),
    ]

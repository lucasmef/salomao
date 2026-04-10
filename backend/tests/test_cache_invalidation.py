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
        "get_cached_dashboard_overview",
        lambda _db, current_company, *, start, end: events.append(("dashboard", current_company.id, start, end)),
    )

    cache_invalidation.refresh_finance_analytics_caches(None, company, include_sales_history=True)

    assert events == [
        ("clear", "company-1", True),
        ("reports", "company-1", date(2026, 4, 1), date(2026, 4, 30)),
        ("dashboard", "company-1", date(2026, 4, 1), date(2026, 4, 30)),
    ]

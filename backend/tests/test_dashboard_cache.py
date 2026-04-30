from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.dashboard import (
    DashboardAccountBalance,
    DashboardKpis,
    DashboardOverview,
    DashboardRevenueComparison,
    DashboardRevenueComparisonPoint,
    DashboardSeriesPoint,
)
from app.services import dashboard


def _sample_overview() -> DashboardOverview:
    return DashboardOverview(
        period_label="2026-04-01 a 2026-04-30",
        kpis=DashboardKpis(
            gross_revenue=Decimal("100.00"),
            net_revenue=Decimal("90.00"),
            cmv=Decimal("10.00"),
            purchases_paid=Decimal("5.00"),
            operating_expenses=Decimal("8.00"),
            financial_expenses=Decimal("2.00"),
            net_profit=Decimal("15.00"),
            profit_distribution=Decimal("3.00"),
            remaining_profit=Decimal("12.00"),
            current_balance=Decimal("50.00"),
            projected_balance=Decimal("70.00"),
            receivables_period=Decimal("200.00"),
            payables_period=Decimal("120.00"),
            receivables_30d=Decimal("200.00"),
            payables_30d=Decimal("120.00"),
            overdue_receivables_amount=Decimal("20.00"),
            delinquency_rate=Decimal("9.09"),
            overdue_payables=1,
            overdue_receivables=2,
            pending_reconciliations=3,
        ),
        dre_cards=[DashboardSeriesPoint(label="Receita", value=Decimal("100.00"))],
        dre_chart=[DashboardSeriesPoint(label="Receita", value=Decimal("100.00"))],
        revenue_comparison=DashboardRevenueComparison(
            current_year=2026,
            previous_year=2025,
            points=[
                DashboardRevenueComparisonPoint(
                    month=4,
                    label="Abr",
                    current_year_value=Decimal("100.00"),
                    previous_year_value=Decimal("80.00"),
                )
            ],
        ),
        account_balances=[
            DashboardAccountBalance(
                account_id="account-1",
                account_name="Conta Principal",
                account_type="checking",
                current_balance=Decimal("50.00"),
            )
        ],
        overdue_payables=[],
        overdue_receivables=[],
        pending_reconciliations=3,
        pending_reconciliation_items=[],
    )


def test_current_month_overview_is_served_from_cache(monkeypatch) -> None:
    dashboard.clear_dashboard_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_overview()

    monkeypatch.setattr(dashboard, "_overview_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(dashboard, "build_dashboard_overview", fake_build)

    first = dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    second = dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert build_calls["count"] == 1
    assert first == second


def test_clearing_overview_cache_forces_rebuild(monkeypatch) -> None:
    dashboard.clear_dashboard_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_overview()

    monkeypatch.setattr(dashboard, "_overview_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(dashboard, "build_dashboard_overview", fake_build)

    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    dashboard.clear_dashboard_overview_cache(company.id)
    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert build_calls["count"] == 2


def test_non_month_overview_bypasses_cache(monkeypatch) -> None:
    dashboard.clear_dashboard_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_overview()

    monkeypatch.setattr(dashboard, "_overview_cache_ttl_seconds", lambda *_args, **_kwargs: None)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(dashboard, "build_dashboard_overview", fake_build)

    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 5), end=date(2026, 4, 30))
    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 5), end=date(2026, 4, 30))

    assert build_calls["count"] == 2


def test_revenue_comparison_reuses_historical_cache_but_queries_today_live(monkeypatch) -> None:
    dashboard.clear_dashboard_revenue_comparison_cache()
    query_calls: list[tuple[date, date]] = []

    def fake_query(_db, _company_id, *, start_date: date, end_date: date):
        query_calls.append((start_date, end_date))
        if start_date == date(2026, 4, 10):
            return {(2026, 4): Decimal("5.00")}
        return {
            (2025, 4): Decimal("80.00"),
            (2026, 4): Decimal("95.00"),
        }

    monkeypatch.setattr(dashboard, "_query_revenue_totals_by_year_month", fake_query)

    first = dashboard._get_revenue_comparison_totals(None, "company-1", 2026, today=date(2026, 4, 10))
    second = dashboard._get_revenue_comparison_totals(None, "company-1", 2026, today=date(2026, 4, 10))

    assert first == second
    assert query_calls == [
        (date(2026, 4, 10), date(2026, 4, 10)),
        (date(2025, 1, 1), date(2026, 4, 9)),
        (date(2026, 4, 10), date(2026, 4, 10)),
    ]


def test_dashboard_refresh_forces_rebuild_even_with_live_cache(monkeypatch) -> None:
    dashboard.clear_dashboard_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_overview()

    monkeypatch.setattr(dashboard, "_overview_cache_ttl_seconds", lambda *_args, **_kwargs: 120)
    monkeypatch.setattr(dashboard, "get_cached_reports_overview", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(dashboard, "get_cached_cashflow_overview", lambda *_args, **_kwargs: object())

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(dashboard, "build_dashboard_overview", fake_build)

    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30), refresh=True)

    assert build_calls["count"] == 2

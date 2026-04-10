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
    )


def test_current_month_overview_is_served_from_cache(monkeypatch) -> None:
    dashboard.clear_dashboard_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_overview()

    monkeypatch.setattr(dashboard, "_overview_cache_signature", lambda *_args, **_kwargs: ("sig-1",))
    monkeypatch.setattr(dashboard, "_overview_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(dashboard, "build_dashboard_overview", fake_build)

    first = dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    second = dashboard.get_cached_dashboard_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert build_calls["count"] == 1
    assert first == second


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

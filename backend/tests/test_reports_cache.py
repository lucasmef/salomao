from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.reports import (
    DreReport,
    DroReport,
    ReportDashboardCard,
    ReportsOverview,
)
from app.services import reports


def _sample_report() -> ReportsOverview:
    return ReportsOverview(
        dre=DreReport(
            period_label="2026-04-01 a 2026-04-30",
            gross_revenue=Decimal("100.00"),
            deductions=Decimal("10.00"),
            net_revenue=Decimal("90.00"),
            cmv=Decimal("20.00"),
            gross_profit=Decimal("70.00"),
            other_operating_income=Decimal("5.00"),
            operating_expenses=Decimal("15.00"),
            financial_expenses=Decimal("2.00"),
            non_operating_income=Decimal("1.00"),
            non_operating_expenses=Decimal("0.00"),
            taxes_on_profit=Decimal("3.00"),
            net_profit=Decimal("56.00"),
            profit_distribution=Decimal("6.00"),
            remaining_profit=Decimal("50.00"),
            dashboard_cards=[ReportDashboardCard(key="gross_revenue", label="Receita", amount=Decimal("100.00"))],
            statement=[],
        ),
        dro=DroReport(
            period_label="2026-04-01 a 2026-04-30",
            bank_revenue=Decimal("80.00"),
            sales_taxes=Decimal("8.00"),
            purchases_paid=Decimal("20.00"),
            contribution_margin=Decimal("52.00"),
            operating_expenses=Decimal("15.00"),
            financial_expenses=Decimal("2.00"),
            non_operating_income=Decimal("1.00"),
            non_operating_expenses=Decimal("0.00"),
            net_profit=Decimal("36.00"),
            profit_distribution=Decimal("6.00"),
            remaining_profit=Decimal("30.00"),
            dashboard_cards=[ReportDashboardCard(key="bank_revenue", label="Receita", amount=Decimal("80.00"))],
            statement=[],
        ),
    )


def test_current_month_reports_are_served_from_cache(monkeypatch) -> None:
    reports.clear_reports_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_report()

    monkeypatch.setattr(reports, "_reports_cache_signature", lambda *_args, **_kwargs: ("sig-1",))
    monkeypatch.setattr(reports, "_reports_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(reports, "build_reports_overview", fake_build)

    first = reports.get_cached_reports_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    second = reports.get_cached_reports_overview(None, company, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert build_calls["count"] == 1
    assert first == second


def test_non_month_reports_bypass_cache(monkeypatch) -> None:
    reports.clear_reports_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_report()

    monkeypatch.setattr(reports, "_reports_cache_ttl_seconds", lambda *_args, **_kwargs: None)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(reports, "build_reports_overview", fake_build)

    reports.get_cached_reports_overview(None, company, start=date(2026, 4, 5), end=date(2026, 4, 30))
    reports.get_cached_reports_overview(None, company, start=date(2026, 4, 5), end=date(2026, 4, 30))

    assert build_calls["count"] == 2

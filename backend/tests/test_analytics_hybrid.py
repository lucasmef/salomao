from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import reporting as reporting_models  # noqa: F401
from app.db.models import security as security_models  # noqa: F401
from app.db.models.base import Base
from app.db.models.security import Company
from app.schemas.reports import DreReport, DroReport, ReportDashboardCard, ReportsOverview
from app.services import analytics_hybrid, reports


def _sample_reports(label: str, gross_revenue: str) -> ReportsOverview:
    amount = Decimal(gross_revenue)
    return ReportsOverview(
        dre=DreReport(
            period_label=label,
            gross_revenue=amount,
            deductions=Decimal("10.00"),
            net_revenue=amount - Decimal("10.00"),
            cmv=Decimal("20.00"),
            gross_profit=amount - Decimal("30.00"),
            other_operating_income=Decimal("0.00"),
            operating_expenses=Decimal("15.00"),
            financial_expenses=Decimal("2.00"),
            non_operating_income=Decimal("0.00"),
            non_operating_expenses=Decimal("0.00"),
            taxes_on_profit=Decimal("3.00"),
            net_profit=amount - Decimal("50.00"),
            profit_distribution=Decimal("5.00"),
            remaining_profit=amount - Decimal("55.00"),
            dashboard_cards=[ReportDashboardCard(key="gross_revenue", label="Receita", amount=amount)],
            statement=[],
        ),
        dro=DroReport(
            period_label=label,
            bank_revenue=amount,
            sales_taxes=Decimal("8.00"),
            purchases_paid=Decimal("20.00"),
            contribution_margin=amount - Decimal("28.00"),
            operating_expenses=Decimal("15.00"),
            financial_expenses=Decimal("2.00"),
            non_operating_income=Decimal("0.00"),
            non_operating_expenses=Decimal("0.00"),
            net_profit=amount - Decimal("45.00"),
            profit_distribution=Decimal("5.00"),
            remaining_profit=amount - Decimal("50.00"),
            dashboard_cards=[ReportDashboardCard(key="bank_revenue", label="Receita", amount=amount)],
            statement=[],
        ),
    )


def _build_company() -> tuple[Session, Company]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
    session.add(company)
    session.commit()
    return session, company


def test_reports_historical_month_reads_persisted_snapshot(monkeypatch) -> None:
    session, company = _build_company()
    snapshot = _sample_reports("2025-12-01 a 2025-12-31", "120.00")
    analytics_hybrid.upsert_monthly_snapshot(
        session,
        snapshot,
        company_id=company.id,
        kind=analytics_hybrid.ANALYTICS_REPORTS_OVERVIEW,
        snapshot_month=date(2025, 12, 1),
    )
    session.commit()

    monkeypatch.setattr(
        reports,
        "build_reports_overview",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("snapshot should be used first")),
    )

    result = reports.get_cached_reports_overview(session, company, start=date(2025, 12, 1), end=date(2025, 12, 31))

    assert result.dre.gross_revenue == Decimal("120.00")


def test_reports_live_month_uses_redis_cache(monkeypatch) -> None:
    session, company = _build_company()
    build_calls = {"count": 0}

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return _sample_reports("2026-04-01 a 2026-04-30", "90.00")

    monkeypatch.setattr(reports, "build_reports_overview", fake_build)

    first = reports.get_cached_reports_overview(session, company, start=date(2026, 4, 1), end=date(2026, 4, 30))
    second = reports.get_cached_reports_overview(session, company, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert build_calls["count"] == 1
    assert first.dre.gross_revenue == second.dre.gross_revenue == Decimal("90.00")


def test_reports_hybrid_query_composes_historical_snapshot_with_live_month(monkeypatch) -> None:
    session, company = _build_company()
    historical = _sample_reports("2025-12-01 a 2025-12-31", "120.00")
    analytics_hybrid.upsert_monthly_snapshot(
        session,
        historical,
        company_id=company.id,
        kind=analytics_hybrid.ANALYTICS_REPORTS_OVERVIEW,
        snapshot_month=date(2025, 12, 1),
    )
    session.commit()
    build_calls = {"count": 0}

    def fake_build(_db, _company, *, start=None, end=None):
        build_calls["count"] += 1
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)
        return _sample_reports("2026-01-01 a 2026-01-31", "80.00")

    monkeypatch.setattr(reports, "build_reports_overview", fake_build)

    result = reports.get_cached_reports_overview(session, company, start=date(2025, 12, 1), end=date(2026, 1, 31))

    assert build_calls["count"] == 1
    assert result.dre.gross_revenue == Decimal("200.00")
    assert result.dro.bank_revenue == Decimal("200.00")


def test_historical_reports_rebuild_updates_persisted_snapshot(monkeypatch) -> None:
    session, company = _build_company()
    monkeypatch.setattr(
        reports,
        "build_reports_overview",
        lambda *_args, **_kwargs: _sample_reports("2025-11-01 a 2025-11-30", "100.00"),
    )

    first = reports.get_cached_reports_overview(session, company, start=date(2025, 11, 1), end=date(2025, 11, 30))
    assert first.dre.gross_revenue == Decimal("100.00")

    analytics_hybrid.enqueue_snapshot_rebuild(
        session,
        company_id=company.id,
        kind=analytics_hybrid.ANALYTICS_REPORTS_OVERVIEW,
        snapshot_month=date(2025, 11, 1),
        reason="historical_change",
    )
    monkeypatch.setattr(
        reports,
        "build_reports_overview",
        lambda *_args, **_kwargs: _sample_reports("2025-11-01 a 2025-11-30", "145.00"),
    )

    rebuilt = analytics_hybrid.process_snapshot_rebuild_queue(session, company, limit=5)
    session.commit()
    result = reports.get_cached_reports_overview(session, company, start=date(2025, 11, 1), end=date(2025, 11, 30))

    assert rebuilt == [(analytics_hybrid.ANALYTICS_REPORTS_OVERVIEW, date(2025, 11, 1))]
    assert result.dre.gross_revenue == Decimal("145.00")

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.cashflow import AccountBalance, CashflowOverview, CashflowPoint
from app.services import cashflow


def _sample_cashflow() -> CashflowOverview:
    return CashflowOverview(
        current_balance=Decimal("100.00"),
        projected_inflows=Decimal("40.00"),
        projected_outflows=Decimal("25.00"),
        planned_purchase_outflows=Decimal("10.00"),
        projected_ending_balance=Decimal("115.00"),
        alerts=[],
        account_balances=[
            AccountBalance(
                account_id="account-1",
                account_name="Conta Principal",
                account_type="checking",
                current_balance=Decimal("100.00"),
            )
        ],
        daily_projection=[
            CashflowPoint(
                reference="2026-04-01",
                opening_balance=Decimal("100.00"),
                crediario_inflows=Decimal("40.00"),
                card_inflows=Decimal("0.00"),
                launched_outflows=Decimal("15.00"),
                planned_purchase_outflows=Decimal("10.00"),
                inflows=Decimal("40.00"),
                outflows=Decimal("25.00"),
                closing_balance=Decimal("115.00"),
            )
        ],
        weekly_projection=[],
        monthly_projection=[],
    )


def test_current_month_cashflow_is_served_from_cache(monkeypatch) -> None:
    cashflow.clear_cashflow_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_cashflow()

    monkeypatch.setattr(cashflow, "_cashflow_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(cashflow, "build_cashflow_overview", fake_build)

    first = cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    second = cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))

    assert build_calls["count"] == 1
    assert first == second


def test_clearing_cashflow_cache_forces_rebuild(monkeypatch) -> None:
    cashflow.clear_cashflow_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_cashflow()

    monkeypatch.setattr(cashflow, "_cashflow_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(cashflow, "build_cashflow_overview", fake_build)

    cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    cashflow.clear_cashflow_overview_cache(company.id)
    cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))

    assert build_calls["count"] == 2


def test_non_month_cashflow_bypasses_cache(monkeypatch) -> None:
    cashflow.clear_cashflow_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_cashflow()

    monkeypatch.setattr(cashflow, "_cashflow_cache_ttl_seconds", lambda *_args, **_kwargs: None)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(cashflow, "build_cashflow_overview", fake_build)

    cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 5), end_date=date(2026, 4, 30))
    cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 5), end_date=date(2026, 4, 30))

    assert build_calls["count"] == 2


def test_cashflow_refresh_forces_rebuild_even_with_live_cache(monkeypatch) -> None:
    cashflow.clear_cashflow_overview_cache()
    build_calls = {"count": 0}
    company = SimpleNamespace(id="company-1")
    overview = _sample_cashflow()

    monkeypatch.setattr(cashflow, "_cashflow_cache_ttl_seconds", lambda *_args, **_kwargs: 120)

    def fake_build(*_args, **_kwargs):
        build_calls["count"] += 1
        return overview.model_copy(deep=True)

    monkeypatch.setattr(cashflow, "build_cashflow_overview", fake_build)

    cashflow.get_cached_cashflow_overview(None, company, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    cashflow.get_cached_cashflow_overview(
        None,
        company,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        refresh=True,
    )

    assert build_calls["count"] == 2

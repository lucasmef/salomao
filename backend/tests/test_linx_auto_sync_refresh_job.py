from __future__ import annotations

from types import SimpleNamespace

from app.jobs import linx_auto_sync_refresh as auto_sync_refresh_job


class _DummySession:
    def __init__(self, company=None) -> None:
        self.company = company

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, model, company_id):
        if self.company and self.company.id == company_id:
            return self.company
        return None



def test_auto_sync_refresh_job_finalizes_refresh_for_successful_runs(monkeypatch) -> None:
    company = SimpleNamespace(id="company-1")
    refresh_calls: list[tuple[object, object]] = []

    monkeypatch.setattr(auto_sync_refresh_job, "SessionLocal", lambda: _DummySession(company=company))
    monkeypatch.setattr(
        auto_sync_refresh_job,
        "run_linx_auto_sync_cycle",
        lambda db, force=False: [
            SimpleNamespace(
                company_id="company-1",
                company_name="Salomao",
                status="success",
                attempted=True,
                inter_statement_message="ok",
                inter_charges_message=None,
                customers_message=None,
                receivables_message=None,
                movements_message=None,
                products_message=None,
                purchase_payables_message=None,
                error_message=None,
            )
        ],
    )
    monkeypatch.setattr(
        auto_sync_refresh_job,
        "finalize_auto_sync_refresh",
        lambda db, current_company: refresh_calls.append((db, current_company)),
    )

    result = auto_sync_refresh_job.main([])

    assert result == 0
    assert refresh_calls == [(_DummySession(company=company), company)]



def test_auto_sync_refresh_job_skips_refresh_for_non_attempted_or_failed_runs(monkeypatch) -> None:
    company = SimpleNamespace(id="company-1")
    refresh_calls: list[tuple[object, object]] = []
    session = _DummySession(company=company)

    monkeypatch.setattr(auto_sync_refresh_job, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        auto_sync_refresh_job,
        "run_linx_auto_sync_cycle",
        lambda db, force=False: [
            SimpleNamespace(
                company_id="company-1",
                company_name="Salomao",
                status="failed",
                attempted=True,
                inter_statement_message=None,
                inter_charges_message=None,
                customers_message=None,
                receivables_message=None,
                movements_message=None,
                products_message=None,
                purchase_payables_message=None,
                error_message="falha total",
            ),
            SimpleNamespace(
                company_id="company-1",
                company_name="Salomao",
                status="before-window",
                attempted=False,
                inter_statement_message=None,
                inter_charges_message=None,
                customers_message=None,
                receivables_message=None,
                movements_message=None,
                products_message=None,
                purchase_payables_message=None,
                error_message=None,
            ),
        ],
    )
    monkeypatch.setattr(
        auto_sync_refresh_job,
        "finalize_auto_sync_refresh",
        lambda db, current_company: refresh_calls.append((db, current_company)),
    )

    result = auto_sync_refresh_job.main([])

    assert result == 1
    assert refresh_calls == []

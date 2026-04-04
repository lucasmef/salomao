from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.security import Company
from app.services.linx_auto_sync import (
    AUTO_SYNC_TIMEZONE,
    run_linx_auto_sync_cycle,
    run_linx_auto_sync_for_company,
)


def _build_session() -> tuple[Session, Company]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    company = Company(
        legal_name="Empresa Teste Ltda",
        trade_name="Salomao",
        linx_auto_sync_enabled=True,
        linx_auto_sync_alert_email="alertas@example.com",
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return session, company


def test_linx_auto_sync_skips_before_22h() -> None:
    session, company = _build_session()

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 21, 0, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is False
        assert result.status == "before-window"
        session.refresh(company)
        assert company.linx_auto_sync_last_run_at is None
    finally:
        session.close()


def test_linx_auto_sync_runs_both_reports_and_updates_status(monkeypatch) -> None:
    session, company = _build_session()
    captured: dict[str, object] = {}

    def _capture_backup(source: str) -> str:
        return str(captured.setdefault("backup", source))

    def _sales_ok(db, current_company, *, target_date):
        return (
            "Faturamento Linx importado com sucesso. "
            "3 dia(s) existentes foram sobrescritos. "
            f"{target_date.isoformat()}:{current_company.id}"
        )

    def _receivables_ok(db, current_company, *, target_date):
        return (
            "Faturas a receber importadas com sucesso. "
            "12 registro(s) antigos de cobranca foram sobrescritos. "
            f"{target_date.isoformat()}:{current_company.id}"
        )

    def _purchase_ok(db, current_company):
        return (
            "Faturas de compra do Linx sincronizadas. "
            "2 nota(s) nova(s) analisada(s). "
            "5 fatura(s) nova(s) incluida(s)."
        )

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", _capture_backup)
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_sales_sync",
        _sales_ok,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_receivables_sync",
        _receivables_ok,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_purchase_payables_sync",
        _purchase_ok,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.send_email",
        lambda subject, body, *, recipients=None: captured.setdefault(
            "email",
            (subject, body, recipients),
        ),
    )

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 22, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is True
        assert result.status == "success"
        assert "3 dia(s)" in (result.sales_message or "")
        assert "12 registro(s)" in (result.receivables_message or "")
        assert "5 fatura(s) nova(s)" in (result.purchase_payables_message or "")
        assert result.summary.sales_overwritten_days == 3
        assert result.summary.receivables_overwritten_count == 12
        assert result.summary.purchase_payables_included_count == 5
        assert captured["backup"] == f"linx-auto-sync:{company.id}"
        email_subject, email_body, email_recipients = captured["email"]
        assert email_recipients == ["alertas@example.com"]
        assert "Dias alterados pelo faturamento: 3" in email_body
        assert "Faturas a receber alteradas: 12" in email_body
        assert "Faturas de compra incluidas: 5" in email_body
        assert "Status: success" in email_body
        assert "Resumo da sincronizacao automatica" in email_subject
        session.refresh(company)
        assert company.linx_auto_sync_last_status == "success"
        assert company.linx_auto_sync_last_error is None
        assert company.linx_auto_sync_last_run_at is not None
    finally:
        session.close()


def test_linx_auto_sync_sends_email_and_marks_partial_failure(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_sales_sync",
        lambda db, current_company, *, target_date: (
            "Faturamento Linx importado com sucesso. "
            "2 dia(s) existentes foram sobrescritos."
        ),
    )

    def _fail_receivables(db, current_company, *, target_date):
        raise ValueError("senha expirou no Linx")

    monkeypatch.setattr("app.services.linx_auto_sync._run_receivables_sync", _fail_receivables)
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_purchase_payables_sync",
        lambda db, current_company: (
            "Faturas de compra do Linx sincronizadas. "
            "1 nota(s) nova(s) analisada(s). "
            "4 fatura(s) nova(s) incluida(s)."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.send_email",
        lambda subject, body, *, recipients=None: email_calls.append((subject, body, recipients)),
    )

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 22, 10, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is True
        assert result.status == "partial_failure"
        assert result.error_message == "Faturas a receber: senha expirou no Linx"
        assert result.summary.sales_overwritten_days == 2
        assert result.summary.receivables_overwritten_count == 0
        assert result.summary.purchase_payables_included_count == 4
        assert len(email_calls) == 1
        assert email_calls[0][2] == ["alertas@example.com"]
        assert "senha expirou no Linx" in email_calls[0][1]
        assert "Dias alterados pelo faturamento: 2" in email_calls[0][1]
        assert "Faturas a receber alteradas: 0" in email_calls[0][1]
        assert "Faturas de compra incluidas: 4" in email_calls[0][1]
        session.refresh(company)
        assert company.linx_auto_sync_last_status == "partial_failure"
        assert company.linx_auto_sync_last_error == "Faturas a receber: senha expirou no Linx"
        assert company.linx_auto_sync_last_run_at is not None

        second_attempt = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 23, 0, tzinfo=AUTO_SYNC_TIMEZONE),
        )
        assert second_attempt.attempted is False
        assert second_attempt.status == "already-ran"
    finally:
        session.close()


def test_linx_auto_sync_cycle_force_runs_disabled_company(monkeypatch) -> None:
    session, company = _build_session()
    company.linx_auto_sync_enabled = False
    session.commit()

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_sales_sync",
        lambda db, current_company, *, target_date: "sales ok",
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_receivables_sync",
        lambda db, current_company, *, target_date: "receivables ok",
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._run_purchase_payables_sync",
        lambda db, current_company: (
            "Faturas de compra do Linx sincronizadas. "
            "0 nota(s) nova(s) analisada(s). "
            "0 fatura(s) nova(s) incluida(s)."
        ),
    )
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        runs = run_linx_auto_sync_cycle(
            session,
            now=datetime(2026, 4, 4, 9, 0, tzinfo=AUTO_SYNC_TIMEZONE),
            force=True,
        )
        assert len(runs) == 1
        assert runs[0].attempted is True
        assert runs[0].status == "success"
    finally:
        session.close()

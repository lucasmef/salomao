from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.security import Company
from app.services.linx_auto_sync import (
    AUTO_SYNC_TIMEZONE,
    LINX_PRODUCTS_SOURCE,
    run_linx_auto_sync_cycle,
    run_linx_auto_sync_for_company,
)
from app.services.purchase_planning import LINX_PURCHASE_PAYABLES_API_SOURCE


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


def _result(message: str, batch_id: str = "batch-1") -> SimpleNamespace:
    return SimpleNamespace(batch=SimpleNamespace(id=batch_id), message=message)


def test_linx_auto_sync_skips_before_6h() -> None:
    session, company = _build_session()

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 5, 59, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is False
        assert result.status == "before-window"
        session.refresh(company)
        assert company.linx_auto_sync_last_run_at is None
    finally:
        session.close()


def test_linx_auto_sync_runs_api_syncs_and_suppresses_success_email(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result(
            "Clientes/fornecedores Linx sincronizados com sucesso. 2 novo(s), 3 atualizado(s) e 4 sem alteracao."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result(
            "Movimentos Linx sincronizados com sucesso. 4 novo(s), 1 atualizado(s) e 0 removido(s).",
            batch_id="mov-batch",
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._count_touched_purchase_movements",
        lambda db, *, company_id, batch_id: 2,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_products",
        lambda db, current_company: _result(
            "Produtos Linx sincronizados com sucesso. 1 novo(s), 5 atualizado(s) e 0 sem alteracao."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result(
            "Faturas a receber Linx sincronizadas com sucesso. 6 nova(s), 2 atualizada(s) e 1 removida(s) da base aberta."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: _result(
            "Faturas de compra via API Linx sincronizadas. 1 fatura(s) nova(s) incluida(s)."
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
            now=datetime(2026, 4, 4, 10, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is True
        assert result.status == "success"
        assert result.summary.customers_changed_count == 5
        assert result.summary.movements_changed_count == 5
        assert result.summary.products_changed_count == 6
        assert result.summary.receivables_changed_count == 9
        assert result.products_message is not None
        assert email_calls == []
        session.refresh(company)
        assert company.linx_auto_sync_last_status == "success"
        assert company.linx_auto_sync_last_error is None
        assert company.linx_auto_sync_last_run_at is not None
    finally:
        session.close()


def test_linx_auto_sync_sends_email_only_when_error_occurs(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result(
            "Clientes/fornecedores Linx sincronizados com sucesso. 1 novo(s), 0 atualizado(s) e 0 sem alteracao."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result(
            "Movimentos Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 0 removido(s).",
            batch_id="mov-batch",
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._should_run_products_now",
        lambda *args, **kwargs: False,
    )

    def _fail_receivables(db, current_company):
        raise ValueError("chave API expirada")

    monkeypatch.setattr("app.services.linx_auto_sync.sync_linx_open_receivables", _fail_receivables)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: _result("purchase payables ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.send_email",
        lambda subject, body, *, recipients=None: email_calls.append((subject, body, recipients)),
    )

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 10, 10, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is True
        assert result.status == "partial_failure"
        assert result.error_message == "Faturas a receber: chave API expirada"
        assert len(email_calls) == 1
        assert email_calls[0][2] == ["alertas@example.com"]
        assert "chave API expirada" in email_calls[0][1]
        session.refresh(company)
        assert company.linx_auto_sync_last_status == "partial_failure"
        assert company.linx_auto_sync_last_error == "Faturas a receber: chave API expirada"
    finally:
        session.close()


def test_linx_auto_sync_product_daily_sync_runs_once_per_day(monkeypatch) -> None:
    session, company = _build_session()
    session.add(
        ImportBatch(
            company_id=company.id,
            source_type=LINX_PRODUCTS_SOURCE,
            filename="linx-products-incremental.xml",
            status="processed",
            created_at=datetime(2026, 4, 4, 11, 0, tzinfo=timezone.utc),
        )
    )
    session.commit()

    product_calls: list[str] = []
    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result("Clientes/fornecedores Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 1 sem alteracao."),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result(
            "Movimentos Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 0 removido(s).",
            batch_id="mov-batch",
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._count_touched_purchase_movements",
        lambda db, *, company_id, batch_id: 0,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_products",
        lambda db, current_company: product_calls.append(current_company.id) or _result(
            "Produtos Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 1 sem alteracao."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result(
            "Faturas a receber Linx sincronizadas com sucesso. 0 nova(s), 0 atualizada(s) e 0 removida(s) da base aberta."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: _result("purchase payables ok"),
    )
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 10, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.status == "success"
        assert product_calls == []
        assert result.products_message is None
    finally:
        session.close()


def test_linx_auto_sync_purchase_payables_daily_sync_runs_once_per_day_without_new_purchase_activity(
    monkeypatch,
) -> None:
    session, company = _build_session()
    session.add(
        ImportBatch(
            company_id=company.id,
            source_type=LINX_PURCHASE_PAYABLES_API_SOURCE,
            filename="linx-purchase-payables-incremental.xml",
            status="processed",
            created_at=datetime(2026, 4, 4, 13, 0, tzinfo=timezone.utc),
        )
    )
    session.commit()

    purchase_payables_calls: list[str] = []
    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result("Clientes/fornecedores Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 1 sem alteracao."),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result(
            "Movimentos Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 0 removido(s).",
            batch_id="mov-batch",
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._count_touched_purchase_movements",
        lambda db, *, company_id, batch_id: 0,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._should_run_products_now",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result(
            "Faturas a receber Linx sincronizadas com sucesso. 0 nova(s), 0 atualizada(s) e 0 removida(s) da base aberta."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: purchase_payables_calls.append(current_company.id) or _result(
            "Faturas de compra via API Linx sincronizadas. 0 fatura(s) nova(s) incluida(s)."
        ),
    )
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 15, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.status == "success"
        assert purchase_payables_calls == []
        assert result.purchase_payables_message is None
    finally:
        session.close()


def test_linx_auto_sync_purchase_payables_runs_again_when_new_purchase_activity_is_found(
    monkeypatch,
) -> None:
    session, company = _build_session()
    session.add(
        ImportBatch(
            company_id=company.id,
            source_type=LINX_PURCHASE_PAYABLES_API_SOURCE,
            filename="linx-purchase-payables-incremental.xml",
            status="processed",
            created_at=datetime(2026, 4, 4, 13, 0, tzinfo=timezone.utc),
        )
    )
    session.commit()

    purchase_payables_calls: list[str] = []
    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result("Clientes/fornecedores Linx sincronizados com sucesso. 0 novo(s), 0 atualizado(s) e 1 sem alteracao."),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result(
            "Movimentos Linx sincronizados com sucesso. 1 novo(s), 0 atualizado(s) e 0 removido(s).",
            batch_id="mov-batch",
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._count_touched_purchase_movements",
        lambda db, *, company_id, batch_id: 1,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._should_run_products_now",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result(
            "Faturas a receber Linx sincronizadas com sucesso. 0 nova(s), 0 atualizada(s) e 0 removida(s) da base aberta."
        ),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: purchase_payables_calls.append(current_company.id) or _result(
            "Faturas de compra via API Linx sincronizadas. 1 fatura(s) nova(s) incluida(s)."
        ),
    )
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 4, 15, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.status == "success"
        assert purchase_payables_calls == [company.id]
        assert result.purchase_payables_message is not None
    finally:
        session.close()


def test_linx_auto_sync_cycle_force_runs_disabled_company(monkeypatch) -> None:
    session, company = _build_session()
    company.linx_auto_sync_enabled = False
    session.commit()

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result("customers ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result("movements ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._count_touched_purchase_movements",
        lambda db, *, company_id, batch_id: 0,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_products",
        lambda db, current_company: _result("products ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result("receivables ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: _result("purchase payables ok"),
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


def test_linx_auto_sync_scheduled_run_still_happens_if_previous_force_was_in_earlier_hour(
    monkeypatch,
) -> None:
    session, company = _build_session()
    company.linx_auto_sync_last_run_at = datetime(2026, 4, 5, 9, 15, tzinfo=AUTO_SYNC_TIMEZONE)
    session.commit()

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_customers",
        lambda db, current_company: _result("customers ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_movements",
        lambda db, current_company: _result("movements ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync._should_run_products_now",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_open_receivables",
        lambda db, current_company: _result("receivables ok"),
    )
    monkeypatch.setattr(
        "app.services.linx_auto_sync.sync_linx_purchase_payables",
        lambda db, current_company, actor_user=None: _result("purchase payables ok"),
    )
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 5, 10, 5, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is True
        assert result.status == "success"
        session.refresh(company)
        assert company.linx_auto_sync_last_run_at is not None
        assert company.linx_auto_sync_last_run_at.replace(tzinfo=AUTO_SYNC_TIMEZONE) == datetime(
            2026, 4, 5, 10, 5, tzinfo=AUTO_SYNC_TIMEZONE
        )
    finally:
        session.close()


def test_linx_auto_sync_still_skips_second_run_in_same_hour(monkeypatch) -> None:
    session, company = _build_session()
    company.linx_auto_sync_last_run_at = datetime(2026, 4, 5, 10, 1, tzinfo=AUTO_SYNC_TIMEZONE)
    session.commit()

    monkeypatch.setattr("app.services.linx_auto_sync.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr("app.services.linx_auto_sync.send_email", lambda *args, **kwargs: None)

    try:
        result = run_linx_auto_sync_for_company(
            session,
            company,
            now=datetime(2026, 4, 5, 10, 55, tzinfo=AUTO_SYNC_TIMEZONE),
        )

        assert result.attempted is False
        assert result.status == "already-ran"
    finally:
        session.close()

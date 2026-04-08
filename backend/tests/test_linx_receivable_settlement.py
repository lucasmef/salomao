from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.boleto import BoletoRecord
from app.db.models.linx import LinxOpenReceivable
from app.db.models.security import Company
from app.services.boletos import normalize_text
from app.services.linx_receivable_settlement import (
    LinxSettlementInvoiceResult,
    _client_names_match,
    _page_matches_due_date,
    settle_paid_pending_inter_receivables,
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
        linx_auto_sync_alert_email="financeiro@example.com",
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return session, company


def test_settle_paid_pending_inter_receivables_removes_open_receivable_and_sends_email(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    session.add(
        LinxOpenReceivable(
            company_id=company.id,
            linx_code=56418,
            customer_code=10,
            customer_name="MARIA APARECIDA",
            issue_date=datetime(2026, 4, 1, 0, 0, 0),
            due_date=datetime(2026, 4, 10, 0, 0, 0),
            amount=Decimal("170.50"),
            paid_amount=Decimal("0"),
        )
    )
    session.add(
        BoletoRecord(
            company_id=company.id,
            bank="INTER",
            client_key=normalize_text("MARIA APARECIDA"),
            client_name="MARIA APARECIDA",
            document_id="56418",
            issue_date=date(2026, 4, 1),
            due_date=date(2026, 4, 10),
            amount=Decimal("170.50"),
            paid_amount=Decimal("170.50"),
            status="Recebido por boleto",
            inter_codigo_solicitacao="SOL-56418",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates: [
            LinxSettlementInvoiceResult(
                client_name=candidates[0].client_name,
                boleto_amount=candidates[0].boleto_amount,
                invoice_number=candidates[0].receivables[0].invoice_number,
                due_date=candidates[0].receivables[0].due_date,
                amount=Decimal(candidates[0].receivables[0].amount),
                success=True,
                message="A fatura 56418 foi baixada com sucesso.",
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.linx_receivable_settlement.send_email",
        lambda subject, body, *, recipients=None: email_calls.append((subject, body, recipients)),
    )

    try:
        summary = settle_paid_pending_inter_receivables(session, company)

        assert summary.attempted_invoice_count == 1
        assert summary.settled_invoice_count == 1
        assert summary.failed_invoice_count == 0
        assert summary.client_count == 1
        assert email_calls[0][2] == ["financeiro@example.com"]
        assert "MARIA APARECIDA pagou boleto no valor R$ 170,50 referente a faturas 56418" in email_calls[0][1]
        assert "total de faturas baixadas: 1" in email_calls[0][1]
        assert session.scalar(select(LinxOpenReceivable.id).where(LinxOpenReceivable.company_id == company.id)) is None
    finally:
        session.close()


def test_settle_paid_pending_inter_receivables_respects_charge_code_filter(monkeypatch) -> None:
    session, company = _build_session()

    session.add(
        LinxOpenReceivable(
            company_id=company.id,
            linx_code=777,
            customer_code=10,
            customer_name="CLIENTE TESTE",
            issue_date=datetime(2026, 4, 1, 0, 0, 0),
            due_date=datetime(2026, 4, 10, 0, 0, 0),
            amount=Decimal("99.90"),
            paid_amount=Decimal("0"),
        )
    )
    session.add(
        BoletoRecord(
            company_id=company.id,
            bank="INTER",
            client_key=normalize_text("CLIENTE TESTE"),
            client_name="CLIENTE TESTE",
            document_id="777",
            issue_date=date(2026, 4, 1),
            due_date=date(2026, 4, 10),
            amount=Decimal("99.90"),
            paid_amount=Decimal("99.90"),
            status="Recebido por boleto",
            inter_codigo_solicitacao="SOL-777",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates: (_ for _ in ()).throw(AssertionError("nao deveria executar")),
    )

    try:
        summary = settle_paid_pending_inter_receivables(
            session,
            company,
            filter_charge_codes={"SOL-OUTRO"},
        )

        assert summary.attempted_invoice_count == 0
        assert summary.settled_invoice_count == 0
        assert summary.failed_invoice_count == 0
    finally:
        session.close()


def test_client_name_match_ignores_accents_and_requires_overlap() -> None:
    assert _client_names_match(
        "MARIA APARECIDA BITENCOURT FORTUNATO DE SOUZA",
        "MARIA APARECIDA BITENCOURT FORTUNATO DE SOUZA",
    )
    assert _client_names_match(
        "ROSANA CAMILO DA ROSA",
        "ROSANA CAMILO ROSA",
    )
    assert not _client_names_match(
        "MARIA APARECIDA BITENCOURT FORTUNATO DE SOUZA",
        "JOAO SILVA",
    )


def test_page_matches_due_date_from_body_text() -> None:
    class _BodyLocator:
        def __init__(self, text: str) -> None:
            self._text = text

        def count(self) -> int:
            return 1

        @property
        def first(self) -> "_BodyLocator":
            return self

        def inner_text(self) -> str:
            return self._text

    class _Page:
        def locator(self, selector: str) -> _BodyLocator:
            return _BodyLocator("Cliente: MARIA APARECIDA Vencimento: 10/04/2026 Valor Pago (R$): 170,50")

    page = _Page()
    assert _page_matches_due_date(
        page,
        expected_due_date=date(2026, 4, 10),
        normalized_body="CLIENTE MARIA APARECIDA VENCIMENTO 10/04/2026 VALOR PAGO 170,50",
    )

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.boleto import BoletoRecord
from app.db.models.linx import LinxOpenReceivable
from app.db.models.security import Company
from app.schemas.boletos import BoletoMatchItem, BoletoReceivableRead, BoletoRecordRead
from app.services.boletos import normalize_text
from app.services.linx_receivable_settlement import (
    LinxSettlementInvoiceResult,
    _build_settlement_candidates,
    _build_success_email,
    _client_names_match,
    _install_dialog_auto_accept,
    _open_receivable_settlement_target,
    _page_mentions_invoice,
    _page_matches_due_date,
    _parse_brl_amount,
    _prepare_receivable_lookup_target,
    _validate_receivable_confirmation_context,
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


@pytest.fixture(autouse=True)
def _configure_email_transport(monkeypatch):
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("SMTP_HOST", "mail.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "alerts@example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
            payment_date=date(2026, 4, 11),
            amount=Decimal("170.50"),
            paid_amount=Decimal("170.50"),
            status="Recebido por boleto",
            inter_codigo_solicitacao="SOL-56418",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates, validate_only=False: [
            LinxSettlementInvoiceResult(
                client_name=candidates[0].client_name,
                boleto_amount=candidates[0].boleto_amount,
                boleto_due_dates=candidates[0].boleto_due_dates,
                payment_dates=candidates[0].payment_dates,
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
        lambda subject, body, *, recipients=None, html_body=None: email_calls.append((subject, body, recipients, html_body)),
    )

    try:
        summary = settle_paid_pending_inter_receivables(session, company)

        assert summary.attempted_invoice_count == 1
        assert summary.settled_invoice_count == 1
        assert summary.failed_invoice_count == 0
        assert summary.client_count == 1
        assert email_calls[0][2] == ["financeiro@example.com"]
        assert "MARIA APARECIDA pagou boleto no valor R$ 170,50 referente a faturas 56418" in email_calls[0][1]
        assert "Vencimento do boleto: 10/04/2026" in email_calls[0][1]
        assert "Data do pagamento: 11/04/2026" in email_calls[0][1]
        assert "Total de faturas baixadas: 1 fatura(s) | R$ 170,50" in email_calls[0][1]
        assert "<table" in (email_calls[0][3] or "")
        assert session.scalar(select(LinxOpenReceivable.id).where(LinxOpenReceivable.company_id == company.id)) is None
    finally:
        session.close()


def test_settle_paid_pending_inter_receivables_reports_disabled_email_transport(monkeypatch) -> None:
    session, company = _build_session()

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
            payment_date=date(2026, 4, 11),
            amount=Decimal("170.50"),
            paid_amount=Decimal("170.50"),
            status="Recebido por boleto",
            inter_codigo_solicitacao="SOL-56418",
        )
    )
    session.commit()

    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "false")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SECURITY_ALERT_EMAIL_FROM", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates, validate_only=False: [
            LinxSettlementInvoiceResult(
                client_name=candidates[0].client_name,
                boleto_amount=candidates[0].boleto_amount,
                boleto_due_dates=candidates[0].boleto_due_dates,
                payment_dates=candidates[0].payment_dates,
                invoice_number=candidates[0].receivables[0].invoice_number,
                due_date=candidates[0].receivables[0].due_date,
                amount=Decimal(candidates[0].receivables[0].amount),
                success=True,
                message="A fatura 56418 foi baixada com sucesso.",
            )
        ],
    )

    try:
        summary = settle_paid_pending_inter_receivables(session, company)

        assert summary.attempted_invoice_count == 1
        assert summary.settled_invoice_count == 1
        assert summary.email_error == "Envio de email desabilitado em SECURITY_ALERT_EMAIL_ENABLED."
    finally:
        get_settings.cache_clear()
        session.close()


def test_settle_paid_pending_inter_receivables_supports_c6_filter(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    session.add(
        LinxOpenReceivable(
            company_id=company.id,
            linx_code=88001,
            customer_code=11,
            customer_name="CLIENTE C6",
            issue_date=datetime(2026, 4, 1, 0, 0, 0),
            due_date=datetime(2026, 4, 10, 0, 0, 0),
            amount=Decimal("250.00"),
            paid_amount=Decimal("0"),
        )
    )
    session.add(
        BoletoRecord(
            company_id=company.id,
            bank="C6",
            client_key=normalize_text("CLIENTE C6"),
            client_name="CLIENTE C6",
            document_id="88001",
            issue_date=date(2026, 4, 1),
            due_date=date(2026, 4, 10),
            payment_date=date(2026, 4, 11),
            amount=Decimal("250.00"),
            paid_amount=Decimal("250.00"),
            status="Pago",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates, validate_only=False: [
            LinxSettlementInvoiceResult(
                client_name=candidates[0].client_name,
                boleto_amount=candidates[0].boleto_amount,
                boleto_due_dates=candidates[0].boleto_due_dates,
                payment_dates=candidates[0].payment_dates,
                invoice_number=candidates[0].receivables[0].invoice_number,
                due_date=candidates[0].receivables[0].due_date,
                amount=Decimal(candidates[0].receivables[0].amount),
                success=True,
                message="A fatura 88001 foi baixada com sucesso.",
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.linx_receivable_settlement.send_email",
        lambda subject, body, *, recipients=None, html_body=None: email_calls.append((subject, body, recipients, html_body)),
    )

    try:
        summary = settle_paid_pending_inter_receivables(
            session,
            company,
            filter_banks={"C6"},
        )

        assert summary.attempted_invoice_count == 1
        assert summary.settled_invoice_count == 1
        assert summary.failed_invoice_count == 0
        assert summary.client_count == 1
        assert email_calls[0][2] == ["financeiro@example.com"]
        assert "CLIENTE C6 pagou boleto no valor R$ 250,00 referente a faturas 88001" in email_calls[0][1]
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
            payment_date=date(2026, 4, 11),
            amount=Decimal("99.90"),
            paid_amount=Decimal("99.90"),
            status="Recebido por boleto",
            inter_codigo_solicitacao="SOL-777",
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._settle_candidates_in_portal",
        lambda current_company, candidates, validate_only=False: (_ for _ in ()).throw(AssertionError("nao deveria executar")),
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


def test_page_mentions_invoice_accepts_numero_fatura_empresa_pattern() -> None:
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

    class _EmptyLocator:
        def count(self) -> int:
            return 0

        @property
        def first(self) -> "_EmptyLocator":
            return self

    class _Page:
        def locator(self, selector: str):
            if selector == "body":
                return _BodyLocator("Numero da fatura/Empresa:\t53615/1")
            return _EmptyLocator()

    assert _page_mentions_invoice(
        _Page(),
        invoice_number="53615",
        normalized_body="NUMERO DA FATURA/EMPRESA: 53615/1",
    )


def test_validate_receivable_confirmation_context_ignores_previous_open_warning_when_other_data_match() -> None:
    values = {
        "input[name='f_valorfatura']": "170,50",
        "input[name='cliente']": "MARIANA DAMIAN SILVESTRE",
        "input[name='data_vencimento']": "10/04/2026",
    }
    body_text = (
        "Existe(m) fatura(s) em aberto deste cliente com vencimento anterior a esta "
        "Numero da fatura/Empresa: 53615/1 "
        "Cliente: MARIANA DAMIAN SILVESTRE "
        "Vencimento: 10/04/2026 "
        "Valor da Fatura: 170,50"
    )

    class _Locator:
        def __init__(self, value: str = "", *, text: str | None = None, exists: bool = True) -> None:
            self._value = value
            self._text = text if text is not None else value
            self._exists = exists

        def count(self) -> int:
            return 1 if self._exists else 0

        @property
        def first(self) -> "_Locator":
            return self

        def input_value(self) -> str:
            return self._value

        def inner_text(self) -> str:
            return self._text

        def text_content(self) -> str:
            return self._text

    class _Page:
        def locator(self, selector: str) -> _Locator:
            if selector == "body":
                return _Locator(text=body_text)
            if selector in values:
                return _Locator(values[selector])
            return _Locator(exists=False)

    _validate_receivable_confirmation_context(
        _Page(),
        invoice_number="53615",
        expected_client_name="MARIANA DAMIAN SILVESTRE",
        expected_due_date=date(2026, 4, 10),
        expected_amount=Decimal("170.50"),
    )


def test_install_dialog_auto_accept_registers_dialog_handler() -> None:
    registered: dict[str, object] = {}

    class _Dialog:
        def __init__(self) -> None:
            self.accepted = False

        def accept(self) -> None:
            self.accepted = True

    class _Page:
        def on(self, event_name: str, handler) -> None:
            registered[event_name] = handler

    page = _Page()
    _install_dialog_auto_accept(page)

    assert "dialog" in registered
    dialog = _Dialog()
    registered["dialog"](dialog)
    assert dialog.accepted is True


def test_prepare_receivable_lookup_target_retries_when_invoice_field_is_missing(monkeypatch) -> None:
    class _Page:
        def __init__(self) -> None:
            self.wait_calls: list[int] = []

        def wait_for_timeout(self, value: int) -> None:
            self.wait_calls.append(value)

    page = _Page()
    opened_targets = ["segundo"]
    fill_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._open_receivable_settlement_target",
        lambda current_page, *, root_url: opened_targets.pop(0),
    )

    def fake_fill(target, selectors, value):
        fill_calls.append((target, value))
        if target == "primeiro":
            raise ValueError("Nao foi possivel localizar o campo 'Numero da fatura' no Linx.")

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._fill_first_matching_locator",
        fake_fill,
    )

    retried_target = _prepare_receivable_lookup_target(
        page,
        root_url="https://linx.example.test",
        target="primeiro",
        lookup_invoice="55048",
    )

    assert retried_target == "segundo"
    assert fill_calls == [("primeiro", "55048"), ("segundo", "55048")]
    assert page.wait_calls == [800]


def test_open_receivable_settlement_target_prefers_direct_navigation_when_invoice_field_exists(monkeypatch) -> None:
    class _Page:
        def __init__(self) -> None:
            self.goto_calls: list[tuple[str, str]] = []
            self.wait_calls: list[int] = []

        def goto(self, url: str, *, wait_until: str) -> None:
            self.goto_calls.append((url, wait_until))

        def wait_for_timeout(self, value: int) -> None:
            self.wait_calls.append(value)

    page = _Page()

    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._wait_for_page_idle",
        lambda current_page: None,
    )
    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._raise_if_permission_denied",
        lambda current_target: None,
    )
    monkeypatch.setattr(
        "app.services.linx_receivable_settlement._find_first_locator",
        lambda current_page, selectors: object(),
    )

    target = _open_receivable_settlement_target(page, root_url="https://linx.example.test")

    assert target is page
    assert page.goto_calls == [
        (
            "https://linx.example.test/gestor_web/financeiro/baixa_faturas.asp?tipolanc=receber",
            "domcontentloaded",
        )
    ]
    assert page.wait_calls == [1_000]


def test_build_settlement_candidates_sorts_clients_and_receivables_by_oldest_due_date() -> None:
    items = [
        BoletoMatchItem(
            selection_key="abril",
            client_key="PRISCILA",
            type="agrupado",
            client_name="PRISCILA TARTARI",
            mode="mensal",
            due_date=date(2026, 4, 1),
            status="Pago sem baixa",
            amount=Decimal("200.00"),
            reason="teste",
            receivable_count=1,
            bank="INTER",
            receivables=[
                BoletoReceivableRead(
                    client_name="PRISCILA TARTARI",
                    invoice_number="55233",
                    installment="004/004",
                    due_date=date(2026, 4, 1),
                    amount=Decimal("200.00"),
                    corrected_amount=Decimal("200.00"),
                    document="257/D",
                    status="Em aberto",
                )
            ],
            boletos=[],
        ),
        BoletoMatchItem(
            selection_key="marco",
            client_key="PRISCILA",
            type="agrupado",
            client_name="PRISCILA TARTARI",
            mode="mensal",
            due_date=date(2026, 3, 1),
            status="Pago sem baixa",
            amount=Decimal("100.00"),
            reason="teste",
            receivable_count=2,
            bank="INTER",
            receivables=[
                BoletoReceivableRead(
                    client_name="PRISCILA TARTARI",
                    invoice_number="55380",
                    installment="003/004",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("60.00"),
                    corrected_amount=Decimal("60.00"),
                    document="269/D",
                    status="Em aberto",
                ),
                BoletoReceivableRead(
                    client_name="PRISCILA TARTARI",
                    invoice_number="55232",
                    installment="003/004",
                    due_date=date(2026, 3, 1),
                    amount=Decimal("50.00"),
                    corrected_amount=Decimal("50.00"),
                    document="257/D",
                    status="Em aberto",
                ),
            ],
            boletos=[
                BoletoRecordRead(
                    id="boleto-marco",
                    bank="INTER",
                    client_name="PRISCILA TARTARI",
                    document_id="2026-03",
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 20),
                    payment_date=date(2026, 3, 21),
                    amount=Decimal("110.00"),
                    paid_amount=Decimal("110.00"),
                    status="Recebido por boleto",
                    inter_codigo_solicitacao="SOL-PRI-1",
                    inter_account_id="acc-1",
                    pdf_available=True,
                )
            ],
        ),
    ]

    candidates, failures = _build_settlement_candidates(items, filter_charge_codes=None, filter_banks={"INTER"})

    assert failures == []
    assert [candidate.invoice_numbers for candidate in candidates] == [
        ("55232", "55380"),
        ("55233",),
    ]
    assert candidates[0].boleto_due_dates == (date(2026, 3, 20),)
    assert candidates[0].payment_dates == (date(2026, 3, 21),)


def test_build_settlement_candidates_blocks_duplicate_invoice_amounts_per_client() -> None:
    items = [
        BoletoMatchItem(
            selection_key="dup",
            client_key="CLIENTE",
            type="agrupado",
            client_name="CLIENTE DUPLICADO",
            mode="mensal",
            due_date=date(2026, 3, 1),
            status="Pago sem baixa",
            amount=Decimal("200.00"),
            reason="teste",
            receivable_count=2,
            bank="INTER",
            receivables=[
                BoletoReceivableRead(
                    client_name="CLIENTE DUPLICADO",
                    invoice_number="1001",
                    installment="001/002",
                    due_date=date(2026, 3, 1),
                    amount=Decimal("100.00"),
                    corrected_amount=Decimal("100.00"),
                    document="DOC-1",
                    status="Em aberto",
                ),
                BoletoReceivableRead(
                    client_name="CLIENTE DUPLICADO",
                    invoice_number="1002",
                    installment="002/002",
                    due_date=date(2026, 3, 5),
                    amount=Decimal("100.00"),
                    corrected_amount=Decimal("100.00"),
                    document="DOC-2",
                    status="Em aberto",
                ),
            ],
            boletos=[
                BoletoRecordRead(
                    id="boleto-dup",
                    bank="INTER",
                    client_name="CLIENTE DUPLICADO",
                    document_id="2026-03",
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 20),
                    payment_date=date(2026, 3, 21),
                    amount=Decimal("200.00"),
                    paid_amount=Decimal("200.00"),
                    status="Recebido por boleto",
                    inter_codigo_solicitacao="SOL-DUP",
                    inter_account_id="acc-1",
                    pdf_available=True,
                )
            ],
        )
    ]

    candidates, failures = _build_settlement_candidates(items, filter_charge_codes=None, filter_banks={"INTER"})

    assert candidates == []
    assert len(failures) == 2
    assert {item.invoice_number for item in failures} == {"1001", "1002"}
    assert all("mais de uma fatura com o mesmo valor" in item.message for item in failures)


def test_parse_brl_amount_accepts_integer_values_from_hidden_linx_fields() -> None:
    assert _parse_brl_amount("195") == Decimal("195.00")


def test_parse_brl_amount_accepts_single_decimal_digit_from_linx_inputs() -> None:
    assert _parse_brl_amount("29,8") == Decimal("29.80")


def test_parse_brl_amount_accepts_thousands_without_decimal_part() -> None:
    assert _parse_brl_amount("1.234") == Decimal("1234.00")


def test_build_success_email_includes_quantity_and_value_totals_and_html_tables() -> None:
    company = Company(legal_name="Empresa Teste Ltda", trade_name="Salomao")
    results = [
        LinxSettlementInvoiceResult(
            client_name="Cliente Exemplo",
            boleto_amount=Decimal("300.00"),
            boleto_due_dates=(date(2026, 4, 20),),
            payment_dates=(date(2026, 4, 21),),
            invoice_number="1001",
            due_date=date(2026, 4, 10),
            amount=Decimal("100.00"),
            success=True,
            message="ok",
            group_token="grupo-1",
        ),
        LinxSettlementInvoiceResult(
            client_name="Cliente Exemplo",
            boleto_amount=Decimal("300.00"),
            boleto_due_dates=(date(2026, 4, 20),),
            payment_dates=(date(2026, 4, 21),),
            invoice_number="1002",
            due_date=date(2026, 4, 20),
            amount=Decimal("200.00"),
            success=True,
            message="ok",
            group_token="grupo-1",
        ),
    ]

    subject, body, html_body = _build_success_email(company, results)

    assert subject == "[Linx] Baixa automatica de faturas - Salomao"
    assert "Vencimento do boleto: 20/04/2026" in body
    assert "Data do pagamento: 21/04/2026" in body
    assert "Total do cliente Cliente Exemplo: 2 fatura(s) | R$ 300,00" in body
    assert "Total de faturas baixadas: 2 fatura(s) | R$ 300,00" in body
    assert "<table" in html_body
    assert "Data do pagamento" in html_body
    assert "Valor total" in html_body
    assert "Cliente Exemplo" in html_body

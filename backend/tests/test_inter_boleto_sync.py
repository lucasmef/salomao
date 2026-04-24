from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord, StandaloneBoletoRecord
from app.db.models.finance import Account
from app.db.models.linx import LinxCustomer, LinxOpenReceivable
from app.db.models.security import Company
from app.services.boletos import normalize_text
from app.services.inter import (
    INTER_CHARGE_FULL_SYNC_DUE_END,
    INTER_CHARGE_FULL_SYNC_START,
    INTER_CHARGE_INCREMENTAL_LOOKBACK_DAYS,
    _build_inter_charge_payload,
    _build_standalone_charge_payload,
    cancel_inter_charge,
    cancel_standalone_inter_charge,
    receive_inter_charge,
    sync_inter_charges,
    sync_standalone_inter_charges,
)
from app.services.linx_receivable_settlement import LinxSettlementSummary


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _build_company_and_account(session: Session) -> tuple[Company, Account]:
    company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste")
    session.add(company)
    session.flush()
    account = Account(
        company_id=company.id,
        name="Inter Matriz",
        account_type="checking",
        bank_code="077",
        account_number="123456",
        inter_api_enabled=True,
        inter_api_key="client-id",
        inter_account_number="123456",
        inter_client_secret_encrypted=encrypt_text("client-secret"),
        inter_certificate_pem_encrypted=encrypt_text("---CERT---"),
        inter_private_key_pem_encrypted=encrypt_text("---KEY---"),
        inter_api_base_url="https://example.test",
    )
    session.add(account)
    session.commit()
    return company, account


def test_sync_inter_charges_updates_existing_record_and_creates_new_one() -> None:
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(
                200,
                json={
                    "cobrancas": [
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-001",
                                "seuNumero": "SEU-001",
                            }
                        },
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-002",
                                "seuNumero": "SEU-002",
                            }
                        },
                    ]
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-001":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-001",
                        "seuNumero": "SEU-001",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2026-03-01",
                        "dataSituacao": "2026-03-10",
                        "dataVencimento": "2026-03-10",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "250.00",
                        "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                    "pix": {
                        "pixCopiaECola": "PIX-COLA-1",
                        "txid": "TXID-1",
                    },
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-002":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-002",
                        "seuNumero": "SEU-002",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-03-02",
                        "dataVencimento": "2026-03-12",
                        "valorNominal": "199.90",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Exemplo Novo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "999888777",
                        "linhaDigitavel": "999.888.777",
                        "nossoNumero": "NOSSO-2",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Exemplo"),
                client_name="Cliente Exemplo",
                document_id="SEU-001",
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 10),
                amount=Decimal("250.00"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                barcode="old-barcode",
            )
        )
        session.commit()

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=httpx.MockTransport(handler),
        )

        records = session.query(BoletoRecord).order_by(BoletoRecord.document_id.asc()).all()
        assert len(records) == 2
        assert result.message == "Cobrancas do Inter sincronizadas com sucesso."
        assert result.batch.records_valid == 2
        assert result.batch.source_type == "inter_charge_sync"
        assert "foram atualizadas" in (result.batch.error_summary or "")

        updated = next(item for item in records if item.document_id == "SEU-001")
        created = next(item for item in records if item.document_id == "SEU-002")

        assert updated.status == "Recebido por boleto"
        assert updated.paid_amount == Decimal("250.00")
        assert updated.payment_date == date(2026, 3, 10)
        assert updated.inter_account_id == account.id
        assert updated.inter_codigo_solicitacao == "SOL-001"
        assert updated.linha_digitavel == "111.222.333"
        assert updated.pix_copia_e_cola == "PIX-COLA-1"

        assert created.status == "A receber"
        assert created.amount == Decimal("199.90")
        assert created.payment_date is None
        assert created.inter_account_id == account.id
        assert created.barcode == "999888777"
        assert created.inter_nosso_numero == "NOSSO-2"
    finally:
        session.close()


def test_build_inter_charge_payload_defaults_address_number_to_zero() -> None:
    config = BoletoCustomerConfig(
        company_id="company-1",
        client_key="CLIENTE EXEMPLO",
        client_name="Cliente Exemplo",
        client_code="1001",
        uses_boleto=True,
        mode="individual",
        boleto_due_day=12,
        include_interest=True,
        address_street="Rua Exemplo",
        address_number=None,
        neighborhood="Centro",
        city="Cidade Exemplo",
        state="SC",
        zip_code="99999999",
        tax_id="12345678901",
        mobile="48999990000",
        phone_primary="4833334444",
        phone_secondary="4833335555",
    )
    item = SimpleNamespace(
        client_name="Cliente Exemplo",
        amount=Decimal("250.00"),
        due_date=date(2026, 3, 12),
        type="individual",
        competence=None,
        receivables=[SimpleNamespace(invoice_number="12345")],
        selection_key="boleto-12345",
    )

    payload = _build_inter_charge_payload(item, config, today=date(2026, 3, 1))

    assert payload["pagador"]["numero"] == "0"
    assert "email" not in payload["pagador"]
    assert "ddd" not in payload["pagador"]
    assert "telefone" not in payload["pagador"]


def test_build_standalone_charge_payload_defaults_address_number_to_zero() -> None:
    customer = LinxCustomer(
        company_id="company-1",
        linx_code=1001,
        display_name="Lais de Oliveira Goncalves",
        legal_name="Lais de Oliveira Goncalves",
        document_number="12345678901",
        person_type="F",
        address_street="Rua Exemplo",
        address_number=None,
        neighborhood="Centro",
        city="Cidade Exemplo",
        state="SC",
        zip_code="99999999",
        mobile="48999990000",
        phone_primary="4833334444",
        email="cliente@example.com",
        registration_type="C",
        is_active=True,
    )

    payload = _build_standalone_charge_payload(
        customer=customer,
        amount=Decimal("170.50"),
        due_date=date(2026, 4, 10),
        note="Boleto avulso",
    )

    assert payload["pagador"]["numero"] == "0"
    assert "email" not in payload["pagador"]
    assert "ddd" not in payload["pagador"]
    assert "telefone" not in payload["pagador"]


def test_sync_inter_charges_triggers_linx_settlement_for_processed_codes(monkeypatch) -> None:
    session = _build_session()
    settlement_calls: list[tuple[set[str] | None, set[str] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(
                200,
                json={
                    "cobrancas": [
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-001",
                                "seuNumero": "SEU-001",
                            }
                        }
                    ]
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-001":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-001",
                        "seuNumero": "SEU-001",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2026-03-01",
                        "dataSituacao": "2026-03-10",
                        "dataVencimento": "2026-03-10",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "250.00",
                        "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    monkeypatch.setattr(
        "app.services.inter.settle_paid_pending_inter_receivables",
        lambda db, company, *, filter_charge_codes=None, filter_banks=None: (
            settlement_calls.append(
                (
                    set(filter_charge_codes) if filter_charge_codes is not None else None,
                    set(filter_banks) if filter_banks is not None else None,
                )
            )
            or LinxSettlementSummary(
                attempted_invoice_count=1,
                settled_invoice_count=1,
                failed_invoice_count=0,
                client_count=1,
            )
        ),
    )

    try:
        company, account = _build_company_and_account(session)

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=httpx.MockTransport(handler),
        )

        assert settlement_calls == [(None, {"INTER"})]
        assert "Baixa automatica no Linx concluida" in (result.batch.error_summary or "")
    finally:
        session.close()


def test_sync_inter_charges_retries_linx_settlement_even_without_new_processed_codes(
    monkeypatch,
) -> None:
    session = _build_session()
    settlement_calls: list[tuple[set[str] | None, set[str] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(200, json={"cobrancas": []})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    monkeypatch.setattr(
        "app.services.inter.settle_paid_pending_inter_receivables",
        lambda db, company, *, filter_charge_codes=None, filter_banks=None: (
            settlement_calls.append(
                (
                    set(filter_charge_codes) if filter_charge_codes is not None else None,
                    set(filter_banks) if filter_banks is not None else None,
                )
            )
            or LinxSettlementSummary(
                attempted_invoice_count=1,
                settled_invoice_count=1,
                failed_invoice_count=0,
                client_count=1,
            )
        ),
    )

    try:
        company, account = _build_company_and_account(session)

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=httpx.MockTransport(handler),
        )

        assert settlement_calls == [(None, {"INTER"})]
        assert "Baixa automatica no Linx concluida" in (result.batch.error_summary or "")
    finally:
        session.close()


def test_sync_inter_charges_matches_legacy_record_without_inter_ids_by_business_key() -> None:
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(
                200,
                json={
                    "cobrancas": [
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-LEGACY",
                                "seuNumero": "SEU-LEGACY",
                            }
                        }
                    ]
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-LEGACY":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-LEGACY",
                        "seuNumero": "SEU-LEGACY",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2026-03-01",
                        "dataSituacao": "2026-03-10",
                        "dataVencimento": "2026-03-10",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "250.00",
                        "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        legacy_record = BoletoRecord(
            company_id=company.id,
            bank="INTER",
            client_key=normalize_text("Cliente Exemplo"),
            client_name="Cliente Exemplo",
            document_id="12345",
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 10),
            amount=Decimal("250.00"),
            paid_amount=Decimal("0.00"),
            status="A receber",
        )
        session.add(legacy_record)
        session.commit()

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=httpx.MockTransport(handler),
        )

        records = session.query(BoletoRecord).all()
        assert len(records) == 1
        session.refresh(legacy_record)
        assert result.batch.records_valid == 1
        assert legacy_record.status == "Recebido por boleto"
        assert legacy_record.paid_amount == Decimal("250.00")
        assert legacy_record.inter_codigo_solicitacao == "SOL-LEGACY"
        assert legacy_record.inter_seu_numero == "SEU-LEGACY"
    finally:
        session.close()


def test_sync_inter_charges_keeps_distinct_records_when_inter_reuses_seu_numero() -> None:
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(
                200,
                json={
                    "cobrancas": [
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-REUSE-1",
                                "seuNumero": "305",
                            }
                        },
                        {
                            "cobranca": {
                                "codigoSolicitacao": "SOL-REUSE-2",
                                "seuNumero": "305",
                            }
                        },
                    ]
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-REUSE-1":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-REUSE-1",
                        "seuNumero": "305",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-03-01",
                        "dataVencimento": "2026-03-10",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Reutilizado", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-REUSE-2":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-REUSE-2",
                        "seuNumero": "305",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2026-04-01",
                        "dataSituacao": "2026-04-10",
                        "dataVencimento": "2026-04-10",
                        "valorNominal": "275.00",
                        "valorTotalRecebido": "275.00",
                        "pagador": {"nome": "Cliente Reutilizado", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "999888777",
                        "linhaDigitavel": "999.888.777",
                        "nossoNumero": "NOSSO-2",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 4, 30),
            transport=httpx.MockTransport(handler),
        )

        records = (
            session.query(BoletoRecord).order_by(BoletoRecord.inter_codigo_solicitacao.asc()).all()
        )
        assert len(records) == 2
        assert result.batch.records_total == 2
        assert result.batch.records_valid == 2
        assert {item.inter_codigo_solicitacao for item in records} == {"SOL-REUSE-1", "SOL-REUSE-2"}
        assert all(item.inter_seu_numero == "305" for item in records)
        assert {item.status for item in records} == {"A receber", "Recebido por boleto"}
    finally:
        session.close()


def test_sync_inter_charges_uses_linx_fatura_code_as_document_id_when_available() -> None:
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(
                200,
                json={
                    "cobrancas": [
                        {"cobranca": {"codigoSolicitacao": "SOL-LINX", "seuNumero": "325/001/008"}}
                    ]
                },
            )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-LINX":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-LINX",
                        "seuNumero": "325/001/008",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-08-01",
                        "dataVencimento": "2026-08-10",
                        "valorNominal": "170.50",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Rosana Camilo da Rosa", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            LinxOpenReceivable(
                company_id=company.id,
                linx_code=56569,
                customer_code=1001,
                customer_name="Rosana Camilo da Rosa",
                issue_date=datetime(2026, 8, 1),
                due_date=datetime(2026, 8, 10),
                amount=Decimal("170.50"),
                interest_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                document_number="325",
                document_series="D",
                installment_number=1,
                installment_count=8,
            )
        )
        session.commit()

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            transport=httpx.MockTransport(handler),
        )

        record = session.query(BoletoRecord).filter_by(inter_codigo_solicitacao="SOL-LINX").one()
        assert result.batch.records_valid == 1
        assert record.document_id == "56569"
        assert record.inter_seu_numero == "325/001/008"
    finally:
        session.close()


def test_sync_inter_charges_refreshes_pending_local_boleto_missing_from_charge_list() -> None:
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            return httpx.Response(200, json={"cobrancas": []})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-OLD":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-OLD",
                        "seuNumero": "SEU-OLD",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2025-12-01",
                        "dataSituacao": "2025-12-15",
                        "dataVencimento": "2025-12-10",
                        "valorNominal": "320.00",
                        "valorTotalRecebido": "320.00",
                        "pagador": {"nome": "Cliente Antigo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "123123123",
                        "linhaDigitavel": "123.123.123",
                        "nossoNumero": "NOSSO-OLD",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Antigo"),
                client_name="Cliente Antigo",
                document_id="SEU-OLD",
                issue_date=date(2025, 12, 1),
                due_date=date(2025, 12, 10),
                amount=Decimal("320.00"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-OLD",
                inter_seu_numero="SEU-OLD",
            )
        )
        session.commit()

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=httpx.MockTransport(handler),
        )

        session.expire_all()
        record = session.query(BoletoRecord).filter_by(inter_codigo_solicitacao="SOL-OLD").one()
        assert result.message == "Cobrancas do Inter sincronizadas com sucesso."
        assert result.batch.records_total == 1
        assert result.batch.records_valid == 1
        assert "conferidos individualmente" in (result.batch.error_summary or "")
        assert record.status == "Recebido por boleto"
        assert record.paid_amount == Decimal("320.00")
        assert record.linha_digitavel == "123.123.123"
    finally:
        session.close()


def test_sync_inter_charges_uses_full_initial_window_for_first_default_sync() -> None:
    session = _build_session()
    requested_end_date = date.today()
    requested_start_date = requested_end_date - timedelta(days=90)
    captured_calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            captured_calls.append(
                {
                    "dataInicial": str(request.url.params.get("dataInicial") or ""),
                    "dataFinal": str(request.url.params.get("dataFinal") or ""),
                    "filtrarDataPor": str(request.url.params.get("filtrarDataPor") or ""),
                }
            )
            return httpx.Response(200, json={"cobrancas": []})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=requested_start_date,
            end_date=requested_end_date,
            transport=httpx.MockTransport(handler),
        )

        assert captured_calls == [
            {
                "dataInicial": INTER_CHARGE_FULL_SYNC_START.isoformat(),
                "dataFinal": requested_end_date.isoformat(),
                "filtrarDataPor": "EMISSAO",
            },
            {
                "dataInicial": INTER_CHARGE_FULL_SYNC_START.isoformat(),
                "dataFinal": INTER_CHARGE_FULL_SYNC_DUE_END.isoformat(),
                "filtrarDataPor": "VENCIMENTO",
            },
        ]
        assert result.batch.filename == (
            "inter-cobrancas-full-"
            f"{INTER_CHARGE_FULL_SYNC_START.isoformat()}-{requested_end_date.isoformat()}-"
            f"venc-{INTER_CHARGE_FULL_SYNC_DUE_END.isoformat()}"
        )
        assert (
            "Carga completa inicial do Inter executada com emissao entre "
            f"{INTER_CHARGE_FULL_SYNC_START.isoformat()} e {requested_end_date.isoformat()} "
            "ou vencimento entre "
            f"{INTER_CHARGE_FULL_SYNC_START.isoformat()} e "
            f"{INTER_CHARGE_FULL_SYNC_DUE_END.isoformat()}."
        ) in (result.batch.error_summary or "")
    finally:
        session.close()


def test_sync_inter_charges_uses_incremental_window_after_first_api_sync() -> None:
    session = _build_session()
    requested_end_date = date.today()
    requested_start_date = requested_end_date - timedelta(days=90)
    reference_issue_date = date(2026, 3, 15)
    expected_start_date = reference_issue_date - timedelta(
        days=INTER_CHARGE_INCREMENTAL_LOOKBACK_DAYS
    )
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            captured_params["dataInicial"] = str(request.url.params.get("dataInicial") or "")
            captured_params["dataFinal"] = str(request.url.params.get("dataFinal") or "")
            return httpx.Response(200, json={"cobrancas": []})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente API"),
                client_name="Cliente API",
                document_id="SEU-API-1",
                issue_date=reference_issue_date,
                due_date=date(2026, 3, 30),
                amount=Decimal("180.00"),
                paid_amount=Decimal("180.00"),
                status="Recebido por boleto",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-API-1",
                inter_seu_numero="SEU-API-1",
            )
        )
        session.commit()

        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=requested_start_date,
            end_date=requested_end_date,
            transport=httpx.MockTransport(handler),
        )

        assert captured_params["dataInicial"] == expected_start_date.isoformat()
        assert captured_params["dataFinal"] == requested_end_date.isoformat()
        assert result.batch.filename == (
            f"inter-cobrancas-{expected_start_date.isoformat()}-{requested_end_date.isoformat()}"
        )
        assert "Sincronizacao incremental do Inter" in (result.batch.error_summary or "")
    finally:
        session.close()


def test_sync_inter_charges_deduplicates_full_sync_summaries_from_emission_and_due_date() -> None:
    session = _build_session()
    requested_end_date = date.today()
    requested_start_date = requested_end_date - timedelta(days=90)
    detail_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas":
            filter_by = str(request.url.params.get("filtrarDataPor") or "")
            if filter_by == "EMISSAO":
                return httpx.Response(
                    200,
                    json={
                        "cobrancas": [
                            {"cobranca": {"codigoSolicitacao": "SOL-001", "seuNumero": "SEU-001"}}
                        ]
                    },
                )
            if filter_by == "VENCIMENTO":
                return httpx.Response(
                    200,
                    json={
                        "cobrancas": [
                            {"cobranca": {"codigoSolicitacao": "SOL-001", "seuNumero": "SEU-001"}}
                        ]
                    },
                )
        if request.url.path == "/cobranca/v3/cobrancas/SOL-001":
            detail_calls.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-001",
                        "seuNumero": "SEU-001",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-03-01",
                        "dataVencimento": "2027-01-10",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=requested_start_date,
            end_date=requested_end_date,
            transport=httpx.MockTransport(handler),
        )

        records = session.query(BoletoRecord).all()
        assert len(records) == 1
        assert detail_calls == ["/cobranca/v3/cobrancas/SOL-001"]
        assert result.batch.records_total == 1
        assert result.batch.records_valid == 1
    finally:
        session.close()


def test_cancel_and_receive_inter_charge_update_boleto_status() -> None:
    session = _build_session()

    def build_transport(mode: str) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/v2/token":
                return httpx.Response(200, json={"access_token": "token-123"})
            if request.url.path == "/cobranca/v3/cobrancas/SOL-001/cancelar":
                return httpx.Response(202, json={})
            if request.url.path == "/cobranca/v3/cobrancas/SOL-001/pagar":
                return httpx.Response(204)
            if request.url.path == "/cobranca/v3/cobrancas/SOL-001":
                status_value = "CANCELADO" if mode == "cancel" else "RECEBIDO"
                return httpx.Response(
                    200,
                    json={
                        "cobranca": {
                            "codigoSolicitacao": "SOL-001",
                            "seuNumero": "SEU-001",
                            "situacao": status_value,
                            "dataEmissao": "2026-03-01",
                            "dataSituacao": "2026-03-10" if status_value == "RECEBIDO" else "",
                            "dataVencimento": "2026-03-10",
                            "valorNominal": "250.00",
                            "valorTotalRecebido": (
                                "250.00" if status_value == "RECEBIDO" else "0.00"
                            ),
                            "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                        },
                        "boleto": {
                            "codigoBarras": "111222333",
                            "linhaDigitavel": "111.222.333",
                            "nossoNumero": "NOSSO-1",
                        },
                    },
                )
            raise AssertionError(f"Requisicao inesperada: {request.url}")

        return httpx.MockTransport(handler)

    try:
        company, account = _build_company_and_account(session)
        account.inter_environment = "sandbox"
        session.add(
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Exemplo"),
                client_name="Cliente Exemplo",
                document_id="SEU-001",
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 10),
                amount=Decimal("250.00"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-001",
            )
        )
        session.commit()

        boleto = session.query(BoletoRecord).one()
        cancel_result = cancel_inter_charge(
            session,
            company,
            boleto_id=boleto.id,
            motivo_cancelamento="Cliente desistiu",
            transport=build_transport("cancel"),
        )
        session.refresh(boleto)
        assert cancel_result.message == "Boleto do Inter cancelado com sucesso."
        assert boleto.status == "Cancelado"

        receive_result = receive_inter_charge(
            session,
            company,
            boleto_id=boleto.id,
            pagar_com="BOLETO",
            transport=build_transport("receive"),
        )
        session.refresh(boleto)
        assert receive_result.message == "Baixa do boleto do Inter concluida com sucesso."
        assert boleto.status == "Recebido por boleto"
        assert boleto.paid_amount == Decimal("250.00")
    finally:
        session.close()


def test_cancel_standalone_inter_charge_marks_record_as_canceled_even_when_detail_is_stale() -> (
    None
):
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-AVL-001/cancelar":
            return httpx.Response(202, json={})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-AVL-001":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-AVL-001",
                        "seuNumero": "AVL-001",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-04-01",
                        "dataVencimento": "2026-04-10",
                        "valorNominal": "89.90",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Avulso", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333",
                        "linhaDigitavel": "111.222.333",
                        "nossoNumero": "NOSSO-AVL-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            StandaloneBoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Avulso"),
                client_name="Cliente Avulso",
                document_id="AVL-001",
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 10),
                amount=Decimal("89.90"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                local_status="open",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-AVL-001",
                description="Boleto avulso",
            )
        )
        session.commit()

        boleto = session.query(StandaloneBoletoRecord).one()
        result = cancel_standalone_inter_charge(
            session,
            company,
            boleto_id=boleto.id,
            motivo_cancelamento="Cliente desistiu",
            transport=httpx.MockTransport(handler),
        )

        session.refresh(boleto)
        assert result.message == "Boleto avulso do Inter cancelado com sucesso."
        assert boleto.status == "Cancelado"
        assert boleto.local_status == "open"
    finally:
        session.close()


def test_sync_standalone_inter_charges_reopens_cancelled_record_when_inter_still_reports_open() -> (
    None
):
    session = _build_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-AVL-002":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-AVL-002",
                        "seuNumero": "AVL-002",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-04-01",
                        "dataVencimento": "2026-04-10",
                        "valorNominal": "109.90",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Avulso", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "444555666",
                        "linhaDigitavel": "444.555.666",
                        "nossoNumero": "NOSSO-AVL-2",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            StandaloneBoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Avulso"),
                client_name="Cliente Avulso",
                document_id="AVL-002",
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 10),
                amount=Decimal("109.90"),
                paid_amount=Decimal("0.00"),
                status="Cancelado",
                local_status="open",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-AVL-002",
                description="Boleto avulso",
            )
        )
        session.commit()

        result = sync_standalone_inter_charges(
            session,
            company,
            transport=httpx.MockTransport(handler),
        )

        boleto = session.query(StandaloneBoletoRecord).one()
        assert result.message == "Boletos avulsos sincronizados com sucesso."
        assert boleto.status == "A receber"
        assert boleto.local_status == "open"
    finally:
        session.close()


def test_sync_standalone_inter_charges_updates_downloaded_record_bank_status(monkeypatch) -> None:
    session = _build_session()
    email_calls: list[tuple[str, str, list[str] | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-AVL-003":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-AVL-003",
                        "seuNumero": "AVL-003",
                        "situacao": "RECEBIDO",
                        "dataEmissao": "2026-04-01",
                        "dataSituacao": "2026-04-12",
                        "dataVencimento": "2026-04-10",
                        "valorNominal": "79.90",
                        "valorTotalRecebido": "79.90",
                        "pagador": {"nome": "Cliente Avulso", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "777888999",
                        "linhaDigitavel": "777.888.999",
                        "nossoNumero": "NOSSO-AVL-3",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        company.linx_auto_sync_alert_email = "financeiro@example.com"
        session.add(company)
        session.flush()
        session.add(
            StandaloneBoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Avulso"),
                client_name="Cliente Avulso",
                document_id="AVL-003",
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 10),
                amount=Decimal("79.90"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                local_status="downloaded",
                inter_account_id=account.id,
                inter_codigo_solicitacao="SOL-AVL-003",
                description="Boleto avulso",
            )
        )
        session.commit()
        monkeypatch.setattr("app.services.inter.ensure_email_transport_configured", lambda: None)
        monkeypatch.setattr(
            "app.services.inter.send_email",
            lambda subject, body, *, recipients=None, html_body=None: email_calls.append(
                (subject, body, recipients, html_body)
            ),
        )

        result = sync_standalone_inter_charges(
            session,
            company,
            transport=httpx.MockTransport(handler),
        )

        boleto = session.query(StandaloneBoletoRecord).one()
        assert (
            result.message
            == "Boletos avulsos sincronizados com sucesso. 1 pagamento(s) identificado(s)."
        )
        assert boleto.status == "Recebido por boleto"
        assert boleto.local_status == "downloaded"
        assert boleto.paid_amount == Decimal("79.90")
        assert len(email_calls) == 1
        assert email_calls[0][2] == ["financeiro@example.com"]
        assert "Cliente Avulso" in email_calls[0][1]
        assert "79,90" in email_calls[0][1]
    finally:
        session.close()

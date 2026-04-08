from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.boleto import BoletoRecord
from app.db.models.finance import Account
from app.db.models.security import Company
from app.services.boletos import normalize_text
from app.services.inter import (
    INTER_CHARGE_FULL_SYNC_START,
    INTER_CHARGE_INCREMENTAL_LOOKBACK_DAYS,
    cancel_inter_charge,
    receive_inter_charge,
    sync_inter_charges,
)


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
        assert updated.inter_account_id == account.id
        assert updated.inter_codigo_solicitacao == "SOL-001"
        assert updated.linha_digitavel == "111.222.333"
        assert updated.pix_copia_e_cola == "PIX-COLA-1"

        assert created.status == "A receber"
        assert created.amount == Decimal("199.90")
        assert created.inter_account_id == account.id
        assert created.barcode == "999888777"
        assert created.inter_nosso_numero == "NOSSO-2"
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
        result = sync_inter_charges(
            session,
            company,
            account_id=account.id,
            start_date=requested_start_date,
            end_date=requested_end_date,
            transport=httpx.MockTransport(handler),
        )

        assert captured_params["dataInicial"] == INTER_CHARGE_FULL_SYNC_START.isoformat()
        assert captured_params["dataFinal"] == requested_end_date.isoformat()
        assert result.batch.filename == (
            f"inter-cobrancas-{INTER_CHARGE_FULL_SYNC_START.isoformat()}-{requested_end_date.isoformat()}"
        )
        assert "Carga completa inicial do Inter" in (result.batch.error_summary or "")
    finally:
        session.close()


def test_sync_inter_charges_uses_incremental_window_after_first_api_sync() -> None:
    session = _build_session()
    requested_end_date = date.today()
    requested_start_date = requested_end_date - timedelta(days=90)
    reference_issue_date = date(2026, 3, 15)
    expected_start_date = reference_issue_date - timedelta(days=INTER_CHARGE_INCREMENTAL_LOOKBACK_DAYS)
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
                            "dataVencimento": "2026-03-10",
                            "valorNominal": "250.00",
                            "valorTotalRecebido": "250.00" if status_value == "RECEBIDO" else "0.00",
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

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord
from app.db.models.finance import Account
from app.db.models.imports import ImportBatch
from app.db.models.linx import ReceivableTitle
from app.db.models.security import Company
from app.services.boletos import build_boleto_dashboard, normalize_text
from app.services.inter import issue_inter_charges


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


def _create_receivable_batch(session: Session, company: Company) -> ImportBatch:
    batch = ImportBatch(
        company_id=company.id,
        source_type="linx_receivables",
        filename="receber.xlsx",
        status="processed",
        records_total=1,
        records_valid=1,
        records_invalid=0,
    )
    session.add(batch)
    session.flush()
    return batch


def test_issue_inter_charges_creates_boleto_from_missing_item() -> None:
    session = _build_session()
    created_payloads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/cobranca/v3/cobrancas" and request.method == "POST":
            payload = request.content
            created_payloads.append(payload)
            assert b"12345" in payload
            return httpx.Response(200, json={"codigoSolicitacao": "SOL-NEW-1"})
        if request.url.path == "/cobranca/v3/cobrancas/SOL-NEW-1":
            return httpx.Response(
                200,
                json={
                    "cobranca": {
                        "codigoSolicitacao": "SOL-NEW-1",
                        "seuNumero": "12345",
                        "situacao": "A_RECEBER",
                        "dataEmissao": "2026-03-01",
                        "dataVencimento": "2026-03-12",
                        "valorNominal": "250.00",
                        "valorTotalRecebido": "0.00",
                        "pagador": {"nome": "Cliente Exemplo", "cpfCnpj": "12345678901"},
                    },
                    "boleto": {
                        "codigoBarras": "111222333444",
                        "linhaDigitavel": "11122.233344 4555",
                        "nossoNumero": "NOSSO-NEW-1",
                    },
                    "pix": {
                        "pixCopiaECola": "PIX-COLA-NEW-1",
                        "txid": "TXID-NEW-1",
                    },
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=normalize_text("Cliente Exemplo"),
                client_name="Cliente Exemplo",
                client_code="1001",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=12,
                include_interest=True,
                address_street="Rua Exemplo",
                address_number="330",
                neighborhood="Centro",
                city="Cidade Exemplo",
                state="SC",
                zip_code="99999999",
                tax_id="12345678901",
                mobile="48999990000",
            )
        )
        receivable_batch = _create_receivable_batch(session, company)
        session.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=receivable_batch.id,
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 12),
                invoice_number="12345",
                company_code="1001",
                installment_label="001",
                original_amount=Decimal("250.00"),
                amount_with_interest=Decimal("250.00"),
                customer_name="Cliente Exemplo",
                document_reference="DOC-1",
                status="Em aberto",
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        assert len(dashboard.missing_boletos) == 1

        result = issue_inter_charges(
            session,
            company,
            account_id=account.id,
            selection_keys=[dashboard.missing_boletos[0].selection_key],
            transport=httpx.MockTransport(handler),
        )

        issued = session.query(BoletoRecord).one()
        assert result.message == "Boletos emitidos no Inter com sucesso."
        assert result.batch.records_valid == 1
        assert result.batch.source_type == "inter_charge_issue"
        assert created_payloads
        assert b'"formasRecebimento":["BOLETO"]' in created_payloads[0]
        created_payload = json.loads(created_payloads[0])
        assert created_payload["multa"] == {"codigo": "PERCENTUAL", "taxa": 2.0}
        assert created_payload["mora"] == {"codigo": "TAXAMENSAL", "taxa": 1.0}
        assert issued.document_id == "12345"
        assert issued.inter_account_id == account.id
        assert issued.inter_codigo_solicitacao == "SOL-NEW-1"
        assert issued.status == "A receber"
        assert issued.linha_digitavel == "11122.233344 4555"
        assert issued.pix_copia_e_cola == "PIX-COLA-NEW-1"
    finally:
        session.close()


def test_issue_inter_charges_requires_complete_customer_registration() -> None:
    session = _build_session()
    try:
        company, account = _build_company_and_account(session)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=normalize_text("Cliente Exemplo"),
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="individual",
            )
        )
        receivable_batch = _create_receivable_batch(session, company)
        session.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=receivable_batch.id,
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 12),
                invoice_number="12345",
                company_code="1001",
                installment_label="001",
                original_amount=Decimal("250.00"),
                amount_with_interest=Decimal("250.00"),
                customer_name="Cliente Exemplo",
                document_reference="DOC-1",
                status="Em aberto",
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)

        with pytest.raises(ValueError, match="Complete os dados obrigatorios"):
            issue_inter_charges(
                session,
                company,
                account_id=account.id,
                selection_keys=[dashboard.missing_boletos[0].selection_key],
                transport=httpx.MockTransport(lambda request: httpx.Response(500)),
            )
    finally:
        session.close()

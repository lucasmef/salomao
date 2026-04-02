from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.boleto import BoletoCustomerConfig
from app.db.models.finance import Account
from app.db.models.imports import ImportBatch
from app.db.models.linx import ReceivableTitle
from app.db.models.security import Company, User
from app.services.boletos import build_boleto_dashboard


class FakeInterApiClient:
    issued_payloads: list[dict] = []

    def __init__(self, config, *, transport=None) -> None:
        self.config = config
        self.transport = transport

    def close(self) -> None:
        return None

    def get_complete_statement(self, start_date: date, end_date: date) -> list[dict]:
        assert start_date <= end_date
        return [
            {
                "idTransacao": "trx-001",
                "dataTransacao": "2026-03-15",
                "tipoTransacao": "PIX",
                "tipoOperacao": "DEBITO",
                "valor": "150.50",
                "titulo": "Pagamento",
                "descricao": "Fornecedor ABC",
            }
        ]

    def list_charges(self, start_date: date, end_date: date) -> list[dict]:
        assert start_date <= end_date
        return [{"codigoSolicitacao": "SOL-001", "seuNumero": "12345"}]

    def get_charge_detail(self, codigo_solicitacao: str) -> dict:
        return {
            "cobranca": {
                "codigoSolicitacao": codigo_solicitacao,
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
                "nossoNumero": "NOSSO-001",
            },
            "pix": {
                "pixCopiaECola": "PIX-COLA-001",
                "txid": "TXID-001",
            },
        }

    def create_charge(self, payload: dict) -> dict:
        self.__class__.issued_payloads.append(payload)
        return {"codigoSolicitacao": "SOL-NEW-1"}


def _build_test_session() -> tuple[Session, Company, User, Account]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)

    company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste")
    session.add(company)
    session.flush()
    user = User(
        company_id=company.id,
        full_name="Admin Teste",
        email="admin@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
    )
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
    )
    session.add_all([user, account])
    session.commit()
    return session, company, user, account


def _create_receivable_seed(session: Session, company: Company) -> None:
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
    session.add(
        BoletoCustomerConfig(
            company_id=company.id,
            client_key="CLIENTE EXEMPLO",
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
    session.add(
        ReceivableTitle(
            company_id=company.id,
            source_batch_id=batch.id,
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


def test_inter_endpoints_smoke(monkeypatch) -> None:
    session, company, user, account = _build_test_session()
    _create_receivable_seed(session, company)
    FakeInterApiClient.issued_payloads = []

    monkeypatch.setattr("app.services.inter.InterApiClient", FakeInterApiClient)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)

    try:
        create_account_response = client.post(
            "/api/v1/accounts",
            json={
                "name": "Conta Inter Filial",
                "account_type": "checking",
                "bank_code": "077",
                "account_number": "789012",
                "inter_api_enabled": True,
                "inter_environment": "sandbox",
                "inter_api_key": "client-id-2",
                "inter_account_number": "789012",
                "inter_client_secret": "secret-2",
                "inter_certificate_pem": "---CERT---",
                "inter_private_key_pem": "---KEY---",
            },
        )
        assert create_account_response.status_code == 201
        assert create_account_response.json()["has_inter_client_secret"] is True

        statement_response = client.post(
            "/api/v1/imports/inter/statement-sync",
            json={"account_id": account.id},
        )
        assert statement_response.status_code == 201

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        assert dashboard.missing_boletos

        issue_response = client.post(
            "/api/v1/boletos/inter/issue",
            json={"account_id": account.id, "selection_keys": [dashboard.missing_boletos[0].selection_key]},
        )
        assert issue_response.status_code == 201
        assert FakeInterApiClient.issued_payloads

        sync_response = client.post(
            "/api/v1/boletos/inter/sync",
            json={"account_id": account.id},
        )
        assert sync_response.status_code == 201
    finally:
        client.close()
        session.close()

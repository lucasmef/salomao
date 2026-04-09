from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.finance import Account
from app.db.models.security import Company, User


class FakeC6ApiClient:
    consulted_ids: list[str] = []
    pdf_ids: list[str] = []

    def __init__(self, config, *, transport=None) -> None:
        self.config = config
        self.transport = transport

    def close(self) -> None:
        return None

    def authenticate(self):
        from app.services.c6 import C6AuthToken

        return C6AuthToken(
            access_token="token-123",
            token_type="Bearer",
            expires_in=600,
            scope="bankslip.read",
        )

    def get_bank_slip(self, bank_slip_id: str):
        self.__class__.consulted_ids.append(bank_slip_id)
        return {
            "id": bank_slip_id,
            "status": "CREATED",
            "amount": 123.45,
            "digitable_line": "12345.67890 12345.678901 12345.678901 1 23450000012345",
        }

    def get_bank_slip_pdf(self, bank_slip_id: str) -> bytes:
        self.__class__.pdf_ids.append(bank_slip_id)
        return b"%PDF-C6"


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
        name="C6 Matriz",
        account_type="checking",
        bank_code="336",
        account_number="123456",
        c6_api_enabled=True,
        c6_environment="sandbox",
        c6_client_id="client-id",
        c6_partner_software_name="Gestor Financeiro",
        c6_partner_software_version="0.1.0",
        c6_client_secret_encrypted=encrypt_text("client-secret"),
        c6_certificate_pem_encrypted=encrypt_text("---CERT---"),
        c6_private_key_pem_encrypted=encrypt_text("---KEY---"),
    )
    session.add_all([user, account])
    session.commit()
    return session, company, user, account


def test_c6_endpoints_smoke(monkeypatch) -> None:
    session, _company, user, account = _build_test_session()
    FakeC6ApiClient.consulted_ids = []
    FakeC6ApiClient.pdf_ids = []

    monkeypatch.setattr("app.services.c6.C6ApiClient", FakeC6ApiClient)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)

    try:
        auth_response = client.post("/api/v1/boletos/c6/auth-test", json={"account_id": account.id})
        assert auth_response.status_code == 200
        assert auth_response.json()["scope"] == "bankslip.read"

        consult_response = client.get(f"/api/v1/boletos/c6/BSL-001?account_id={account.id}")
        assert consult_response.status_code == 200
        assert consult_response.json()["payload"]["id"] == "BSL-001"
        assert FakeC6ApiClient.consulted_ids == ["BSL-001"]

        pdf_response = client.get(f"/api/v1/boletos/c6/BSL-001/pdf?account_id={account.id}")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"].startswith("application/pdf")
        assert pdf_response.content == b"%PDF-C6"
        assert FakeC6ApiClient.pdf_ids == ["BSL-001"]
    finally:
        client.close()
        session.close()

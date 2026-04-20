from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.api.routes import boletos as boletos_routes
from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.security import Company, User
from app.services.linx_receivable_settlement import LinxSettlementSummary


def _build_test_session() -> tuple[Session, Company, User]:
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
    session.add(user)
    session.commit()
    return session, company, user


def test_run_c6_settlement_after_import_updates_batch_error_summary(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste")
        session.add(company)
        session.flush()
        batch = ImportBatch(
            company_id=company.id,
            source_type="boletos:c6",
            filename="relatorio-c6.csv",
            status="processed",
            records_total=1,
            records_valid=1,
            records_invalid=0,
        )
        session.add(batch)
        session.commit()
        company_id = company.id
        batch_id = batch.id

    monkeypatch.setattr(boletos_routes, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        boletos_routes,
        "settle_paid_pending_inter_receivables",
        lambda db, company, filter_banks: LinxSettlementSummary(
            attempted_invoice_count=1,
            settled_invoice_count=1,
            failed_invoice_count=0,
            client_count=1,
            empty_scope_phrase="do C6",
        ),
    )

    message = boletos_routes._run_c6_settlement_after_import(company_id, batch_id)

    assert "Baixa automatica no Linx concluida." in message

    with TestingSessionLocal() as session:
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None
        assert batch.error_summary == message

    engine.dispose()


def test_trigger_c6_linx_settlement_endpoint_returns_summary(monkeypatch) -> None:
    session, company, user = _build_test_session()
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(boletos_routes, "get_current_company", lambda current_db: company)
    monkeypatch.setattr(
        boletos_routes,
        "settle_paid_pending_inter_receivables",
        lambda db, current_company, filter_banks: LinxSettlementSummary(
            attempted_invoice_count=0,
            settled_invoice_count=0,
            failed_invoice_count=0,
            client_count=0,
            empty_scope_phrase="do C6",
        ),
    )

    client = TestClient(app)

    try:
        response = client.post("/api/v1/boletos/linx/c6-settlement")
        assert response.status_code == 201
        assert response.json()["message"] == "Nenhuma fatura paga sem baixa do C6 encontrada para baixar no Linx."
    finally:
        client.close()
        session.close()

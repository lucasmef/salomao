from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxOpenReceivable
from app.db.models.security import Company, User
from app.schemas.imports import ImportResult
from app.schemas.linx_open_receivables import (
    LinxOpenReceivableDirectoryRead,
    LinxOpenReceivableDirectorySummaryRead,
    LinxOpenReceivableListItemRead,
)
from app.services.linx_open_receivables import list_linx_open_receivables, sync_linx_open_receivables


def _build_session() -> tuple[Session, Company, User]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    company = Company(legal_name="Empresa Teste Ltda", trade_name="Salomao")
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


def test_sync_linx_open_receivables_tracks_open_only(monkeypatch) -> None:
    session, company, _ = _build_session()
    first_rows = [
        {
            "portal": "10994",
            "empresa": "1",
            "codigo_fatura": "55885",
            "data_emissao": "2026-01-06T00:00:00",
            "cod_cliente": "1147",
            "nome_cliente": "VALDETE DAMIAN SILVESTRI",
            "data_vencimento": "2026-03-06T00:00:00",
            "data_baixa": "",
            "valor_fatura": "118.0500",
            "valor_pago": "0.0000",
            "valor_desconto": "0.0000",
            "valor_juros": "0.0000",
            "documento": "285",
            "serie": "D",
            "qtde_parcelas": "6",
            "ordem_parcela": "2",
            "receber_pagar": "R",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "abc",
            "forma_pgto": "Crediário",
            "plano": "114",
            "vendedor": "7",
            "observacao": "",
            "timestamp": "15865025",
        },
        {
            "portal": "10994",
            "empresa": "1",
            "codigo_fatura": "99999",
            "data_emissao": "2026-01-06T00:00:00",
            "cod_cliente": "1",
            "nome_cliente": "BANCO INTER",
            "data_vencimento": "2026-03-06T00:00:00",
            "data_baixa": "",
            "valor_fatura": "10.0000",
            "valor_pago": "0.0000",
            "valor_desconto": "0.0000",
            "valor_juros": "0.0000",
            "documento": "999",
            "serie": "D",
            "qtde_parcelas": "1",
            "ordem_parcela": "1",
            "receber_pagar": "R",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "not-crediario",
            "forma_pgto": "Cartão",
            "plano": "999",
            "vendedor": "7",
            "observacao": "",
            "timestamp": "15865026",
        },
    ]
    second_rows = [
        {
            "portal": "10994",
            "empresa": "1",
            "codigo_fatura": "55885",
            "data_emissao": "2026-01-06T00:00:00",
            "cod_cliente": "1147",
            "nome_cliente": "VALDETE DAMIAN SILVESTRI",
            "data_vencimento": "2026-03-06T00:00:00",
            "data_baixa": "2026-04-07T00:00:00",
            "valor_fatura": "118.0500",
            "valor_pago": "118.0500",
            "valor_desconto": "0.0000",
            "valor_juros": "0.0000",
            "documento": "285",
            "serie": "D",
            "qtde_parcelas": "6",
            "ordem_parcela": "2",
            "receber_pagar": "R",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "abc",
            "forma_pgto": "Crediário",
            "plano": "114",
            "vendedor": "7",
            "observacao": "",
            "timestamp": "15866000",
        }
    ]
    calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.linx_open_receivables.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )

    def fake_collect_rows(settings, *, start_timestamp, hasher):
        calls["count"] += 1
        return first_rows if calls["count"] == 1 else second_rows

    monkeypatch.setattr("app.services.linx_open_receivables._collect_rows", fake_collect_rows)

    try:
        first = sync_linx_open_receivables(session, company)
        assert "1 nova(s)" in first.message
        assert session.query(LinxOpenReceivable).filter_by(company_id=company.id).count() == 1

        second = sync_linx_open_receivables(session, company)
        assert "1 removida(s)" in second.message
        assert session.query(LinxOpenReceivable).filter_by(company_id=company.id).count() == 0
    finally:
        session.close()


def test_list_linx_open_receivables_paginates() -> None:
    session, company, _ = _build_session()
    try:
        session.add_all(
            [
                LinxOpenReceivable(
                    company_id=company.id,
                    linx_code=1,
                    customer_code=10,
                    customer_name="ANA",
                    due_date=datetime(2026, 4, 5),
                    amount=Decimal("100.00"),
                ),
                LinxOpenReceivable(
                    company_id=company.id,
                    linx_code=2,
                    customer_code=11,
                    customer_name="BRUNO",
                    due_date=datetime(2026, 4, 7),
                    amount=Decimal("200.00"),
                ),
                LinxOpenReceivable(
                    company_id=company.id,
                    linx_code=3,
                    customer_code=12,
                    customer_name="CARLA",
                    due_date=datetime(2026, 4, 10),
                    amount=Decimal("300.00"),
                ),
            ]
        )
        session.commit()

        response = list_linx_open_receivables(session, company, page=1, page_size=2, search="A")
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 10
        assert response.summary.total_count == 3
        assert response.summary.total_amount == Decimal("600.00")
        assert len(response.items) == 2
    finally:
        session.close()


def test_linx_open_receivables_endpoints_smoke(monkeypatch) -> None:
    session, company, user = _build_session()
    captured: dict[str, object] = {}

    def fake_sync(db, current_company, *, full_refresh=False):
        captured["sync"] = (db, current_company.id, full_refresh)
        batch = ImportBatch(
            company_id=company.id,
            source_type="linx_open_receivables",
            filename="linx-open-receivables-full.xml",
            status="processed",
            records_total=1,
            records_valid=1,
            records_invalid=0,
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return ImportResult(batch=batch, message="open receivables ok")

    def fake_list(db, current_company, *, page=1, page_size=50, search=None):
        captured["list"] = (db, current_company.id, page, page_size, search)
        return LinxOpenReceivableDirectoryRead(
            generated_at=datetime.now(timezone.utc),
            summary=LinxOpenReceivableDirectorySummaryRead(
                total_count=1,
                overdue_count=1,
                due_today_count=0,
                total_amount=Decimal("118.05"),
            ),
            items=[
                LinxOpenReceivableListItemRead(
                    id="1",
                    linx_code=55885,
                    customer_name="VALDETE DAMIAN SILVESTRI",
                    amount=Decimal("118.05"),
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
        )

    monkeypatch.setattr("app.api.routes.imports.sync_linx_open_receivables", fake_sync)
    monkeypatch.setattr("app.api.routes.linx_open_receivables.list_linx_open_receivables", fake_list)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        sync_response = client.post("/api/v1/imports/linx-open-receivables/sync", json={"full_refresh": True})
        list_response = client.get("/api/v1/linx-open-receivables?page=2&page_size=25&search=valdete")

        assert sync_response.status_code == 201
        assert sync_response.json()["message"] == "open receivables ok"
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert captured["sync"] == (session, company.id, True)
        assert captured["list"] == (session, company.id, 2, 25, "valdete")
    finally:
        client.close()
        session.close()

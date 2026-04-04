from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.core.crypto import decrypt_text
from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.security import Company, User
from app.schemas.imports import ImportResult
from app.services.imports import sync_linx_receivables, sync_linx_sales
from app.services.linx import serialize_linx_settings


def _build_session() -> tuple[Session, Company, User]:
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


def _create_batch(
    session: Session,
    company_id: str,
    *,
    source_type: str,
    filename: str,
) -> ImportBatch:
    batch = ImportBatch(
        company_id=company_id,
        source_type=source_type,
        filename=filename,
        status="processed",
        records_total=1,
        records_valid=1,
        records_invalid=0,
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def test_sync_linx_sales_downloads_file_and_delegates_import(monkeypatch) -> None:
    session, company, _ = _build_session()
    captured: dict[str, object] = {}

    def fake_download_linx_sales_report(current_company, *, start_date=None, end_date=None):
        captured["download_period"] = (current_company.id, start_date, end_date)
        return "FaturamentoDiario.xls", b"sales-content"

    def fake_import_linx_sales(db, current_company, filename, content):
        captured["import_args"] = (db, current_company, filename, content)
        batch = _create_batch(session, company.id, source_type="linx_sales", filename=filename)
        return ImportResult(batch=batch, message="ok")

    monkeypatch.setattr(
        "app.services.imports.download_linx_sales_report",
        fake_download_linx_sales_report,
    )
    monkeypatch.setattr("app.services.imports.import_linx_sales", fake_import_linx_sales)

    try:
        result = sync_linx_sales(
            session,
            company,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )

        assert captured["download_period"] == (
            company.id,
            date(2026, 4, 1),
            date(2026, 4, 30),
        )
        assert captured["import_args"] == (
            session,
            company,
            "FaturamentoDiario.xls",
            b"sales-content",
        )
        assert result.message == "ok"
    finally:
        session.close()


def test_sync_linx_receivables_downloads_file_and_delegates_import(monkeypatch) -> None:
    session, company, _ = _build_session()
    captured: dict[str, object] = {}

    def fake_download_linx_receivables_report(
        current_company,
        *,
        start_date=None,
        end_date=None,
    ):
        captured["download_period"] = (current_company.id, start_date, end_date)
        return "FaturasaReceberporPeriodo.xls", b"receivables-content"

    def fake_import_linx_receivables(db, current_company, filename, content):
        captured["import_args"] = (db, current_company, filename, content)
        batch = _create_batch(
            session,
            company.id,
            source_type="linx_receivables",
            filename=filename,
        )
        return ImportResult(batch=batch, message="ok")

    monkeypatch.setattr(
        "app.services.imports.download_linx_receivables_report",
        fake_download_linx_receivables_report,
    )
    monkeypatch.setattr(
        "app.services.imports.import_linx_receivables",
        fake_import_linx_receivables,
    )

    try:
        result = sync_linx_receivables(
            session,
            company,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )

        assert captured["download_period"] == (
            company.id,
            date(2026, 4, 1),
            date(2026, 4, 30),
        )
        assert captured["import_args"] == (
            session,
            company,
            "FaturasaReceberporPeriodo.xls",
            b"receivables-content",
        )
        assert result.message == "ok"
    finally:
        session.close()


def test_linx_sync_endpoints_smoke(monkeypatch) -> None:
    session, company, user = _build_session()
    captured: dict[str, object] = {}

    def fake_sync_linx_sales(db, current_company, *, start_date=None, end_date=None):
        captured["sales"] = (db, current_company.id, start_date, end_date)
        batch = _create_batch(
            session,
            company.id,
            source_type="linx_sales",
            filename="FaturamentoDiario.xls",
        )
        return ImportResult(batch=batch, message="sales ok")

    def fake_sync_linx_receivables(db, current_company, *, start_date=None, end_date=None):
        captured["receivables"] = (db, current_company.id, start_date, end_date)
        batch = _create_batch(
            session,
            company.id,
            source_type="linx_receivables",
            filename="FaturasaReceberporPeriodo.xls",
        )
        return ImportResult(batch=batch, message="receivables ok")

    monkeypatch.setattr("app.api.routes.imports.sync_linx_sales", fake_sync_linx_sales)
    monkeypatch.setattr(
        "app.api.routes.imports.sync_linx_receivables",
        fake_sync_linx_receivables,
    )

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)

    try:
        sales_response = client.post(
            "/api/v1/imports/linx-sales/sync",
            json={"start_date": "2026-04-01", "end_date": "2026-04-30"},
        )
        receivables_response = client.post(
            "/api/v1/imports/linx-receivables/sync",
            json={"start_date": "2026-04-05", "end_date": "2026-04-25"},
        )

        assert sales_response.status_code == 201
        assert sales_response.json()["message"] == "sales ok"
        assert receivables_response.status_code == 201
        assert receivables_response.json()["message"] == "receivables ok"
        assert captured["sales"] == (session, company.id, date(2026, 4, 1), date(2026, 4, 30))
        assert captured["receivables"] == (
            session,
            company.id,
            date(2026, 4, 5),
            date(2026, 4, 25),
        )
    finally:
        client.close()
        session.close()


def test_linx_settings_serialization_and_update_endpoint() -> None:
    session, company, user = _build_session()
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        initial = serialize_linx_settings(company)
        assert initial.base_url == "https://erp.microvix.com.br"
        assert initial.has_password is False

        update_response = client.put(
            "/api/v1/company-settings/linx",
            json={
                "base_url": "https://erp.microvix.com.br",
                "username": "usuario.linx",
                "password": "senha-super-secreta",
                "sales_view_name": "FATURAMENTO SALOMAO",
                "receivables_view_name": "CREDIARIO SALOMAO",
                "auto_sync_enabled": True,
                "auto_sync_alert_email": "financeiro@example.com",
            },
        )
        assert update_response.status_code == 200
        body = update_response.json()
        assert body["username"] == "usuario.linx"
        assert body["has_password"] is True
        assert body["auto_sync_enabled"] is True
        assert body["auto_sync_alert_email"] == "financeiro@example.com"
        assert "password" not in body

        session.refresh(company)
        assert decrypt_text(company.linx_password_encrypted) == "senha-super-secreta"
        assert company.linx_auto_sync_enabled is True
        assert company.linx_auto_sync_alert_email == "financeiro@example.com"

        preserve_response = client.put(
            "/api/v1/company-settings/linx",
            json={
                "base_url": "https://erp.microvix.com.br",
                "username": "usuario.atualizado",
                "password": "",
                "sales_view_name": "FATURAMENTO SALOMAO",
                "receivables_view_name": "CREDIARIO SALOMAO",
                "auto_sync_enabled": False,
                "auto_sync_alert_email": "",
            },
        )
        assert preserve_response.status_code == 200
        session.refresh(company)
        assert company.linx_username == "usuario.atualizado"
        assert decrypt_text(company.linx_password_encrypted) == "senha-super-secreta"
        assert company.linx_auto_sync_enabled is False
        assert company.linx_auto_sync_alert_email is None

        get_response = client.get("/api/v1/company-settings/linx")
        assert get_response.status_code == 200
        assert get_response.json()["has_password"] is True
        assert get_response.json()["auto_sync_enabled"] is False
    finally:
        client.close()
        session.close()

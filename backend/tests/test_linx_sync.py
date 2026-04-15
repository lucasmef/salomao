from __future__ import annotations

from datetime import date, datetime

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
from app.services.linx import download_linx_receivables_report, serialize_linx_settings


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


def test_download_linx_receivables_report_submits_saved_view_without_overwriting_period(
    monkeypatch,
) -> None:
    _, company, _ = _build_session()
    selected_views: list[tuple[str, str]] = []

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        def click(self) -> None:
            self.page.clicks.append(self.selector)

        def wait_for(self, *, state: str) -> None:
            self.page.waits.append((self.selector, state))

    class FakePage:
        def __init__(self) -> None:
            self.clicks: list[str] = []
            self.waits: list[tuple[str, str]] = []
            self.gotos: list[str] = []
            self.waited_urls: list[str] = []
            self.timeout_ms: int | None = None

        def set_default_timeout(self, timeout_ms: int) -> None:
            self.timeout_ms = timeout_ms

        def goto(self, url: str, *, wait_until: str) -> None:
            self.gotos.append(f"{url}|{wait_until}")

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def wait_for_url(self, pattern: str, *, timeout: int) -> None:
            self.waited_urls.append(pattern)
            assert timeout == 12_345

    class FakeContext:
        def __init__(self, page: FakePage) -> None:
            self.page = page

        def new_page(self) -> FakePage:
            return self.page

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self, page: FakePage) -> None:
            self.page = page

        def new_context(self, *, accept_downloads: bool) -> FakeContext:
            assert accept_downloads is True
            return FakeContext(self.page)

        def close(self) -> None:
            return None

    class FakeChromium:
        def __init__(self, page: FakePage) -> None:
            self.page = page

        def launch(self, *, headless: bool) -> FakeBrowser:
            assert headless is True
            return FakeBrowser(self.page)

    class FakePlaywright:
        def __init__(self, page: FakePage) -> None:
            self.chromium = FakeChromium(page)

    class FakePlaywrightManager:
        def __init__(self, page: FakePage) -> None:
            self.page = page

        def __enter__(self) -> FakePlaywright:
            return FakePlaywright(self.page)

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeTimeoutError(Exception):
        pass

    fake_page = FakePage()

    monkeypatch.setattr(
        "app.services.linx._load_linx_settings",
        lambda current_company: type(
            "Settings",
            (),
            {
                "base_url": "https://erp.microvix.com.br",
                "username": "usuario",
                "password": "senha",
                "timeout_ms": 12_345,
                "headless": True,
                "sales_view_name": "FATURAMENTO SALOMAO",
                "receivables_view_name": "VISAO GERAL",
                "payables_view_name": "LANCAR NOTAS SALOMAO",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.linx._require_playwright",
        lambda: (lambda: FakePlaywrightManager(fake_page), FakeTimeoutError),
    )
    monkeypatch.setattr(
        "app.services.linx._login_and_get_report_root",
        lambda page, settings, timeout_error_cls: "https://erp.microvix.com.br",
    )
    monkeypatch.setattr(
        "app.services.linx._select_view",
        lambda page, selector, expected_view_name: selected_views.append(
            (selector, expected_view_name)
        )
        or False,
    )
    monkeypatch.setattr(
        "app.services.linx._apply_date_range",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Receivables sync should not overwrite the saved Linx view period.")
        ),
    )
    monkeypatch.setattr(
        "app.services.linx._download_report",
        lambda page, export_selector: ("FaturasaReceberporPeriodo.xls", b"conteudo"),
    )

    filename, content = download_linx_receivables_report(
        company,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert filename == "FaturasaReceberporPeriodo.xls"
    assert content == b"conteudo"
    assert selected_views == [("#form1_id_visao", "VISAO GERAL")]
    assert fake_page.clicks == ["input[name='form1_SubmitVisao']"]
    assert fake_page.waited_urls == ["**/listagem_relatorio_periodo.asp**"]
    assert all("Prosseguir" not in selector for selector in fake_page.clicks)


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
    company.linx_auto_sync_last_run_at = datetime(2026, 4, 5, 22, 0)
    session.commit()
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
        assert initial.payables_view_name == "LANCAR NOTAS SALOMAO"
        assert initial.has_password is False

        update_response = client.put(
            "/api/v1/company-settings/linx",
            json={
                "base_url": "https://erp.microvix.com.br",
                "username": "usuario.linx",
                "password": "senha-super-secreta",
                "sales_view_name": "FATURAMENTO SALOMAO",
                "receivables_view_name": "CREDIARIO SALOMAO",
                "payables_view_name": "LANCAR NOTAS SALOMAO",
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
        assert body["payables_view_name"] == "LANCAR NOTAS SALOMAO"
        assert body["auto_sync_last_run_at"] is not None
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
                "payables_view_name": "LANCAR NOTAS SALOMAO",
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

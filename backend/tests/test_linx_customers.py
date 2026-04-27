from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.linx import LinxCustomer
from app.db.models.security import Company
from app.services.linx_customers import sync_linx_customers


def _build_session() -> tuple[Session, Company]:
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
    session.commit()
    session.refresh(company)
    return session, company


def test_sync_linx_customers_persists_birth_date_from_linx_payload(monkeypatch) -> None:
    session, company = _build_session()

    monkeypatch.setattr(
        "app.services.linx_customers.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )
    monkeypatch.setattr(
        "app.services.linx_customers._fetch_linx_rows",
        lambda settings, *, method_name, parameters: (
            b"<xml />",
            [
                {
                    "portal": "10994",
                    "cod_cliente": "1001",
                    "razao_cliente": "Maria da Silva",
                    "nome_cliente": "Maria",
                    "doc_cliente": "123.456.789-01",
                    "tipo_cliente": "F",
                    "tipo_cadastro": "C",
                    "ativo": "S",
                    "data_nascimento": "1988-04-20",
                    "dt_update": "2026-04-20T08:00:00",
                    "timestamp": "42",
                }
            ],
        ),
    )

    try:
        result = sync_linx_customers(session, company)

        assert "1 novo(s)" in result.message
        customer = (
            session.query(LinxCustomer)
            .filter_by(company_id=company.id, linx_code=1001)
            .one()
        )
        assert customer.birth_date == date(1988, 4, 20)
    finally:
        session.close()


def test_sync_linx_customers_full_refresh_backfills_existing_birth_date(monkeypatch) -> None:
    session, company = _build_session()
    session.add(
        LinxCustomer(
            company_id=company.id,
            linx_code=1001,
            legal_name="Cliente Existente",
            registration_type="C",
            is_active=True,
            anonymous_customer=False,
            linx_row_timestamp=42,
        )
    )
    session.commit()
    captured_parameters: list[dict[str, str]] = []

    monkeypatch.setattr(
        "app.services.linx_customers.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )

    def fake_fetch(settings, *, method_name, parameters):
        captured_parameters.append(parameters)
        return (
            b"<xml />",
            [
                {
                    "portal": "10994",
                    "cod_cliente": "1001",
                    "razao_cliente": "Cliente Existente",
                    "tipo_cliente": "F",
                    "tipo_cadastro": "C",
                    "ativo": "S",
                    "data_nascimento": "1988-04-20T00:00:00",
                    "dt_update": "2020-01-01T08:00:00",
                    "timestamp": "42",
                }
            ],
        )

    monkeypatch.setattr("app.services.linx_customers._fetch_linx_rows", fake_fetch)

    try:
        result = sync_linx_customers(session, company, full_refresh=True)

        assert "1 atualizado(s)" in result.message
        assert captured_parameters[0]["timestamp"] == "0"
        customer = (
            session.query(LinxCustomer)
            .filter_by(company_id=company.id, linx_code=1001)
            .one()
        )
        assert customer.birth_date == date(1988, 4, 20)
    finally:
        session.close()

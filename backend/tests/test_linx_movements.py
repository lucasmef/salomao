from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxMovement, LinxProduct
from app.db.models.security import Company, User
from app.schemas.imports import ImportResult
from app.schemas.linx_movements import (
    LinxMovementDirectoryRead,
    LinxMovementDirectorySummaryRead,
    LinxMovementListItemRead,
)
from app.services.linx_movements import (
    _collect_rows,
    list_linx_movements,
    list_linx_sales_report,
    sync_linx_movements,
)


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


def test_sync_linx_movements_filters_relevant_natures(monkeypatch) -> None:
    session, company, _ = _build_session()
    first_rows = [
        {
            "portal": "10994",
            "empresa": "1",
            "transacao": "1001",
            "documento": "8023",
            "serie": "2",
            "data_documento": "2026-04-01T00:00:00",
            "data_lancamento": "2026-04-01T00:00:00",
            "codigo_cliente": "1",
            "id_cfop": "5102",
            "desc_cfop": "Venda de mercadoria adquirida ou recebida de terceiros",
            "cod_vendedor": "7",
            "quantidade": "1",
            "preco_custo": "289.9000",
            "valor_liquido": "605.9005",
            "valor_total": "637.7900",
            "desconto": "68.2000",
            "operacao": "S",
            "tipo_transacao": "V",
            "cod_produto": "26436",
            "cod_barra": "7900214309780",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "sale-1",
            "obs": "",
            "preco_unitario": "637.7900",
            "natureza_operacao": "S - VENDA DE MERCADORIA",
            "cod_natureza_operacao": "5.102",
            "dt_update": "2026-04-01T11:56:00",
            "ordem": "1",
            "timestamp": "16042434",
        },
        {
            "portal": "10994",
            "empresa": "1",
            "transacao": "1002",
            "documento": "3596",
            "serie": "2",
            "data_documento": "2026-04-02T00:00:00",
            "data_lancamento": "2026-04-02T00:00:00",
            "codigo_cliente": "1",
            "id_cfop": "1201",
            "desc_cfop": "Devolucao de venda",
            "cod_vendedor": "7",
            "quantidade": "1",
            "preco_custo": "289.9000",
            "valor_liquido": "605.9005",
            "valor_total": "637.7900",
            "desconto": "0.0000",
            "operacao": "DS",
            "tipo_transacao": "",
            "cod_produto": "26436",
            "cod_barra": "7900214309780",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "sale-return-1",
            "obs": "",
            "preco_unitario": "637.7900",
            "natureza_operacao": "D- DEVOLUÇÃO DE VENDA DE MERCADORIA",
            "cod_natureza_operacao": "1.201",
            "dt_update": "2026-04-02T11:56:00",
            "ordem": "1",
            "timestamp": "16042435",
        },
        {
            "portal": "10994",
            "empresa": "1",
            "transacao": "1003",
            "documento": "308913",
            "serie": "1",
            "data_documento": "2026-03-25T00:00:00",
            "data_lancamento": "2026-04-02T00:00:00",
            "codigo_cliente": "1549",
            "id_cfop": "1102",
            "desc_cfop": "Compra para comercialização",
            "cod_vendedor": "1",
            "quantidade": "3",
            "preco_custo": "90.4500",
            "valor_liquido": "271.3500",
            "valor_total": "271.3500",
            "desconto": "0.0000",
            "operacao": "E",
            "tipo_transacao": "",
            "cod_produto": "26529",
            "cod_barra": "123",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "purchase-1",
            "obs": "",
            "preco_unitario": "90.4500",
            "natureza_operacao": "E - COMPRA DE MERCADORIAS",
            "cod_natureza_operacao": "1.102",
            "dt_update": "2026-04-02T10:51:00",
            "ordem": "1",
            "timestamp": "16042821",
        },
        {
            "portal": "10994",
            "empresa": "1",
            "transacao": "1004",
            "documento": "9999",
            "serie": "1",
            "data_documento": "2026-03-25T00:00:00",
            "data_lancamento": "2026-04-03T00:00:00",
            "codigo_cliente": "1549",
            "id_cfop": "1949",
            "desc_cfop": "Outras saídas",
            "cod_vendedor": "1",
            "quantidade": "1",
            "preco_custo": "0.0000",
            "valor_liquido": "0.0000",
            "valor_total": "0.0000",
            "desconto": "0.0000",
            "operacao": "S",
            "tipo_transacao": "",
            "cod_produto": "26529",
            "cod_barra": "123",
            "cancelado": "N",
            "excluido": "N",
            "identificador": "ignored",
            "obs": "",
            "preco_unitario": "0.0000",
            "natureza_operacao": "IGNORAR",
            "cod_natureza_operacao": "54",
            "dt_update": "2026-04-03T10:51:00",
            "ordem": "1",
            "timestamp": "16042822",
        },
    ]
    second_rows = [
        {
            **first_rows[0],
            "cancelado": "S",
            "timestamp": "16050000",
        }
    ]
    calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.linx_movements.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )

    def fake_collect_rows(settings, *, start_timestamp, hasher):
        calls["count"] += 1
        return first_rows if calls["count"] == 1 else second_rows

    monkeypatch.setattr("app.services.linx_movements._collect_rows", fake_collect_rows)

    try:
        first = sync_linx_movements(session, company)
        assert "3 novo(s)" in first.message
        assert session.query(LinxMovement).filter_by(company_id=company.id).count() == 3

        second = sync_linx_movements(session, company)
        assert "1 removido(s)" in second.message
        assert session.query(LinxMovement).filter_by(company_id=company.id).count() == 2
    finally:
        session.close()


def test_sync_linx_movements_accepts_historical_inactive_natures(monkeypatch) -> None:
    session, company, _ = _build_session()

    monkeypatch.setattr(
        "app.services.linx_movements.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )
    monkeypatch.setattr(
        "app.services.linx_movements._collect_rows",
        lambda settings, *, start_timestamp, hasher: [
            {
                "portal": "10994",
                "empresa": "1",
                "transacao": "3001",
                "documento": "9101",
                "serie": "1",
                "data_documento": "2020-01-02T00:00:00",
                "data_lancamento": "2020-01-02T00:00:00",
                "codigo_cliente": "1",
                "cod_vendedor": "7",
                "quantidade": "1",
                "preco_custo": "10.0000",
                "valor_liquido": "20.0000",
                "valor_total": "20.0000",
                "desconto": "0.0000",
                "operacao": "S",
                "tipo_transacao": "V",
                "cod_produto": "26436",
                "cod_barra": "7900214309780",
                "cancelado": "N",
                "excluido": "N",
                "identificador": "sale-historical",
                "obs": "",
                "preco_unitario": "20.0000",
                "natureza_operacao": "S - NOVA VENDA DE MERCADORIA",
                "cod_natureza_operacao": "36",
                "dt_update": "2020-01-02T11:56:00",
                "ordem": "1",
                "timestamp": "3711881",
            },
            {
                "portal": "10994",
                "empresa": "1",
                "transacao": "3002",
                "documento": "9102",
                "serie": "1",
                "data_documento": "2020-01-03T00:00:00",
                "data_lancamento": "2020-01-03T00:00:00",
                "codigo_cliente": "1",
                "cod_vendedor": "7",
                "quantidade": "1",
                "preco_custo": "10.0000",
                "valor_liquido": "20.0000",
                "valor_total": "20.0000",
                "desconto": "0.0000",
                "operacao": "DS",
                "tipo_transacao": "",
                "cod_produto": "26436",
                "cod_barra": "7900214309780",
                "cancelado": "N",
                "excluido": "N",
                "identificador": "sale-return-historical",
                "obs": "",
                "preco_unitario": "20.0000",
                "natureza_operacao": "D - DEVOLUCAO DE VENDA DE MERCADORIA",
                "cod_natureza_operacao": "999",
                "dt_update": "2020-01-03T11:56:00",
                "ordem": "1",
                "timestamp": "3711882",
            },
        ],
    )

    try:
        result = sync_linx_movements(session, company)
        assert "2 novo(s)" in result.message
        saved = (
            session.query(LinxMovement)
            .filter_by(company_id=company.id)
            .order_by(LinxMovement.linx_transaction)
            .all()
        )
        assert len(saved) == 2
        assert saved[0].movement_type == "sale"
        assert saved[1].movement_type == "sale_return"
    finally:
        session.close()


def test_sync_linx_movements_initial_load_skips_existing_lookup(monkeypatch) -> None:
    session, company, _ = _build_session()

    monkeypatch.setattr(
        "app.services.linx_movements.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )
    monkeypatch.setattr(
        "app.services.linx_movements._collect_rows",
        lambda settings, *, start_timestamp, hasher: [
            {
                "portal": "10994",
                "empresa": "1",
                "transacao": "2001",
                "documento": "9001",
                "serie": "1",
                "data_documento": "2026-04-01T00:00:00",
                "data_lancamento": "2026-04-01T00:00:00",
                "codigo_cliente": "1",
                "cod_vendedor": "7",
                "quantidade": "1",
                "preco_custo": "10.0000",
                "valor_liquido": "20.0000",
                "valor_total": "20.0000",
                "desconto": "0.0000",
                "operacao": "S",
                "tipo_transacao": "V",
                "cod_produto": "26436",
                "cod_barra": "7900214309780",
                "cancelado": "N",
                "excluido": "N",
                "identificador": "sale-2001",
                "obs": "",
                "preco_unitario": "20.0000",
                "natureza_operacao": "S - VENDA DE MERCADORIA",
                "cod_natureza_operacao": "5.102",
                "dt_update": "2026-04-01T11:56:00",
                "ordem": "1",
                "timestamp": "16042499",
            }
        ],
    )

    def fail_load_existing_rows(*args, **kwargs):
        raise AssertionError("initial full load should not query existing rows in bulk")

    monkeypatch.setattr("app.services.linx_movements._load_existing_rows", fail_load_existing_rows)

    try:
        result = sync_linx_movements(session, company)
        assert "1 novo(s)" in result.message
        assert session.query(LinxMovement).filter_by(company_id=company.id).count() == 1
    finally:
        session.close()


def test_collect_rows_continues_after_short_page(monkeypatch) -> None:
    pages = [
        (
            b"page-1",
            [
                {"transacao": "1", "timestamp": "10"},
                {"transacao": "2", "timestamp": "11"},
            ],
        ),
        (
            b"page-2",
            [
                {"transacao": "3", "timestamp": "12"},
            ],
        ),
        (b"page-3", []),
    ]
    calls = {"count": 0}

    def fake_fetch(settings, *, method_name, parameters):
        index = calls["count"]
        calls["count"] += 1
        return pages[index]

    monkeypatch.setattr("app.services.linx_movements._fetch_linx_rows", fake_fetch)

    rows = _collect_rows(
        type(
            "Settings",
            (),
            {
                "base_url": "https://example.com",
                "cnpj": "13092113000106",
                "api_key": "teste",
            },
        )(),
        start_timestamp=0,
        hasher=hashlib.sha256(),
    )

    assert [row["transacao"] for row in rows] == ["1", "2", "3"]
    assert calls["count"] == 3


def test_list_linx_movements_paginates_and_joins_products() -> None:
    session, company, _ = _build_session()
    try:
        session.add(
            LinxProduct(
                company_id=company.id,
                linx_code=26436,
                description="CALCA TESTE",
                reference="REF-1",
                collection_name="Inverno 2026",
            )
        )
        session.add_all(
            [
                LinxMovement(
                    company_id=company.id,
                    linx_transaction=1,
                    movement_group="sale",
                    movement_type="sale",
                    product_code=26436,
                    total_amount=Decimal("100.00"),
                    launch_date=datetime(2026, 4, 7),
                    nature_code="5.102",
                    nature_description="S - VENDA DE MERCADORIA",
                ),
                LinxMovement(
                    company_id=company.id,
                    linx_transaction=2,
                    movement_group="sale",
                    movement_type="sale_return",
                    product_code=26436,
                    total_amount=Decimal("20.00"),
                    launch_date=datetime(2026, 4, 6),
                    nature_code="1.201",
                    nature_description="D- DEVOLUÇÃO DE VENDA DE MERCADORIA",
                ),
                LinxMovement(
                    company_id=company.id,
                    linx_transaction=3,
                    movement_group="purchase",
                    movement_type="purchase",
                    product_code=99999,
                    total_amount=Decimal("80.00"),
                    launch_date=datetime(2026, 4, 5),
                    nature_code="1.102",
                    nature_description="E - COMPRA DE MERCADORIAS",
                ),
            ]
        )
        session.commit()

        response = list_linx_movements(session, company, page=1, page_size=2, search="CALCA")
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 10
        assert response.summary.sales_total_amount == Decimal("100.00")
        assert response.summary.sales_return_total_amount == Decimal("20.00")
        assert response.summary.purchases_total_amount == Decimal("80.00")
        assert len(response.items) == 2
        assert response.items[0].product_description == "CALCA TESTE"
        assert response.items[0].collection_name == "Inverno 2026"
    finally:
        session.close()


def test_linx_sales_report_reuses_grouped_coalesce_expressions_for_postgres() -> None:
    class CaptureDb:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            raise RuntimeError("captured")

    db = CaptureDb()
    company = SimpleNamespace(id="company-1")

    try:
        list_linx_sales_report(
            db,  # type: ignore[arg-type]
            company,  # type: ignore[arg-type]
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
        )
    except RuntimeError as error:
        assert str(error) == "captured"

    compiled = str(db.statement.compile(dialect=postgresql.dialect()))
    assert "GROUP BY coalesce(linx_movements.document_number, %(coalesce_1)s)" in compiled
    assert "coalesce_6" not in compiled
    assert "coalesce_7" not in compiled


def test_linx_movements_endpoints_smoke(monkeypatch) -> None:
    session, company, user = _build_session()
    captured: dict[str, object] = {}

    def fake_sync(db, current_company, *, full_refresh=False):
        captured["sync"] = (db, current_company.id, full_refresh)
        batch = ImportBatch(
            company_id=company.id,
            source_type="linx_movements",
            filename="linx-movements-full.xml",
            status="processed",
            records_total=1,
            records_valid=1,
            records_invalid=0,
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return ImportResult(batch=batch, message="movements ok")

    def fake_list(
        db,
        current_company,
        *,
        page=1,
        page_size=50,
        search=None,
        group="all",
        movement_type="all",
    ):
        captured["list"] = (db, current_company.id, page, page_size, search, group, movement_type)
        return LinxMovementDirectoryRead(
            generated_at=datetime.now(timezone.utc),
            summary=LinxMovementDirectorySummaryRead(
                total_count=1,
                sales_total_amount=Decimal("100.00"),
                sales_return_total_amount=Decimal("0"),
                purchases_total_amount=Decimal("0"),
                purchase_returns_total_amount=Decimal("0"),
            ),
            items=[
                LinxMovementListItemRead(
                    id="1",
                    linx_transaction=1001,
                    movement_group="sale",
                    movement_type="sale",
                    product_code=26436,
                    product_description="CALCA TESTE",
                    total_amount=Decimal("100.00"),
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
        )

    monkeypatch.setattr("app.api.routes.imports.sync_linx_movements", fake_sync)
    monkeypatch.setattr("app.api.routes.linx_movements.list_linx_movements", fake_list)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        sync_response = client.post(
            "/api/v1/imports/linx-movements/sync",
            json={"full_refresh": True},
        )
        list_response = client.get(
            "/api/v1/linx-movements"
            "?page=2&page_size=25&search=calca&group=sale&movement_type=sale"
        )

        assert sync_response.status_code == 201
        assert sync_response.json()["message"] == "movements ok"
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert captured["sync"] == (session, company.id, True)
        assert captured["list"] == (session, company.id, 2, 25, "calca", "sale", "sale")
    finally:
        client.close()
        session.close()

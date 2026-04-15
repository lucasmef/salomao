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
from app.db.models.linx import LinxProduct
from app.db.models.security import Company, User
from app.schemas.imports import ImportResult
from app.schemas.linx_products import (
    LinxProductDirectoryRead,
    LinxProductDirectorySummaryRead,
    LinxProductListItemRead,
    LinxProductSearchRead,
)
from app.services.linx_products import list_linx_products, normalize_collection_name, search_linx_products, sync_linx_products


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


def test_normalize_collection_name_strips_only_current_prefix() -> None:
    assert normalize_collection_name("1 - Inverno 2026") == "Inverno 2026"
    assert normalize_collection_name("Verao 2026") == "Verao 2026"


def test_sync_linx_products_full_then_incremental(monkeypatch) -> None:
    session, company, _ = _build_session()
    collect_calls = {"products": 0, "details": 0}

    full_product_rows = [
        {
            "portal": "10994",
            "cod_produto": "26519",
            "cod_barra": "26519",
            "nome": "CALCA TESTE",
            "referencia": "540281",
            "unidade": "PC",
            "desc_cor": "MARROM",
            "desc_tamanho": "36",
            "desc_setor": "1-GERAL",
            "desc_linha": "CALCAS",
            "desc_marca": "CANTAO",
            "desc_colecao": "1 - Inverno 2026",
            "dt_update": "2026-04-02T10:51:00",
            "cod_fornecedor": "12",
            "desativado": "N",
            "id_colecao": "21",
            "dt_inclusao": "2026-03-10T11:52:00",
            "timestamp": "16042000",
        }
    ]
    full_detail_rows = [
        {
            "cod_produto": "26519",
            "quantidade": "3.0000",
            "preco_custo": "90.4500",
            "preco_venda": "217.7900",
            "custo_medio": "90.4500",
            "empresa": "1",
            "localizacao": "ARARA 01",
            "timestamp": "16042317",
        }
    ]
    incremental_detail_rows = [
        {
            "cod_produto": "26519",
            "quantidade": "4.0000",
            "preco_custo": "95.0000",
            "preco_venda": "220.0000",
            "custo_medio": "95.0000",
            "empresa": "1",
            "localizacao": "ARARA 01",
            "timestamp": "16050000",
        }
    ]

    monkeypatch.setattr(
        "app.services.linx_products.load_linx_api_settings",
        lambda current_company: type(
            "Settings",
            (),
            {"base_url": "https://example.com", "cnpj": "13092113000106", "api_key": "teste"},
        )(),
    )

    def fake_collect_product_rows(settings, *, start_timestamp, hasher):
        collect_calls["products"] += 1
        return full_product_rows if collect_calls["products"] == 1 else []

    def fake_collect_detail_rows(settings, *, start_timestamp, hasher):
        collect_calls["details"] += 1
        return full_detail_rows if collect_calls["details"] == 1 else incremental_detail_rows

    monkeypatch.setattr("app.services.linx_products._collect_product_rows", fake_collect_product_rows)
    monkeypatch.setattr("app.services.linx_products._collect_detail_rows", fake_collect_detail_rows)
    monkeypatch.setattr("app.services.linx_products._fetch_products_by_code", lambda settings, codes, *, hasher: {})
    monkeypatch.setattr(
        "app.services.linx_products._resolve_supplier_names",
        lambda db, *, company_id, settings, supplier_codes, hasher: {12: "BIAMAR MALHAS E CONFECCOES LTDA"},
    )

    try:
        first = sync_linx_products(session, company)
        assert "1 novo(s)" in first.message

        product = session.query(LinxProduct).filter_by(company_id=company.id, linx_code=26519).one()
        assert product.description == "CALCA TESTE"
        assert product.collection_name == "Inverno 2026"
        assert product.supplier_name == "BIAMAR MALHAS E CONFECCOES LTDA"
        assert product.price_cost == Decimal("90.4500")
        assert product.price_sale == Decimal("217.7900")
        assert product.stock_quantity == Decimal("3.0000")

        second = sync_linx_products(session, company)
        assert "1 atualizado(s)" in second.message

        session.refresh(product)
        assert product.price_cost == Decimal("95.0000")
        assert product.price_sale == Decimal("220.0000")
        assert product.stock_quantity == Decimal("4.0000")
        assert product.linx_detail_row_timestamp == 16050000
    finally:
        session.close()


def test_list_linx_products_paginates_and_filters() -> None:
    session, company, _ = _build_session()
    try:
        session.add_all(
            [
                LinxProduct(
                    company_id=company.id,
                    linx_code=1,
                    description="BLUSA TESTE",
                    reference="REF1",
                    supplier_name="Fornecedor A",
                    collection_name="Inverno 2026",
                    is_active=True,
                ),
                LinxProduct(
                    company_id=company.id,
                    linx_code=2,
                    description="CALCA TESTE",
                    reference="REF2",
                    supplier_name="Fornecedor B",
                    collection_name="Verao 2026",
                    is_active=False,
                ),
                LinxProduct(
                    company_id=company.id,
                    linx_code=3,
                    description="CAMISA TESTE",
                    reference="REF3",
                    supplier_name=None,
                    collection_name=None,
                    is_active=True,
                ),
            ]
        )
        session.commit()

        response = list_linx_products(session, company, page=1, page_size=2, search="TESTE", status="active")
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 10
        assert response.summary.total_count == 3
        assert response.summary.active_count == 2
        assert len(response.items) == 2
        assert all(item.is_active for item in response.items)
    finally:
        session.close()


def test_search_linx_products_matches_chunks_and_brand() -> None:
    session, company, _ = _build_session()
    try:
        session.add_all(
            [
                LinxProduct(
                    company_id=company.id,
                    linx_code=101,
                    description="Calca Maria Preta 38",
                    reference="CAL-MAR-38",
                    brand_name="Lafort",
                    collection_name="Inverno 2026",
                    stock_quantity=Decimal("5.0000"),
                    price_sale=Decimal("199.9000"),
                    is_active=True,
                ),
                LinxProduct(
                    company_id=company.id,
                    linx_code=102,
                    description="Blusa Azul 40",
                    reference="BLU-AZU-40",
                    brand_name="Outra Marca",
                    collection_name="Verao 2026",
                    stock_quantity=Decimal("2.0000"),
                    price_sale=Decimal("149.9000"),
                    is_active=True,
                ),
            ]
        )
        session.commit()

        for query in ("calca 38", "Mari preta 38", "Mari 38", "Mari Lafort 38"):
            response = search_linx_products(session, company, query=query, limit=10)
            assert response.total >= 1
            assert response.items[0].linx_code == 101
            assert response.items[0].brand_name == "Lafort"
    finally:
        session.close()


def test_linx_products_endpoints_smoke(monkeypatch) -> None:
    session, company, user = _build_session()
    captured: dict[str, object] = {}

    def fake_sync_linx_products(db, current_company, *, full_refresh=False):
        captured["sync"] = (db, current_company.id, full_refresh)
        batch = ImportBatch(
            company_id=company.id,
            source_type="linx_products",
            filename="linx-products-full.xml",
            status="processed",
            records_total=1,
            records_valid=1,
            records_invalid=0,
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return ImportResult(batch=batch, message="products ok")

    def fake_list_linx_products(db, current_company, *, page=1, page_size=50, search=None, status="all"):
        captured["list"] = (db, current_company.id, page, page_size, search, status)
        return LinxProductDirectoryRead(
            generated_at=datetime.now(timezone.utc),
            summary=LinxProductDirectorySummaryRead(
                total_count=1,
                active_count=1,
                inactive_count=0,
                with_supplier_count=1,
                with_collection_count=1,
            ),
            items=[
                LinxProductListItemRead(
                    id="1",
                    linx_code=26519,
                    description="CALCA TESTE",
                    supplier_name="Fornecedor A",
                    collection_name="Inverno 2026",
                    is_active=True,
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
        )

    def fake_search_linx_products(db, current_company, *, query, limit=20):
        captured["search"] = (db, current_company.id, query, limit)
        return LinxProductSearchRead(
            generated_at=datetime.now(timezone.utc),
            query=query,
            total=1,
            items=[
                LinxProductListItemRead(
                    id="1",
                    linx_code=26519,
                    description="CALCA TESTE",
                    reference="540281",
                    brand_name="LAFORT",
                    collection_name="Inverno 2026",
                    stock_quantity=Decimal("3.0000"),
                    price_sale=Decimal("217.7900"),
                    is_active=True,
                )
            ],
        )

    monkeypatch.setattr("app.api.routes.imports.sync_linx_products", fake_sync_linx_products)
    monkeypatch.setattr("app.api.routes.linx_products.list_linx_products", fake_list_linx_products)
    monkeypatch.setattr("app.api.routes.linx_products.search_linx_products", fake_search_linx_products)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        sync_response = client.post("/api/v1/imports/linx-products/sync", json={"full_refresh": True})
        list_response = client.get("/api/v1/linx-products?page=2&page_size=25&search=calca&status=active")
        search_response = client.get("/api/v1/linx-products/search?q=mari%20lafort%2038&limit=15")

        assert sync_response.status_code == 201
        assert sync_response.json()["message"] == "products ok"
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert search_response.status_code == 200
        assert search_response.json()["items"][0]["brand_name"] == "LAFORT"
        assert captured["sync"] == (session, company.id, True)
        assert captured["list"] == (session, company.id, 2, 25, "calca", "active")
        assert captured["search"] == (session, company.id, "mari lafort 38", 15)
    finally:
        client.close()
        session.close()

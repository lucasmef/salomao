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
from app.db.base import Base
from app.db.models.finance import FinancialEntry
from app.db.models.security import Company, User


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
        email="admin-filters@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return session, company, user


def _add_entry(session: Session, company: Company, *, title: str, amount: str) -> None:
    entry_date = date(2026, 4, 8)
    session.add(
        FinancialEntry(
            company_id=company.id,
            entry_type="income",
            status="planned",
            title=title,
            issue_date=entry_date,
            competence_date=entry_date,
            due_date=entry_date,
            principal_amount=Decimal(amount),
            total_amount=Decimal(amount),
            paid_amount=Decimal("0.00"),
            source_system="manual",
            is_deleted=False,
        )
    )
    session.commit()


def test_entries_endpoint_filters_by_amount_range() -> None:
    session, company, user = _build_test_session()
    _add_entry(session, company, title="Fatura 980", amount="980.00")
    _add_entry(session, company, title="Fatura 1000", amount="1000.00")
    _add_entry(session, company, title="Fatura 1099", amount="1099.00")
    _add_entry(session, company, title="Fatura 1200", amount="1200.00")

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        response = client.get(
            "/api/v1/entries",
            params={
                "amount_min": "990.00",
                "amount_max": "1100.00",
                "page": "1",
                "page_size": "50",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert [item["title"] for item in payload["items"]] == ["Fatura 1099", "Fatura 1000"]
    finally:
        client.close()
        session.close()

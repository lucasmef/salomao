from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.linx import LinxCustomer, LinxMovement
from app.db.models.security import Company
from app.services.dashboard import build_dashboard_week_birthdays


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


def test_build_dashboard_week_birthdays_lists_only_eligible_customers_for_current_week() -> None:
    session, company = _build_session()

    session.add_all(
        [
            LinxCustomer(
                company_id=company.id,
                linx_code=1001,
                legal_name="Ana Semana",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1990, 4, 21),
            ),
            LinxCustomer(
                company_id=company.id,
                linx_code=1002,
                legal_name="Bruno Semana",
                registration_type="A",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1988, 4, 24),
            ),
            LinxCustomer(
                company_id=company.id,
                linx_code=1003,
                legal_name="Carla Antiga",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1985, 4, 22),
            ),
            LinxCustomer(
                company_id=company.id,
                linx_code=1004,
                legal_name="Diego Fora",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1987, 4, 28),
            ),
        ]
    )
    session.add_all(
        [
            LinxMovement(
                company_id=company.id,
                linx_transaction=1,
                movement_group="sale",
                movement_type="sale",
                customer_code=1001,
                product_code=10,
                issue_date=datetime(2025, 5, 10, 10, 0, 0),
                launch_date=datetime(2025, 5, 10, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
            LinxMovement(
                company_id=company.id,
                linx_transaction=2,
                movement_group="sale",
                movement_type="sale",
                customer_code=1002,
                product_code=11,
                issue_date=datetime(2026, 4, 2, 10, 0, 0),
                launch_date=datetime(2026, 4, 2, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
            LinxMovement(
                company_id=company.id,
                linx_transaction=3,
                movement_group="sale",
                movement_type="sale",
                customer_code=1003,
                product_code=12,
                issue_date=datetime(2024, 4, 18, 10, 0, 0),
                launch_date=datetime(2024, 4, 18, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
            LinxMovement(
                company_id=company.id,
                linx_transaction=4,
                movement_group="sale",
                movement_type="sale_return",
                customer_code=1004,
                product_code=13,
                issue_date=datetime(2026, 4, 10, 10, 0, 0),
                launch_date=datetime(2026, 4, 10, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
        ]
    )
    session.commit()

    try:
        result = build_dashboard_week_birthdays(
            session,
            company,
            today=date(2026, 4, 20),
        )

        assert result.week_label == "Seg 20/04 a Dom 26/04"
        assert [item.customer_name for item in result.items] == ["Ana Semana", "Bruno Semana"]
        assert result.items[0].birthday_date == date(2026, 4, 21)
        assert result.items[1].birthday_date == date(2026, 4, 24)
    finally:
        session.close()

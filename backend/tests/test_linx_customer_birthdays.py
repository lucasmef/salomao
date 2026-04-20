from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.linx import LinxCustomer, LinxMovement
from app.db.models.security import Company
from app.services.linx_customer_birthdays import send_linx_customer_birthday_alert


def _build_session() -> tuple[Session, Company]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    company = Company(
        legal_name="Empresa Teste Ltda",
        trade_name="Salomao",
        linx_auto_sync_alert_email="alertas@example.com",
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return session, company


def test_send_linx_customer_birthday_alert_filters_recent_sales_and_dedupes_same_day(monkeypatch) -> None:
    session, company = _build_session()
    email_calls: list[tuple[str, str, list[str] | None]] = []

    session.add_all(
        [
            LinxCustomer(
                company_id=company.id,
                linx_code=1001,
                legal_name="Cliente Elegivel",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1990, 4, 20),
            ),
            LinxCustomer(
                company_id=company.id,
                linx_code=1002,
                legal_name="Cliente Antigo",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1985, 4, 20),
            ),
            LinxCustomer(
                company_id=company.id,
                linx_code=1003,
                legal_name="Cliente Devolucao",
                registration_type="C",
                is_active=True,
                anonymous_customer=False,
                birth_date=date(1987, 4, 20),
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
                issue_date=datetime(2025, 6, 15, 10, 0, 0),
                launch_date=datetime(2025, 6, 15, 10, 0, 0),
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
                issue_date=datetime(2023, 4, 19, 10, 0, 0),
                launch_date=datetime(2023, 4, 19, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
            LinxMovement(
                company_id=company.id,
                linx_transaction=3,
                movement_group="sale",
                movement_type="sale_return",
                customer_code=1003,
                product_code=12,
                issue_date=datetime(2026, 4, 10, 10, 0, 0),
                launch_date=datetime(2026, 4, 10, 10, 0, 0),
                quantity=Decimal("1"),
                total_amount=Decimal("100.00"),
                net_amount=Decimal("100.00"),
            ),
        ]
    )
    session.commit()

    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("SMTP_HOST", "mail.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "alerts@example.com")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.linx_customer_birthdays.send_email",
        lambda subject, body, *, recipients=None, html_body=None: email_calls.append((subject, body, recipients)),
    )

    try:
        message = send_linx_customer_birthday_alert(
            session,
            company,
            now=datetime(2026, 4, 20, 9, 5),
        )

        assert message == "Alerta de aniversariantes enviado com sucesso. 1 cliente(s) elegivel(is)."
        assert len(email_calls) == 1
        assert email_calls[0][2] == ["alertas@example.com"]
        assert "Cliente Elegivel" in email_calls[0][1]
        assert "Cliente Antigo" not in email_calls[0][1]
        assert "Cliente Devolucao" not in email_calls[0][1]

        second_message = send_linx_customer_birthday_alert(
            session,
            company,
            now=datetime(2026, 4, 20, 10, 0),
        )
        assert second_message is None
        assert len(email_calls) == 1
        assert company.linx_birthday_alert_last_sent_at is not None
    finally:
        get_settings.cache_clear()
        session.close()

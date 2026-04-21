from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.accounts import create_account, update_account
from app.db.base import Base
from app.db.models.finance import FinancialEntry
from app.db.models.security import Company, User
from app.schemas.account import AccountCreate
from app.services.cashflow import build_cashflow_overview


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _build_company_and_user(session: Session) -> tuple[Company, User]:
    company = Company(
        legal_name="Empresa Teste Ltda",
        trade_name="Empresa Teste",
        default_currency="BRL",
    )
    user = User(
        company=company,
        full_name="Admin Teste",
        email="admin-saldo@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
    )
    session.add_all([company, user])
    session.commit()
    return company, user


def _add_settled_income(session: Session, company_id: str, account_id: str, amount: str) -> None:
    entry = FinancialEntry(
        company_id=company_id,
        account_id=account_id,
        entry_type="income",
        status="settled",
        title="Receita teste",
        issue_date=date(2026, 4, 1),
        competence_date=date(2026, 4, 1),
        due_date=date(2026, 4, 1),
        principal_amount=Decimal(amount),
        total_amount=Decimal(amount),
        paid_amount=Decimal(amount),
        is_deleted=False,
    )
    session.add(entry)
    session.commit()


def test_create_and_update_account_support_exclude_from_balance_flag() -> None:
    session = _build_session()
    try:
        _company, user = _build_company_and_user(session)

        created = create_account(
            AccountCreate(
                name="Conta Reserva",
                account_type="checking",
                exclude_from_balance=True,
            ),
            db=session,
            current_user=user,
        )

        assert created.exclude_from_balance is True

        updated = update_account(
            created.id,
            AccountCreate(
                name="Conta Reserva",
                account_type="checking",
                exclude_from_balance=False,
            ),
            db=session,
            current_user=user,
        )

        assert updated.exclude_from_balance is False
    finally:
        session.close()


def test_cashflow_ignores_excluded_account_in_consolidated_balance_but_keeps_explicit_account_view() -> None:
    session = _build_session()
    try:
        company, user = _build_company_and_user(session)

        included = create_account(
            AccountCreate(
                name="Conta Principal",
                account_type="checking",
                opening_balance=Decimal("100.00"),
            ),
            db=session,
            current_user=user,
        )
        excluded = create_account(
            AccountCreate(
                name="Conta Ignorada",
                account_type="checking",
                opening_balance=Decimal("200.00"),
                exclude_from_balance=True,
            ),
            db=session,
            current_user=user,
        )

        _add_settled_income(session, company.id, included.id, "50.00")
        _add_settled_income(session, company.id, excluded.id, "75.00")

        consolidated = build_cashflow_overview(session, company)
        excluded_only = build_cashflow_overview(session, company, account_id=excluded.id)

        assert consolidated.current_balance == Decimal("150.00")
        assert len(consolidated.account_balances) == 2
        balances = {item.account_id: item for item in consolidated.account_balances}
        assert balances[included.id].current_balance == Decimal("150.00")
        assert balances[included.id].exclude_from_balance is False
        assert balances[excluded.id].current_balance == Decimal("275.00")
        assert balances[excluded.id].exclude_from_balance is True

        assert excluded_only.current_balance == Decimal("275.00")
        assert len(excluded_only.account_balances) == 1
        assert excluded_only.account_balances[0].account_id == excluded.id
    finally:
        session.close()

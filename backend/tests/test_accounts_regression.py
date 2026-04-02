from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.accounts import create_account, update_account
from app.db.base import Base
from app.db.models.finance import Account
from app.db.models.security import Company, User
from app.schemas.account import AccountCreate


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
        email="admin-contas@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
    )
    session.add_all([company, user])
    session.commit()
    return company, user


def test_create_account_keeps_ofx_disabled_by_default() -> None:
    session = _build_session()
    try:
        company, user = _build_company_and_user(session)

        account = create_account(
            AccountCreate(
                name="Conta Caixa",
                account_type="cash",
            ),
            db=session,
            current_user=user,
        )

        persisted = session.get(Account, account.id)
        assert persisted is not None
        assert persisted.company_id == company.id
        assert persisted.import_ofx_enabled is False
        assert persisted.is_active is True
    finally:
        session.close()


def test_update_account_allows_switching_ofx_flag_without_losing_bank_fields() -> None:
    session = _build_session()
    try:
        _company, user = _build_company_and_user(session)
        account = create_account(
            AccountCreate(
                name="Conta Inter",
                account_type="checking",
                bank_code="077",
                branch_number="0001",
                account_number="12345678",
                import_ofx_enabled=False,
            ),
            db=session,
            current_user=user,
        )

        updated = update_account(
            account.id,
            AccountCreate(
                name="Conta Inter Matriz",
                account_type="checking",
                bank_code="077",
                branch_number="9999",
                account_number="87654321",
                opening_balance="100.50",
                is_active=True,
                import_ofx_enabled=True,
            ),
            db=session,
            current_user=user,
        )

        assert updated.name == "Conta Inter Matriz"
        assert updated.bank_code == "077"
        assert updated.branch_number == "9999"
        assert updated.account_number == "87654321"
        assert updated.import_ofx_enabled is True
    finally:
        session.close()


def test_update_account_rejects_account_from_another_company() -> None:
    session = _build_session()
    try:
        _company_one, _user_one = _build_company_and_user(session)
        company_two = Company(
            legal_name="Empresa Dois Ltda",
            trade_name="Empresa Dois",
            default_currency="BRL",
        )
        session.add(company_two)
        session.flush()
        user_two = User(
            company=company_two,
            full_name="Admin Dois",
            email="admin-dois@example.com",
            password_hash="hash",
            role="admin",
            is_active=True,
        )
        foreign_account = Account(
            company_id=company_two.id,
            name="Conta Externa",
            account_type="checking",
        )
        session.add_all([user_two, foreign_account])
        session.commit()

        with pytest.raises(HTTPException, match="Conta nao encontrada") as error:
            update_account(
                foreign_account.id,
                AccountCreate(
                    name="Nao deve atualizar",
                    account_type="checking",
                ),
                db=session,
                current_user=user_two,
            )

        assert error.value.status_code == 404
    finally:
        session.close()


def test_update_account_preserves_inter_secret_material_when_form_is_resubmitted_without_plaintext() -> None:
    session = _build_session()
    try:
        _company, user = _build_company_and_user(session)
        account = create_account(
            AccountCreate(
                name="Conta Inter",
                account_type="checking",
                bank_code="077",
                account_number="123456",
                inter_api_enabled=True,
                inter_api_key="client-id",
                inter_account_number="123456",
                inter_client_secret="client-secret",
                inter_certificate_pem="---CERT---",
                inter_private_key_pem="---KEY---",
            ),
            db=session,
            current_user=user,
        )

        updated = update_account(
            account.id,
            AccountCreate(
                name="Conta Inter Atualizada",
                account_type="checking",
                bank_code="077",
                account_number="123456",
                inter_api_enabled=True,
                inter_api_key="client-id-2",
                inter_account_number="654321",
            ),
            db=session,
            current_user=user,
        )

        assert updated.inter_api_key == "client-id-2"
        assert updated.inter_account_number == "654321"
        assert updated.has_inter_client_secret is True
        assert updated.has_inter_certificate is True
        assert updated.has_inter_private_key is True
    finally:
        session.close()


def test_enabling_inter_api_disables_other_accounts_from_same_company() -> None:
    session = _build_session()
    try:
        _company, user = _build_company_and_user(session)
        first = create_account(
            AccountCreate(
                name="Conta Inter 1",
                account_type="checking",
                inter_api_enabled=True,
                inter_api_key="client-1",
                inter_account_number="111",
                inter_client_secret="secret-1",
                inter_certificate_pem="---CERT-1---",
                inter_private_key_pem="---KEY-1---",
            ),
            db=session,
            current_user=user,
        )
        second = create_account(
            AccountCreate(
                name="Conta Inter 2",
                account_type="checking",
                inter_api_enabled=True,
                inter_api_key="client-2",
                inter_account_number="222",
                inter_client_secret="secret-2",
                inter_certificate_pem="---CERT-2---",
                inter_private_key_pem="---KEY-2---",
            ),
            db=session,
            current_user=user,
        )

        persisted_first = session.get(Account, first.id)
        persisted_second = session.get(Account, second.id)

        assert persisted_first is not None
        assert persisted_second is not None
        assert persisted_first.inter_api_enabled is False
        assert persisted_second.inter_api_enabled is True
    finally:
        session.close()

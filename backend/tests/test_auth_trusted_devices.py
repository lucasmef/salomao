from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import encrypt_text
from app.core.security import generate_mfa_secret, generate_totp_code, hash_password
from app.db.base import Base
from app.db.models.security import Company, User
from app.services.auth import authenticate_login, revoke_mfa_trusted_device, verify_login_mfa


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _configure_server_mode(monkeypatch) -> None:
    monkeypatch.setenv("APP_MODE", "server")
    monkeypatch.setenv("SESSION_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "fedcba9876543210fedcba9876543210")
    monkeypatch.setenv("MFA_TRUSTED_DEVICE_DAYS", "15")
    get_settings.cache_clear()


def _create_user(session: Session) -> tuple[Company, User, str]:
    secret = generate_mfa_secret()
    company = Company(
        legal_name="Empresa Teste Ltda",
        trade_name="Empresa Teste",
        document="12345678000199",
        default_currency="BRL",
        is_active=True,
    )
    session.add(company)
    session.flush()

    user = User(
        company_id=company.id,
        full_name="Operador Teste",
        email="operador@teste.local",
        password_hash=hash_password("senha-super-segura"),
        role="admin",
        is_active=True,
        mfa_enabled=True,
        mfa_secret_encrypted=encrypt_text(secret),
    )
    session.add(user)
    session.commit()
    return company, user, secret


def test_trusted_device_skips_mfa_for_followup_login(monkeypatch) -> None:
    _configure_server_mode(monkeypatch)
    session = _build_session()
    try:
        _, user, secret = _create_user(session)

        login_challenge = authenticate_login(session, user.email, "senha-super-segura")

        assert login_challenge.status == "mfa_required"
        assert login_challenge.pending_token is not None

        login_result = verify_login_mfa(
            session,
            login_challenge.pending_token,
            generate_totp_code(secret),
            remember_device=True,
            trusted_device_user_agent="pytest-agent",
        )

        assert login_result.status == "authenticated"
        assert login_result.trusted_device_token is not None
        assert login_result.trusted_device_expires_at is not None

        trusted_login = authenticate_login(
            session,
            user.email,
            "senha-super-segura",
            trusted_device_token=login_result.trusted_device_token,
        )

        assert trusted_login.status == "authenticated"
        assert trusted_login.pending_token is None
        assert trusted_login.trusted_device_expires_at is not None
    finally:
        session.close()
        get_settings.cache_clear()


def test_revoked_trusted_device_requires_mfa_again(monkeypatch) -> None:
    _configure_server_mode(monkeypatch)
    session = _build_session()
    try:
        _, user, secret = _create_user(session)

        login_challenge = authenticate_login(session, user.email, "senha-super-segura")
        login_result = verify_login_mfa(
            session,
            login_challenge.pending_token,
            generate_totp_code(secret),
            remember_device=True,
        )

        assert login_result.trusted_device_token is not None

        revoke_mfa_trusted_device(session, login_result.trusted_device_token, user)
        session.commit()

        login_after_revoke = authenticate_login(
            session,
            user.email,
            "senha-super-segura",
            trusted_device_token=login_result.trusted_device_token,
        )

        assert login_after_revoke.status == "mfa_required"
        assert login_after_revoke.pending_token is not None
    finally:
        session.close()
        get_settings.cache_clear()

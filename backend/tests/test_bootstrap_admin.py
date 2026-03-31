from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_password
from app.db.base import Base
from app.db.models.security import Company
from app.services.auth import ensure_default_admin


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_bootstrap_admin_requires_explicit_credentials(monkeypatch) -> None:
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    session = _build_session()
    try:
        company = Company(
            legal_name="Empresa Teste Ltda",
            trade_name="Empresa Teste",
            default_currency="BRL",
        )
        session.add(company)
        session.flush()

        with pytest.raises(RuntimeError, match="Primeiro administrador nao configurado"):
            ensure_default_admin(session, company)
    finally:
        session.close()
        get_settings.cache_clear()


def test_bootstrap_admin_uses_environment_credentials(monkeypatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@teste.local")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "senha-inicial-segura")
    get_settings.cache_clear()
    session = _build_session()
    try:
        company = Company(
            legal_name="Empresa Teste Ltda",
            trade_name="Empresa Teste",
            default_currency="BRL",
        )
        session.add(company)
        session.flush()

        user = ensure_default_admin(session, company)

        assert user.email == "admin@teste.local"
        assert verify_password("senha-inicial-segura", user.password_hash)
        assert user.role == "admin"
    finally:
        session.close()
        get_settings.cache_clear()

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.audit import AuditLog
from app.services.security_alerts import alert_on_foreign_access, record_auth_failure


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "false")
    monkeypatch.setenv("SECURITY_ALERT_ALLOWED_COUNTRIES", "BR")
    monkeypatch.setenv("SECURITY_ALERT_FAILURE_WINDOW_SECONDS", "600")
    monkeypatch.setenv("SECURITY_ALERT_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("SECURITY_ALERT_DEDUP_WINDOW_SECONDS", "1800")
    get_settings.cache_clear()


def test_auth_failure_alert_emits_after_threshold(monkeypatch) -> None:
    _configure_settings(monkeypatch)
    session = _build_session()
    try:
        monkeypatch.setattr(
            "app.services.security_alerts._lookup_ip_country",
            lambda client_ip: {"country_code": "BR", "country_name": "Brazil", "asn": "", "as_name": ""},
        )

        emitted = [
            record_auth_failure(
                session,
                client_ip="201.1.1.1",
                email="ataque@teste.local",
                user_agent="pytest",
                reason="invalid_credentials",
                path="/api/v1/auth/login",
            )
            for _ in range(3)
        ]

        session.commit()
        alerts = list(session.scalars(select(AuditLog).where(AuditLog.action == "security_attack_attempt")))

        assert emitted == [False, False, True]
        assert len(alerts) == 1
        assert alerts[0].after_state["failure_count"] == 3
    finally:
        session.close()
        get_settings.cache_clear()


def test_foreign_access_alert_emits_for_non_br_ip(monkeypatch) -> None:
    _configure_settings(monkeypatch)
    session = _build_session()
    try:
        monkeypatch.setattr(
            "app.services.security_alerts._lookup_ip_country",
            lambda client_ip: {
                "country_code": "US",
                "country_name": "United States",
                "asn": "AS15169",
                "as_name": "Google LLC",
            },
        )

        emitted = alert_on_foreign_access(
            session,
            client_ip="8.8.8.8",
            user_agent="pytest",
            email="usuario@teste.local",
            user=None,
            login_status="mfa_required",
        )

        session.commit()
        alerts = list(session.scalars(select(AuditLog).where(AuditLog.action == "security_foreign_access")))

        assert emitted is True
        assert len(alerts) == 1
        assert alerts[0].after_state["country_code"] == "US"
    finally:
        session.close()
        get_settings.cache_clear()

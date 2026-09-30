import json
import smtplib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.routes.company_settings import router
from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.db.base import Base
from app.db.models.audit import AuditLog
from app.db.models.email_settings import EmailSettings
from app.db.session import get_db
from app.services import security_alerts, smtp_settings


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "mail.example.invalid")
    monkeypatch.setenv("SMTP_USERNAME", "old@example.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "previous-secret")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_FROM", "old@example.invalid")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_TO", "recipient@example.invalid")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(smtp_settings, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(router, prefix="/company-settings")

    def dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    user = SimpleNamespace(role="admin", company_id=None, id=None)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, factory, user, app
    engine.dispose()
    get_settings.cache_clear()


def payload(**overrides):
    return {
        "enabled": True,
        "host": "mail.example.invalid",
        "port": 465,
        "encryption": "ssl",
        "username": "alerts@example.invalid",
        "sender": "alerts@example.invalid",
        "recipients": "recipient@example.invalid",
        "password": "new-secret",
        **overrides,
    }


def test_save_encrypts_password_and_redacts_response_and_audit(context):
    client, factory, _, _ = context
    result = client.put("/company-settings/smtp", json=payload())
    assert result.status_code == 200
    assert result.json()["has_password"] is True
    assert "new-secret" not in result.text
    assert "password" not in result.json()
    with factory() as db:
        row = db.get(EmailSettings, 1)
        assert row.password_encrypted.startswith("enc:v1:")
        assert decrypt_text(row.password_encrypted) == "new-secret"
        audit = db.scalar(select(AuditLog))
        assert "new-secret" not in json.dumps(audit.after_state)
        assert "previous-secret" not in json.dumps(audit.before_state)
    assert client.get("/company-settings/smtp").json()["source"] == "database"


def test_blank_password_preserves_saved_secret_and_account_change_requires_new_secret(context):
    client, factory, _, _ = context
    assert client.put("/company-settings/smtp", json=payload()).status_code == 200
    assert client.put("/company-settings/smtp", json=payload(password="")).status_code == 200
    with factory() as db:
        assert decrypt_text(db.get(EmailSettings, 1).password_encrypted) == "new-secret"
    assert (
        client.put(
            "/company-settings/smtp", json=payload(username="other@example.invalid", password=None)
        ).status_code
        == 400
    )


@pytest.mark.parametrize("role", ["operador", "consulta"])
def test_non_admin_cannot_read_save_or_test(context, role):
    client, _, user, _ = context
    user.role = role
    assert client.get("/company-settings/smtp").status_code == 403
    assert client.put("/company-settings/smtp", json=payload()).status_code == 403
    assert (
        client.post(
            "/company-settings/smtp/test", json=payload(recipient="test@example.invalid")
        ).status_code
        == 403
    )


def test_authentication_is_required(context):
    client, _, _, app = context
    del app.dependency_overrides[get_current_user]
    assert client.get("/company-settings/smtp").status_code == 401


def test_unsaved_test_uses_entered_secret_even_when_disabled_and_does_not_persist(
    context, monkeypatch
):
    client, factory, _, _ = context
    delivered = []
    monkeypatch.setattr(
        smtp_settings,
        "deliver_message",
        lambda config, message: delivered.append((config, message)),
    )
    result = client.post(
        "/company-settings/smtp/test", json=payload(enabled=False, recipient="test@example.invalid")
    )
    assert result.status_code == 200
    config, message = delivered[0]
    assert config.password == "new-secret"
    assert message["To"] == "test@example.invalid"
    with factory() as db:
        assert db.get(EmailSettings, 1) is None


def test_authentication_error_reports_code_without_echoing_provider_text(context, monkeypatch):
    client, _, _, _ = context

    def fail(*args):
        raise smtplib.SMTPAuthenticationError(535, b"sensitive-provider-message")

    monkeypatch.setattr(smtp_settings, "deliver_message", fail)
    result = client.post(
        "/company-settings/smtp/test", json=payload(recipient="test@example.invalid")
    )
    assert result.status_code == 400
    assert "535" in result.text
    assert "sensitive-provider-message" not in result.text


def test_database_configuration_controls_actual_delivery_without_restart(context, monkeypatch):
    client, _, _, _ = context
    assert client.get("/company-settings/smtp").json()["source"] == "environment"
    delivered = []
    monkeypatch.setattr(
        security_alerts, "deliver_message", lambda config, message: delivered.append(config)
    )
    client.put("/company-settings/smtp", json=payload(enabled=False))
    security_alerts.send_email("Subject", "Body")
    assert not delivered
    with pytest.raises(RuntimeError):
        security_alerts.ensure_email_transport_configured()
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "false")
    get_settings.cache_clear()
    client.put("/company-settings/smtp", json=payload(enabled=True))
    security_alerts.ensure_email_transport_configured()
    security_alerts.send_email("Subject", "Body")
    assert delivered[0].username == "alerts@example.invalid"
    assert delivered[0].password == "new-secret"


def test_password_length_error_does_not_echo_secret(context):
    client, _, _, _ = context
    secret = "sensitive-value-" * 100
    result = client.put("/company-settings/smtp", json=payload(password=secret))
    assert result.status_code == 400
    assert "sensitive-value" not in result.text


@pytest.mark.parametrize(
    "changes",
    [
        {"sender": "a@example.invalid\r\nBcc: x@example.invalid"},
        {"port": 0},
        {"encryption": "none"},
        {"recipients": "invalid"},
    ],
)
def test_invalid_connection_fields_are_rejected(context, changes):
    client, _, _, _ = context
    assert client.put("/company-settings/smtp", json=payload(**changes)).status_code == 422

from __future__ import annotations

from app.core.config import get_settings
from app.services.security_alerts import _send_email


class _DummySmtp:
    def __init__(self, host: str, port: int, *, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False
        self.sent = False

    def __enter__(self) -> "_DummySmtp":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = True

    def send_message(self, message) -> None:
        self.sent = True


def _configure_smtp(monkeypatch, *, use_ssl: bool, use_tls: bool) -> None:
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_TO", "destinatario@example.invalid")
    monkeypatch.setenv("SECURITY_ALERT_EMAIL_FROM", "alerts@example.invalid")
    monkeypatch.setenv("SMTP_HOST", "mail.example.invalid")
    monkeypatch.setenv("SMTP_PORT", "465" if use_ssl else "587")
    monkeypatch.setenv("SMTP_USERNAME", "alerts@example.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_USE_SSL", "true" if use_ssl else "false")
    monkeypatch.setenv("SMTP_USE_TLS", "true" if use_tls else "false")
    get_settings.cache_clear()


def test_send_email_uses_ssl_client_when_requested(monkeypatch) -> None:
    _configure_smtp(monkeypatch, use_ssl=True, use_tls=False)
    instances: list[_DummySmtp] = []

    def _smtp_ssl(host: str, port: int, *, timeout: int) -> _DummySmtp:
        smtp = _DummySmtp(host, port, timeout=timeout)
        instances.append(smtp)
        return smtp

    monkeypatch.setattr("app.services.security_alerts.smtplib.SMTP_SSL", _smtp_ssl)
    monkeypatch.setattr("app.services.security_alerts.smtplib.SMTP", lambda *args, **kwargs: None)

    _send_email("Assunto", "Corpo")

    assert len(instances) == 1
    assert instances[0].port == 465
    assert instances[0].started_tls is False
    assert instances[0].logged_in is True
    assert instances[0].sent is True


def test_send_email_uses_starttls_when_configured(monkeypatch) -> None:
    _configure_smtp(monkeypatch, use_ssl=False, use_tls=True)
    instances: list[_DummySmtp] = []

    def _smtp(host: str, port: int, *, timeout: int) -> _DummySmtp:
        smtp = _DummySmtp(host, port, timeout=timeout)
        instances.append(smtp)
        return smtp

    monkeypatch.setattr("app.services.security_alerts.smtplib.SMTP", _smtp)
    monkeypatch.setattr("app.services.security_alerts.smtplib.SMTP_SSL", lambda *args, **kwargs: None)

    _send_email("Assunto", "Corpo")

    assert len(instances) == 1
    assert instances[0].port == 587
    assert instances[0].started_tls is True
    assert instances[0].logged_in is True
    assert instances[0].sent is True

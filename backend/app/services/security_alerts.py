from __future__ import annotations

import json
import smtplib
import socket
import threading
import time
from collections import deque
from email.message import EmailMessage
from ipaddress import ip_address
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.security import User
from app.services.audit import write_audit_log


class _EventTracker:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def record(self, key: str, *, window_seconds: int) -> int:
        now = time.time()
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            bucket.append(now)
            return len(bucket)


class _DedupTracker:
    def __init__(self) -> None:
        self._events: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            last_sent = self._events.get(key)
            if last_sent and (now - last_sent) < window_seconds:
                return False
            self._events[key] = now
            return True


failure_tracker = _EventTracker()
alert_deduper = _DedupTracker()


def get_client_ip(headers: dict[str, str] | Any, fallback: str | None = None) -> str:
    forwarded_for = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        if candidate:
            return candidate
    real_ip = headers.get("x-real-ip") or headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return fallback or "unknown"


def _is_public_ip(client_ip: str) -> bool:
    try:
        address = ip_address(client_ip)
    except ValueError:
        return False
    return not (address.is_private or address.is_loopback or address.is_reserved or address.is_multicast)


def _lookup_ip_country(client_ip: str) -> dict[str, str] | None:
    settings = get_settings()
    if not settings.ipinfo_token or not _is_public_ip(client_ip):
        return None
    request_url = f"https://api.ipinfo.io/lite/{quote(client_ip)}?token={quote(settings.ipinfo_token)}"
    try:
        with urlopen(request_url, timeout=3) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, socket.timeout, json.JSONDecodeError):
        return None
    country_code = str(payload.get("country_code") or "").upper()
    country_name = str(payload.get("country") or "").strip()
    if not country_code:
        return None
    return {
        "country_code": country_code,
        "country_name": country_name or country_code,
        "asn": str(payload.get("asn") or "").strip(),
        "as_name": str(payload.get("as_name") or "").strip(),
    }


def send_email(
    subject: str,
    body: str,
    *,
    recipients: list[str] | None = None,
    html_body: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.security_alert_email_enabled:
        return
    resolved_recipients = [
        item.strip()
        for item in (recipients or settings.security_alert_recipients)
        if item.strip()
    ]
    if not settings.smtp_host or not resolved_recipients:
        return
    sender = settings.security_alert_email_from or settings.smtp_username
    if not sender:
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(resolved_recipients)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    retryable_errors = (TimeoutError, socket.timeout, smtplib.SMTPException, OSError)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            _deliver_email(message)
            return
        except retryable_errors as error:
            last_error = error
            if attempt == 1:
                raise
    if last_error is not None:
        raise last_error


def ensure_email_transport_configured() -> None:
    settings = get_settings()
    if not settings.security_alert_email_enabled:
        raise RuntimeError("Envio de email desabilitado em SECURITY_ALERT_EMAIL_ENABLED.")
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST nao configurado para envio de email.")
    sender = settings.security_alert_email_from or settings.smtp_username
    if not sender:
        raise RuntimeError("SECURITY_ALERT_EMAIL_FROM ou SMTP_USERNAME deve ser configurado para envio de email.")


def _deliver_email(message: EmailMessage) -> None:
    settings = get_settings()
    smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def _send_email(subject: str, body: str) -> None:
    send_email(subject, body)


def _emit_alert(
    db: Session,
    *,
    action: str,
    subject: str,
    metadata: dict[str, Any],
    actor_user: User | None = None,
    company_id: str | None = None,
) -> None:
    write_audit_log(
        db,
        action=action,
        entity_name="security_alert",
        entity_id=str(uuid4()),
        company_id=company_id,
        actor_user=actor_user,
        after_state=metadata,
    )
    try:
        body = "\n".join(f"{key}: {value}" for key, value in metadata.items())
        _send_email(subject, body)
    except Exception:
        # Alert delivery cannot block the authentication flow.
        return


def record_auth_failure(
    db: Session,
    *,
    client_ip: str,
    email: str,
    user_agent: str | None,
    reason: str,
    path: str,
) -> bool:
    settings = get_settings()
    normalized_email = email.strip().lower()
    event_key = f"auth-failure:{client_ip}:{normalized_email}:{path}:{reason}"
    failure_count = failure_tracker.record(event_key, window_seconds=settings.security_alert_failure_window_seconds)
    if failure_count < settings.security_alert_failure_threshold:
        return False

    dedup_key = f"auth-failure-alert:{client_ip}:{normalized_email}:{path}:{reason}"
    if not alert_deduper.allow(dedup_key, window_seconds=settings.security_alert_dedup_window_seconds):
        return False

    geo = _lookup_ip_country(client_ip) or {}
    _emit_alert(
        db,
        action="security_attack_attempt",
        subject=f"[Seguranca] Tentativas suspeitas de autenticacao para {normalized_email}",
        metadata={
            "email": normalized_email,
            "client_ip": client_ip,
            "user_agent": user_agent or "",
            "reason": reason,
            "path": path,
            "failure_count": failure_count,
            "country_code": geo.get("country_code", ""),
            "country_name": geo.get("country_name", ""),
            "asn": geo.get("asn", ""),
            "as_name": geo.get("as_name", ""),
        },
    )
    return True


def record_rate_limit_attack(
    db: Session,
    *,
    client_ip: str,
    email: str | None,
    user_agent: str | None,
    path: str,
    rate_limit_key: str,
) -> bool:
    settings = get_settings()
    dedup_key = f"rate-limit-alert:{rate_limit_key}"
    if not alert_deduper.allow(dedup_key, window_seconds=settings.security_alert_dedup_window_seconds):
        return False

    geo = _lookup_ip_country(client_ip) or {}
    _emit_alert(
        db,
        action="security_rate_limit_blocked",
        subject="[Seguranca] Origem bloqueada por excesso de tentativas",
        metadata={
            "email": (email or "").strip().lower(),
            "client_ip": client_ip,
            "user_agent": user_agent or "",
            "path": path,
            "rate_limit_key": rate_limit_key,
            "country_code": geo.get("country_code", ""),
            "country_name": geo.get("country_name", ""),
            "asn": geo.get("asn", ""),
            "as_name": geo.get("as_name", ""),
        },
    )
    return True


def alert_on_foreign_access(
    db: Session,
    *,
    client_ip: str,
    user_agent: str | None,
    email: str,
    user: User | None,
    login_status: str,
) -> bool:
    settings = get_settings()
    geo = _lookup_ip_country(client_ip)
    if not geo:
        return False
    if geo["country_code"] in settings.allowed_country_codes:
        return False

    dedup_key = f"foreign-access:{client_ip}:{email.strip().lower()}:{login_status}:{geo['country_code']}"
    if not alert_deduper.allow(dedup_key, window_seconds=settings.security_alert_dedup_window_seconds):
        return False

    _emit_alert(
        db,
        action="security_foreign_access",
        subject=f"[Seguranca] Acesso fora do Brasil para {email.strip().lower()}",
        metadata={
            "email": email.strip().lower(),
            "client_ip": client_ip,
            "user_agent": user_agent or "",
            "login_status": login_status,
            "country_code": geo.get("country_code", ""),
            "country_name": geo.get("country_name", ""),
            "asn": geo.get("asn", ""),
            "as_name": geo.get("as_name", ""),
        },
        actor_user=user,
        company_id=user.company_id if user else None,
    )
    return True

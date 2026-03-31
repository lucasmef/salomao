from datetime import datetime, timezone

from app.core.security import (
    build_totp_uri,
    generate_mfa_secret,
    generate_totp_code,
    sign_state_token,
    verify_state_token,
    verify_totp_code,
)


def test_totp_roundtrip() -> None:
    secret = generate_mfa_secret()
    current_time = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)

    code = generate_totp_code(secret, current_time)

    assert len(code) == 6
    assert verify_totp_code(secret, code, for_time=current_time)


def test_totp_uri_contains_account_and_issuer() -> None:
    secret = generate_mfa_secret()

    uri = build_totp_uri(secret, "admin@gestor.local", "Gestor Financeiro")

    assert uri.startswith("otpauth://totp/")
    assert "admin@gestor.local" in uri
    assert "issuer=Gestor%20Financeiro" in uri


def test_signed_state_token_roundtrip() -> None:
    payload = {"sub": "user-1", "purpose": "mfa-login", "exp": "2026-03-25T12:00:00+00:00"}

    token = sign_state_token(payload, "test-secret")

    assert verify_state_token(token, "test-secret") == payload

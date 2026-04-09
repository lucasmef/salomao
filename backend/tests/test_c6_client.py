from __future__ import annotations

import base64

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.crypto import encrypt_text
from app.db.models.finance import Account
from app.services.c6 import C6AccountConfig, C6ApiClient, _load_c6_account_config


def _build_config() -> C6AccountConfig:
    return C6AccountConfig(
        account_id="account-1",
        client_id="client-id",
        client_secret="client-secret",
        certificate_pem="---CERT---",
        private_key_pem="---KEY---",
        environment="sandbox",
        api_base_url="https://example.test",
        partner_software_name="Gestor Financeiro",
        partner_software_version="0.1.0",
    )


def test_c6_client_reuses_token_and_sends_partner_headers() -> None:
    token_calls = 0
    consult_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, consult_calls
        if request.url.path == "/v1/auth/":
            token_calls += 1
            assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
            body = request.read().decode("utf-8")
            assert "client_id=client-id" in body
            assert "client_secret=client-secret" in body
            assert "grant_type=client_credentials" in body
            return httpx.Response(
                200,
                json={
                    "access_token": "token-123",
                    "token_type": "Bearer",
                    "expires_in": 600,
                    "scope": "bankslip.read",
                },
            )
        if request.url.path == "/v1/bank_slips/BSL-001":
            consult_calls += 1
            assert request.headers["authorization"] == "Bearer token-123"
            assert request.headers["partner-software-name"] == "Gestor Financeiro"
            assert request.headers["partner-software-version"] == "0.1.0"
            return httpx.Response(200, json={"id": "BSL-001", "status": "CREATED"})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    client = C6ApiClient(_build_config(), transport=httpx.MockTransport(handler))
    try:
        client.get_bank_slip("BSL-001")
        client.get_bank_slip("BSL-001")
    finally:
        client.close()

    assert token_calls == 1
    assert consult_calls == 2


def test_load_c6_account_config_decrypts_sensitive_values() -> None:
    account = Account(
        company_id="company-1",
        name="C6",
        account_type="checking",
        c6_api_enabled=True,
        c6_environment="production",
        c6_client_id="client-id",
        c6_partner_software_name="Gestor Financeiro",
        c6_partner_software_version="0.1.0",
        c6_client_secret_encrypted=encrypt_text("client-secret"),
        c6_certificate_pem_encrypted=encrypt_text("---CERT---"),
        c6_private_key_pem_encrypted=encrypt_text("---KEY---"),
    )

    config = _load_c6_account_config(account)

    assert config.client_id == "client-id"
    assert config.client_secret == "client-secret"
    assert config.certificate_pem == "---CERT---"
    assert config.private_key_pem == "---KEY---"
    assert config.partner_software_name == "Gestor Financeiro"


def test_c6_client_reports_invalid_pem_configuration() -> None:
    client = C6ApiClient(_build_config())
    try:
        with pytest.raises(ValueError, match="certificado PEM|chave privada PEM"):
            client.get_bank_slip("BSL-001")
    finally:
        client.close()


def test_c6_client_decodes_pdf_from_json_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/":
            return httpx.Response(
                200,
                json={
                    "access_token": "token-123",
                    "token_type": "Bearer",
                    "expires_in": 600,
                    "scope": "bankslip.read",
                },
            )
        if request.url.path == "/v1/bank_slips/BSL-001/pdf":
            return httpx.Response(
                200,
                json={"base64_pdf_file": base64.b64encode(b"%PDF-C6").decode("ascii")},
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    client = C6ApiClient(_build_config(), transport=httpx.MockTransport(handler))
    try:
        assert client.get_bank_slip_pdf("BSL-001") == b"%PDF-C6"
    finally:
        client.close()


def test_c6_client_refreshes_expired_token() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/v1/auth/":
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"token-{token_calls}", "expires_in": 1})
        if request.url.path == "/v1/bank_slips/BSL-001":
            return httpx.Response(200, json={"id": "BSL-001"})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    client = C6ApiClient(_build_config(), transport=httpx.MockTransport(handler))
    try:
        client.get_bank_slip("BSL-001")
        client._token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        client.get_bank_slip("BSL-001")
    finally:
        client.close()

    assert token_calls == 2


def test_c6_client_normalizes_partner_headers_to_ascii() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/":
            return httpx.Response(200, json={"access_token": "token-123", "expires_in": 600})
        if request.url.path == "/v1/bank_slips/BSL-001":
            assert request.headers["partner-software-name"] == "Salomao ERP"
            assert request.headers["partner-software-version"] == "v1.0"
            return httpx.Response(200, json={"id": "BSL-001"})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    config = _build_config()
    config.partner_software_name = "Salomão ERP"
    config.partner_software_version = "v1.0"
    client = C6ApiClient(config, transport=httpx.MockTransport(handler))
    try:
        client.get_bank_slip("BSL-001")
    finally:
        client.close()

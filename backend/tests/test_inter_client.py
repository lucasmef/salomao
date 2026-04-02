from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

from app.core.crypto import encrypt_text
from app.db.models.finance import Account
from app.services.inter import (
    InterAccountConfig,
    InterApiClient,
    _load_inter_account_config,
    _map_charge_status,
    _map_statement_to_transaction_payload,
)


def _build_config() -> InterAccountConfig:
    return InterAccountConfig(
        account_id="account-1",
        account_number="123456",
        api_key="client-id",
        client_secret="client-secret",
        certificate_pem="---CERT---",
        private_key_pem="---KEY---",
        environment="sandbox",
        api_base_url="https://example.test",
    )


def test_inter_client_reuses_token_and_sends_account_headers() -> None:
    token_calls = 0
    statement_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, statement_calls
        if request.url.path == "/oauth/v2/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/banking/v2/extrato/completo":
            statement_calls += 1
            assert request.headers["authorization"] == "Bearer token-123"
            assert request.headers["x-conta-corrente"] == "123456"
            assert request.headers["x-inter-conta-corrente"] == "123456"
            return httpx.Response(200, json={"transacoes": []})
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    client = InterApiClient(_build_config(), transport=httpx.MockTransport(handler))
    try:
        client.get_complete_statement(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31))
        client.get_complete_statement(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31))
    finally:
        client.close()

    assert token_calls == 1
    assert statement_calls == 2


def test_map_statement_payload_normalizes_amount_and_metadata() -> None:
    payload = _map_statement_to_transaction_payload(
        company_id="company-1",
        batch_id="batch-1",
        account_id="account-1",
        transaction={
            "idTransacao": "trx-001",
            "dataTransacao": "2026-03-15",
            "tipoTransacao": "PIX",
            "tipoOperacao": "DEBITO",
            "valor": "150.50",
            "titulo": "Pagamento",
            "descricao": "Fornecedor ABC",
            "numeroDocumento": "DOC-77",
        },
    )

    assert payload["fit_id"] == "INTER:trx-001"
    assert payload["amount"] == Decimal("-150.50")
    assert payload["trn_type"] == "DEBITO"
    assert payload["memo"] == "Pagamento | Fornecedor ABC"
    assert payload["check_number"] == "DOC-77"
    assert payload["bank_name"] == "Banco Inter"


def test_load_inter_account_config_decrypts_sensitive_values() -> None:
    account = Account(
        company_id="company-1",
        name="Inter",
        account_type="checking",
        inter_api_enabled=True,
        inter_environment="production",
        inter_api_key="client-id",
        inter_account_number="123456",
        inter_client_secret_encrypted=encrypt_text("client-secret"),
        inter_certificate_pem_encrypted=encrypt_text("---CERT---"),
        inter_private_key_pem_encrypted=encrypt_text("---KEY---"),
    )

    config = _load_inter_account_config(account)

    assert config.api_key == "client-id"
    assert config.client_secret == "client-secret"
    assert config.certificate_pem == "---CERT---"
    assert config.private_key_pem == "---KEY---"
    assert config.account_number == "123456"


def test_map_charge_status_preserves_dashboard_buckets() -> None:
    assert _map_charge_status("A_RECEBER") == "A receber"
    assert _map_charge_status("ATRASADO") == "A receber"
    assert _map_charge_status("RECEBIDO") == "Recebido por boleto"
    assert _map_charge_status("CANCELADO") == "Cancelado"

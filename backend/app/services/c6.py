from __future__ import annotations

import base64
import binascii
import os
import ssl
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.db.models.finance import Account
from app.db.models.security import Company

C6_PRODUCTION_API_ROOT = "https://baas-api.c6bank.info"
C6_SANDBOX_API_ROOT = "https://baas-api-sandbox.c6bank.info"
C6_AUTH_PATH = "/v1/auth"
C6_BANK_SLIPS_PATH = "/v1/bank_slips"
C6_DEFAULT_PARTNER_SOFTWARE_NAME = "Gestor Financeiro"
C6_DEFAULT_PARTNER_SOFTWARE_VERSION = "0.1.0"
C6_REQUEST_CONTENT_TYPE = "application/x-www-form-urlencoded"


@dataclass
class C6AccountConfig:
    account_id: str
    client_id: str
    client_secret: str
    certificate_pem: str
    private_key_pem: str
    environment: str
    api_base_url: str | None
    partner_software_name: str | None
    partner_software_version: str | None


@dataclass
class C6AuthToken:
    access_token: str
    token_type: str
    expires_in: int | None
    scope: str | None


def _normalize_optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _normalize_c6_api_root(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if not normalized:
        return None
    root = normalized.rstrip("/")
    for suffix in (C6_AUTH_PATH, C6_BANK_SLIPS_PATH):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    return root.rstrip("/") or None


def _extract_c6_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or None

    details: list[str] = []
    if isinstance(payload, dict):
        for key in ("message", "detail", "error_description", "error", "title"):
            value = _normalize_optional_text(str(payload.get(key) or ""))
            if value and value not in details:
                details.append(value)
        errors = payload.get("errors") or payload.get("violations")
        if isinstance(errors, list):
            for item in errors:
                if isinstance(item, dict):
                    text = _normalize_optional_text(
                        str(item.get("message") or item.get("detail") or item.get("title") or "")
                    )
                else:
                    text = _normalize_optional_text(str(item))
                if text and text not in details:
                    details.append(text)
    elif isinstance(payload, list):
        for item in payload:
            text = _normalize_optional_text(str(item))
            if text and text not in details:
                details.append(text)
    else:
        text = _normalize_optional_text(str(payload))
        if text:
            details.append(text)

    if not details:
        return None
    return " | ".join(details[:3])[:300]


def _raise_c6_request_error(error: Exception, *, stage: str) -> None:
    if isinstance(error, ssl.SSLError):
        raise ValueError(
            "Nao foi possivel carregar o certificado PEM ou a chave privada PEM do C6. "
            "Confira se ambos foram colados completos e no formato correto."
        ) from error
    if isinstance(error, httpx.TimeoutException):
        raise ValueError(
            f"A API do C6 demorou demais para responder durante {stage}. Tente novamente."
        ) from error
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        detail = _extract_c6_error_detail(response)
        if response.status_code in {401, 403}:
            message = (
                "C6 recusou a autenticacao da integracao. Confira client id, client secret, "
                "certificado, chave privada e permissoes da aplicacao."
            )
        elif response.status_code == 400:
            message = "C6 rejeitou a requisicao enviada pela integracao."
        elif response.status_code == 404:
            message = (
                "A integracao nao encontrou o endpoint do C6. Confira o ambiente "
                "(producao/sandbox) e a URL base configurada."
            )
        elif response.status_code >= 500:
            message = "C6 retornou um erro interno ao processar a integracao."
        else:
            message = f"Falha na integracao com o C6 (HTTP {response.status_code})."
        if detail:
            message = f"{message} Detalhe: {detail}"
        raise ValueError(message) from error
    if isinstance(error, httpx.RequestError):
        raise ValueError(
            f"Nao foi possivel conectar com a API do C6 durante {stage}. "
            "Confira a conexao, o ambiente configurado e os arquivos PEM."
        ) from error
    raise error


def _load_c6_account_config(account: Account) -> C6AccountConfig:
    if not account.c6_api_enabled:
        raise ValueError("API do C6 nao esta habilitada para esta conta")

    client_id = _normalize_optional_text(account.c6_client_id)
    client_secret = _normalize_optional_text(decrypt_text(account.c6_client_secret_encrypted))
    certificate_pem = _normalize_optional_text(decrypt_text(account.c6_certificate_pem_encrypted))
    private_key_pem = _normalize_optional_text(decrypt_text(account.c6_private_key_pem_encrypted))
    if not client_id:
        raise ValueError("Configure o client id da API do C6 nesta conta")
    if not client_secret:
        raise ValueError("Configure o client secret da API do C6 nesta conta")
    if not certificate_pem:
        raise ValueError("Cole o certificado PEM do C6 nesta conta")
    if not private_key_pem:
        raise ValueError("Cole a chave privada PEM do C6 nesta conta")

    return C6AccountConfig(
        account_id=account.id,
        client_id=client_id,
        client_secret=client_secret,
        certificate_pem=certificate_pem,
        private_key_pem=private_key_pem,
        environment=(account.c6_environment or "production").strip().lower(),
        api_base_url=_normalize_c6_api_root(account.c6_api_base_url),
        partner_software_name=_normalize_optional_text(account.c6_partner_software_name),
        partner_software_version=_normalize_optional_text(account.c6_partner_software_version),
    )


def _resolve_c6_account(
    db: Session,
    company: Company,
    account_id: str | None,
) -> tuple[Account, C6AccountConfig]:
    normalized_account_id = _normalize_optional_text(account_id)
    if normalized_account_id:
        account = db.get(Account, normalized_account_id)
        if not account or account.company_id != company.id:
            raise ValueError("Conta C6 nao encontrada")
        return account, _load_c6_account_config(account)

    account = db.scalar(
        select(Account)
        .where(
            Account.company_id == company.id,
            Account.c6_api_enabled.is_(True),
        )
        .order_by(Account.name.asc())
    )
    if not account:
        raise ValueError("Nenhuma conta com API do C6 habilitada foi encontrada")
    return account, _load_c6_account_config(account)


class C6ApiClient:
    def __init__(
        self,
        config: C6AccountConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self._token: C6AuthToken | None = None
        self._token_expires_at: datetime | None = None
        self._temp_paths: list[str] = []

    def _api_root(self) -> str:
        if self.config.api_base_url:
            return self.config.api_base_url.rstrip("/")
        if self.config.environment == "sandbox":
            return C6_SANDBOX_API_ROOT
        return C6_PRODUCTION_API_ROOT

    def _auth_base_url(self) -> str:
        return f"{self._api_root()}{C6_AUTH_PATH}"

    def _bank_slip_base_url(self) -> str:
        return f"{self._api_root()}{C6_BANK_SLIPS_PATH}"

    def _create_client(self, *, base_url: str) -> httpx.Client:
        if self.transport is not None:
            return httpx.Client(base_url=base_url, timeout=30.0, transport=self.transport)

        cert_file = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="utf-8")
        cert_file.write(self.config.certificate_pem)
        cert_file.close()
        self._temp_paths.append(cert_file.name)

        key_file = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="utf-8")
        key_file.write(self.config.private_key_pem)
        key_file.close()
        self._temp_paths.append(key_file.name)

        try:
            ssl_context = ssl.create_default_context()
            ssl_context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
            return httpx.Client(
                base_url=base_url,
                timeout=30.0,
                verify=ssl_context,
            )
        except ssl.SSLError as error:
            self.close()
            _raise_c6_request_error(error, stage="a configuracao do certificado")

    def close(self) -> None:
        for path in self._temp_paths:
            try:
                os.unlink(path)
            except FileNotFoundError:
                continue
        self._temp_paths.clear()

    def authenticate(self) -> C6AuthToken:
        now = datetime.now(UTC)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token
        try:
            with self._create_client(base_url=self._auth_base_url()) as client:
                response = client.post(
                    "/",
                    headers={"Content-Type": C6_REQUEST_CONTENT_TYPE},
                    data={
                        "client_id": self.config.client_id,
                        "client_secret": self.config.client_secret,
                        "grant_type": "client_credentials",
                    },
                )
            response.raise_for_status()
        except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as error:
            _raise_c6_request_error(error, stage="a autenticacao com o C6")

        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError("C6 retornou uma resposta invalida durante a autenticacao.") from error

        token = _normalize_optional_text(str(payload.get("access_token") or ""))
        if not token:
            raise ValueError("C6 nao retornou token de acesso")

        expires_in_raw = payload.get("expires_in")
        try:
            expires_in = int(expires_in_raw) if expires_in_raw is not None else None
        except (TypeError, ValueError):
            expires_in = None
        auth_token = C6AuthToken(
            access_token=token,
            token_type=_normalize_optional_text(str(payload.get("token_type") or "")) or "Bearer",
            expires_in=expires_in,
            scope=_normalize_optional_text(str(payload.get("scope") or "")),
        )
        self._token = auth_token
        self._token_expires_at = now + timedelta(seconds=max(1, expires_in - 30)) if expires_in else now + timedelta(minutes=9)
        return auth_token

    def _default_headers(self, access_token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": C6_REQUEST_CONTENT_TYPE,
        }
        partner_name = self.config.partner_software_name or C6_DEFAULT_PARTNER_SOFTWARE_NAME
        partner_version = self.config.partner_software_version or C6_DEFAULT_PARTNER_SOFTWARE_VERSION
        headers["partner-software-name"] = partner_name
        headers["partner-software-version"] = partner_version
        return headers

    def get_bank_slip(self, bank_slip_id: str) -> dict[str, Any]:
        auth_token = self.authenticate()
        try:
            with self._create_client(base_url=self._bank_slip_base_url()) as client:
                response = client.get(f"/{bank_slip_id}", headers=self._default_headers(auth_token.access_token))
            response.raise_for_status()
        except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as error:
            _raise_c6_request_error(error, stage="a consulta do boleto no C6")
        try:
            return response.json()
        except ValueError as error:
            raise ValueError("C6 retornou uma resposta invalida para a consulta do boleto.") from error

    def get_bank_slip_pdf(self, bank_slip_id: str) -> bytes:
        auth_token = self.authenticate()
        try:
            with self._create_client(base_url=self._bank_slip_base_url()) as client:
                response = client.get(f"/{bank_slip_id}/pdf", headers=self._default_headers(auth_token.access_token))
            response.raise_for_status()
        except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as error:
            _raise_c6_request_error(error, stage="o download do PDF do boleto no C6")

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError as error:
                raise ValueError("C6 retornou uma resposta invalida para o PDF do boleto.") from error
            encoded_pdf = _normalize_optional_text(
                str(payload.get("base64_pdf_file") or payload.get("pdf") or "")
            )
            if not encoded_pdf:
                raise ValueError("C6 nao retornou o PDF do boleto")
            try:
                return base64.b64decode(encoded_pdf, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("C6 retornou um PDF invalido para o boleto") from error

        if not response.content:
            raise ValueError("C6 nao retornou o PDF do boleto")
        return response.content


def test_c6_authentication(
    db: Session,
    company: Company,
    *,
    account_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[C6AccountConfig, C6AuthToken]:
    _account, config = _resolve_c6_account(db, company, account_id)
    client = C6ApiClient(config, transport=transport)
    try:
        return config, client.authenticate()
    finally:
        client.close()


def consult_c6_bank_slip(
    db: Session,
    company: Company,
    *,
    bank_slip_id: str,
    account_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[C6AccountConfig, dict[str, Any]]:
    _account, config = _resolve_c6_account(db, company, account_id)
    client = C6ApiClient(config, transport=transport)
    try:
        return config, client.get_bank_slip(bank_slip_id.strip())
    finally:
        client.close()


def download_c6_bank_slip_pdf(
    db: Session,
    company: Company,
    *,
    bank_slip_id: str,
    account_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[C6AccountConfig, bytes]:
    _account, config = _resolve_c6_account(db, company, account_id)
    client = C6ApiClient(config, transport=transport)
    try:
        return config, client.get_bank_slip_pdf(bank_slip_id.strip())
    finally:
        client.close()

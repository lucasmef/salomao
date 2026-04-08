from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import ssl
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.db.models.banking import BankTransaction
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord, StandaloneBoletoRecord
from app.db.models.finance import Account
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer
from app.db.models.security import Company
from app.schemas.imports import ImportResult
from app.services.boletos import (
    _build_export_charge_code,
    _digits_only,
    _resolve_export_due_date,
    _truncate_text,
    _validate_export_client_config,
    build_boleto_dashboard,
    normalize_text,
)

INTER_PRODUCTION_BASE_URL = "https://cdpj.partners.bancointer.com.br"
INTER_SANDBOX_BASE_URL = "https://cdpj-sandbox.partners.uatinter.co"
INTER_BANK_CODE = "077"
INTER_REQUIRED_SCOPES = "boleto-cobranca.read boleto-cobranca.write extrato.read"
INTER_STATEMENT_FIT_ID_MAX_LENGTH = 80
INTER_STATEMENT_REFERENCE_NUMBER_MAX_LENGTH = 50
INTER_STATEMENT_MATCH_STOPWORDS = {
    "A",
    "API",
    "BANCO",
    "BOLETO",
    "CARTAO",
    "CC",
    "CLIENTE",
    "CONTA",
    "CREDITO",
    "DEBITO",
    "DOC",
    "EFETUADO",
    "ENVIADO",
    "EXTRATO",
    "INTER",
    "PAGAMENTO",
    "PAGTO",
    "PIX",
    "RECEB",
    "RECEBIDO",
    "RECEBIMENTO",
    "TED",
    "TITULO",
    "TRANSACAO",
    "TRANSFERENCIA",
}
INTER_BATCH_SOURCE_TYPES = {
    "statement": "inter_statement",
    "charge_sync": "inter_charge_sync",
    "charge_issue": "inter_charge_issue",
    "charge_cancel": "inter_charge_cancel",
    "charge_receive": "inter_charge_receive",
    "standalone_charge_issue": "inter_standalone_charge_issue",
    "standalone_charge_sync": "inter_standalone_charge_sync",
}


@dataclass
class InterAccountConfig:
    account_id: str
    account_number: str
    api_key: str
    client_secret: str
    certificate_pem: str
    private_key_pem: str
    environment: str
    api_base_url: str | None


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, default=str)


def _normalize_optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _to_decimal(value: Any) -> Decimal:
    if value in {None, ""}:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _parse_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    normalized = text[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT", "%d/%m/%Y"):
        try:
            if fmt == "%Y-%m-%dT":
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _resolve_statement_amount(transaction: dict[str, Any]) -> Decimal:
    amount = _to_decimal(transaction.get("valor"))
    operation = str(transaction.get("tipoOperacao") or "").strip().upper()
    if amount > 0 and operation in {"DEBITO", "DEBIT", "D"}:
        return -amount
    if amount < 0 and operation in {"CREDITO", "CREDIT", "C"}:
        return abs(amount)
    return amount


def _build_statement_fit_id(transaction: dict[str, Any]) -> str:
    transaction_id = _normalize_optional_text(str(transaction.get("idTransacao") or ""))
    if transaction_id:
        fit_id = f"INTER:{transaction_id}"
        if len(fit_id) <= INTER_STATEMENT_FIT_ID_MAX_LENGTH:
            return fit_id
        return f"INTER:{hashlib.sha1(transaction_id.encode('utf-8')).hexdigest()}"
    payload = "|".join(
        [
            str(transaction.get("dataTransacao") or transaction.get("dataInclusao") or ""),
            str(transaction.get("tipoTransacao") or ""),
            str(transaction.get("tipoOperacao") or ""),
            str(transaction.get("valor") or ""),
            str(transaction.get("titulo") or ""),
            str(transaction.get("descricao") or ""),
        ]
    )
    return f"INTER:{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:32]}"


def _truncate_statement_reference_number(transaction: dict[str, Any]) -> str | None:
    transaction_id = _normalize_optional_text(str(transaction.get("idTransacao") or ""))
    if not transaction_id:
        return None
    return transaction_id[:INTER_STATEMENT_REFERENCE_NUMBER_MAX_LENGTH]


def _map_statement_to_transaction_payload(
    company_id: str,
    batch_id: str,
    account_id: str,
    transaction: dict[str, Any],
) -> dict[str, Any]:
    posted_at = _parse_date(str(transaction.get("dataTransacao") or transaction.get("dataInclusao") or ""))
    if posted_at is None:
        raise ValueError("Transacao do Inter sem data valida")
    title = _normalize_optional_text(str(transaction.get("titulo") or ""))
    description = _normalize_optional_text(str(transaction.get("descricao") or ""))
    memo_parts = [part for part in [title, description] if part]
    return {
        "company_id": company_id,
        "source_batch_id": batch_id,
        "account_id": account_id,
        "bank_name": "Banco Inter",
        "bank_code": INTER_BANK_CODE,
        "posted_at": posted_at,
        "trn_type": str(transaction.get("tipoOperacao") or transaction.get("tipoTransacao") or "OUTROS"),
        "amount": _resolve_statement_amount(transaction),
        "fit_id": _build_statement_fit_id(transaction),
        "check_number": _normalize_optional_text(str(transaction.get("numeroDocumento") or "")),
        "reference_number": _truncate_statement_reference_number(transaction),
        "memo": " | ".join(memo_parts) if memo_parts else None,
        "name": title,
        "raw_payload": _json_dumps(transaction),
    }


def _statement_match_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = normalize_text(value or "")
        for token in normalized.split():
            if token in INTER_STATEMENT_MATCH_STOPWORDS:
                continue
            if len(token) < 3 and not token.isdigit():
                continue
            tokens.add(token)
    return tokens


def _statement_texts_match(existing: BankTransaction, payload: dict[str, Any]) -> bool:
    existing_tokens = _statement_match_tokens(existing.name, existing.memo)
    payload_tokens = _statement_match_tokens(
        str(payload.get("name") or ""),
        str(payload.get("memo") or ""),
    )
    if not existing_tokens or not payload_tokens:
        return False
    common_tokens = existing_tokens & payload_tokens
    if existing_tokens.issubset(payload_tokens) or payload_tokens.issubset(existing_tokens):
        return True
    return len(common_tokens) >= 2


def _find_existing_ofx_statement_match(
    db: Session,
    *,
    account_id: str,
    payload: dict[str, Any],
) -> BankTransaction | None:
    candidates = list(
        db.scalars(
            select(BankTransaction)
            .join(ImportBatch, ImportBatch.id == BankTransaction.source_batch_id)
            .where(
                BankTransaction.account_id == account_id,
                BankTransaction.posted_at == payload["posted_at"],
                BankTransaction.amount == payload["amount"],
                BankTransaction.fit_id != payload["fit_id"],
                ImportBatch.source_type.like("ofx:%"),
            )
        )
    )
    matches = [candidate for candidate in candidates if _statement_texts_match(candidate, payload)]
    if len(matches) == 1:
        return matches[0]
    return None


def _adopt_inter_statement_identity(existing: BankTransaction, payload: dict[str, Any]) -> None:
    existing.fit_id = str(payload["fit_id"])
    if not existing.reference_number and payload.get("reference_number"):
        existing.reference_number = str(payload["reference_number"])
    if not existing.check_number and payload.get("check_number"):
        existing.check_number = str(payload["check_number"])
    if not existing.name and payload.get("name"):
        existing.name = str(payload["name"])
    if not existing.memo and payload.get("memo"):
        existing.memo = str(payload["memo"])


def _map_charge_status(status: str | None) -> str:
    normalized = (status or "").strip().upper()
    if normalized in {"RECEBIDO", "MARCADO_RECEBIDO"}:
        return "Recebido por boleto"
    if normalized in {"CANCELADO", "EXPIRADO", "FALHA_EMISSAO"}:
        return "Cancelado"
    if normalized in {"A_RECEBER", "ATRASADO", "EM_PROCESSAMENTO", "PROTESTO"}:
        return "A receber"
    return status or ""


def _sanitize_pdf_filename_fragment(value: str | None, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-._")
    return normalized or fallback


def _start_sync_batch(
    db: Session,
    company_id: str,
    *,
    source_type: str,
    filename: str,
) -> ImportBatch:
    batch = ImportBatch(
        company_id=company_id,
        source_type=source_type,
        filename=filename,
        status="processing",
    )
    db.add(batch)
    db.flush()
    return batch


def _resolve_batch_source_type(kind: str) -> str:
    source_type = INTER_BATCH_SOURCE_TYPES.get(kind)
    if not source_type:
        raise ValueError(f"Tipo de lote do Inter nao suportado: {kind}")
    return source_type


def _extract_inter_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or None

    details: list[str] = []
    if isinstance(payload, dict):
        for key in ("detail", "message", "title", "error_description", "error"):
            value = _normalize_optional_text(str(payload.get(key) or ""))
            if value and value not in details:
                details.append(value)
        violations = payload.get("violacoes") or payload.get("violations") or payload.get("errors")
        if isinstance(violations, list):
            for item in violations:
                if isinstance(item, dict):
                    text = _normalize_optional_text(
                        str(item.get("razao") or item.get("mensagem") or item.get("message") or "")
                    )
                    if text and text not in details:
                        details.append(text)
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


def _raise_inter_request_error(error: Exception, *, stage: str) -> None:
    if isinstance(error, ssl.SSLError):
        raise ValueError(
            "Nao foi possivel carregar o certificado PEM ou a chave privada PEM do Inter. "
            "Confira se ambos foram colados completos e no formato correto."
        ) from error
    if isinstance(error, httpx.TimeoutException):
        raise ValueError(
            f"A API do Banco Inter demorou demais para responder durante {stage}. Tente novamente."
        ) from error
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        detail = _extract_inter_error_detail(response)
        if response.status_code in {401, 403}:
            message = (
                "Banco Inter recusou a autenticacao da integracao. Confira client id, client secret, "
                "certificado, chave privada e permissoes da aplicacao."
            )
        elif response.status_code == 400:
            message = "Banco Inter rejeitou a requisicao enviada pela integracao."
        elif response.status_code == 404:
            message = (
                "A integracao nao encontrou o endpoint do Banco Inter. Confira o ambiente "
                "(producao/sandbox) e a URL base configurada."
            )
        elif response.status_code >= 500:
            message = "Banco Inter retornou um erro interno ao processar a integracao."
        else:
            message = f"Falha na integracao com o Banco Inter (HTTP {response.status_code})."
        if detail:
            message = f"{message} Detalhe: {detail}"
        raise ValueError(message) from error
    if isinstance(error, httpx.RequestError):
        raise ValueError(
            f"Nao foi possivel conectar com a API do Banco Inter durante {stage}. "
            "Confira a conexao, o ambiente configurado e os arquivos PEM."
        ) from error
    raise error


def _load_inter_account_config(account: Account) -> InterAccountConfig:
    if not account.inter_api_enabled:
        raise ValueError("API do Inter nao esta habilitada para esta conta")

    api_key = _normalize_optional_text(account.inter_api_key)
    account_number = _normalize_optional_text(account.inter_account_number or account.account_number)
    client_secret = _normalize_optional_text(decrypt_text(account.inter_client_secret_encrypted))
    certificate_pem = _normalize_optional_text(decrypt_text(account.inter_certificate_pem_encrypted))
    private_key_pem = _normalize_optional_text(decrypt_text(account.inter_private_key_pem_encrypted))

    if not api_key:
        raise ValueError("Configure a chave da API do Inter nesta conta")
    if not account_number:
        raise ValueError("Configure o numero da conta corrente do Inter")
    if not client_secret:
        raise ValueError("Configure o client secret do Inter nesta conta")
    if not certificate_pem:
        raise ValueError("Configure o certificado PEM do Inter nesta conta")
    if not private_key_pem:
        raise ValueError("Configure a chave privada PEM do Inter nesta conta")

    return InterAccountConfig(
        account_id=account.id,
        account_number=account_number,
        api_key=api_key,
        client_secret=client_secret,
        certificate_pem=certificate_pem,
        private_key_pem=private_key_pem,
        environment=(account.inter_environment or "production").strip().lower(),
        api_base_url=_normalize_optional_text(account.inter_api_base_url),
    )


def _get_inter_account(db: Session, company: Company, account_id: str) -> tuple[Account, InterAccountConfig]:
    account = db.get(Account, account_id)
    if not account or account.company_id != company.id:
        raise ValueError("Conta Inter nao encontrada")
    return account, _load_inter_account_config(account)


def _resolve_inter_account(
    db: Session,
    company: Company,
    account_id: str | None,
) -> tuple[Account, InterAccountConfig]:
    normalized_account_id = _normalize_optional_text(account_id)
    if normalized_account_id:
        return _get_inter_account(db, company, normalized_account_id)

    enabled_accounts = list(
        db.scalars(
            select(Account).where(
                Account.company_id == company.id,
                Account.is_active.is_(True),
                Account.inter_api_enabled.is_(True),
            )
        )
    )
    if not enabled_accounts:
        raise ValueError("Nenhuma conta com API do Inter habilitada foi encontrada.")
    if len(enabled_accounts) > 1:
        raise ValueError("Existe mais de uma conta com API do Inter habilitada. Mantenha apenas uma ativa.")
    account = enabled_accounts[0]
    return account, _load_inter_account_config(account)


class InterApiClient:
    def __init__(
        self,
        config: InterAccountConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self._token: str | None = None
        self._temp_paths: list[str] = []

    def _base_url(self) -> str:
        if self.config.api_base_url:
            return self.config.api_base_url.rstrip("/")
        if self.config.environment == "sandbox":
            return INTER_SANDBOX_BASE_URL
        return INTER_PRODUCTION_BASE_URL

    def _create_client(self) -> httpx.Client:
        base_url = self._base_url()
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
            return httpx.Client(
                base_url=base_url,
                timeout=30.0,
                cert=(cert_file.name, key_file.name),
            )
        except ssl.SSLError as error:
            self.close()
            _raise_inter_request_error(error, stage="a configuracao do certificado")

    def close(self) -> None:
        for path in self._temp_paths:
            try:
                os.unlink(path)
            except FileNotFoundError:
                continue
        self._temp_paths.clear()

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        try:
            with self._create_client() as client:
                response = client.post(
                    "/oauth/v2/token",
                    data={
                        "grant_type": "client_credentials",
                        "scope": INTER_REQUIRED_SCOPES,
                    },
                    auth=(self.config.api_key, self.config.client_secret),
                )
            response.raise_for_status()
        except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as error:
            _raise_inter_request_error(error, stage="a autenticacao com o Banco Inter")
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise ValueError("Banco Inter nao retornou token de acesso")
        self._token = token
        return token

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = self._ensure_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", f"Bearer {token}")
        headers.setdefault("x-conta-corrente", self.config.account_number)
        headers.setdefault("x-inter-conta-corrente", self.config.account_number)
        try:
            with self._create_client() as client:
                response = client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
        except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as error:
            _raise_inter_request_error(error, stage="a chamada da API do Banco Inter")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise ValueError("Banco Inter retornou uma resposta invalida para a integracao.") from error

    def get_complete_statement(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "dataInicio": start_date.isoformat(),
            "dataFim": end_date.isoformat(),
            "scrollEnabled": True,
        }
        payload = self.request("GET", "/banking/v2/extrato/completo", params=params)
        transactions = list(payload.get("transacoes") or [])
        scroll_id = payload.get("scrollId")
        while scroll_id:
            payload = self.request(
                "GET",
                "/banking/v2/extrato/completo",
                params={
                    **params,
                    "scrollId": scroll_id,
                },
            )
            transactions.extend(payload.get("transacoes") or [])
            scroll_id = payload.get("scrollId")
        return transactions

    def list_charges(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        payload = self.request(
            "GET",
            "/cobranca/v3/cobrancas",
            params={
                "dataInicial": start_date.isoformat(),
                "dataFinal": end_date.isoformat(),
                "filtrarDataPor": "EMISSAO",
            },
        )
        return list(payload.get("cobrancas") or [])

    def get_charge_detail(self, codigo_solicitacao: str) -> dict[str, Any]:
        payload = self.request("GET", f"/cobranca/v3/cobrancas/{codigo_solicitacao}")
        if "cobranca" in payload:
            return payload
        return {"cobranca": payload}

    def get_charge_pdf(self, codigo_solicitacao: str) -> bytes:
        payload = self.request("GET", f"/cobranca/v3/cobrancas/{codigo_solicitacao}/pdf")
        encoded_pdf = str(payload.get("pdf") or "").strip()
        if not encoded_pdf:
            raise ValueError("Banco Inter nao retornou o PDF da cobranca")
        try:
            return base64.b64decode(encoded_pdf, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Banco Inter retornou um PDF invalido para a cobranca") from error

    def create_charge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/cobranca/v3/cobrancas", json=payload)

    def cancel_charge(self, codigo_solicitacao: str, *, motivo_cancelamento: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/cobranca/v3/cobrancas/{codigo_solicitacao}/cancelar",
            json={"motivoCancelamento": motivo_cancelamento},
        )

    def pay_charge(self, codigo_solicitacao: str, *, pagar_com: str = "BOLETO") -> dict[str, Any]:
        return self.request(
            "POST",
            f"/cobranca/v3/cobrancas/{codigo_solicitacao}/pagar",
            json={"pagarCom": pagar_com},
        )


def _find_existing_boleto_record(
    db: Session,
    *,
    company_id: str,
    codigo_solicitacao: str | None,
    seu_numero: str | None,
) -> BoletoRecord | None:
    filters = []
    if codigo_solicitacao:
        filters.append(BoletoRecord.inter_codigo_solicitacao == codigo_solicitacao)
        filters.append(BoletoRecord.document_id == codigo_solicitacao)
    if seu_numero:
        filters.append(BoletoRecord.inter_seu_numero == seu_numero)
        filters.append(BoletoRecord.document_id == seu_numero)
    if not filters:
        return None
    return db.scalar(
        select(BoletoRecord).where(
            BoletoRecord.company_id == company_id,
            BoletoRecord.bank == "INTER",
            or_(*filters),
        )
    )


def _upsert_boleto_record(
    db: Session,
    *,
    company_id: str,
    batch_id: str,
    account_id: str,
    detail_payload: dict[str, Any],
) -> tuple[BoletoRecord, bool]:
    cobranca = detail_payload.get("cobranca") or {}
    boleto = detail_payload.get("boleto") or {}
    pix = detail_payload.get("pix") or {}
    pagador = cobranca.get("pagador") or {}

    codigo_solicitacao = _normalize_optional_text(str(cobranca.get("codigoSolicitacao") or ""))
    seu_numero = _normalize_optional_text(str(cobranca.get("seuNumero") or ""))
    client_name = _normalize_optional_text(str(pagador.get("nome") or "")) or "Cliente Inter"
    record = _find_existing_boleto_record(
        db,
        company_id=company_id,
        codigo_solicitacao=codigo_solicitacao,
        seu_numero=seu_numero,
    )
    created = record is None
    if record is None:
        record = BoletoRecord(
            company_id=company_id,
            source_batch_id=batch_id,
            bank="INTER",
            client_key=normalize_text(client_name),
            client_name=client_name,
            document_id=seu_numero or codigo_solicitacao or f"INTER-{datetime.now().timestamp()}",
        )
        db.add(record)

    record.source_batch_id = batch_id
    record.bank = "INTER"
    record.inter_account_id = account_id
    record.client_name = client_name
    record.client_key = normalize_text(client_name)
    record.document_id = seu_numero or codigo_solicitacao or record.document_id
    record.issue_date = _parse_date(str(cobranca.get("dataEmissao") or ""))
    record.due_date = _parse_date(str(cobranca.get("dataVencimento") or ""))
    record.amount = _to_decimal(cobranca.get("valorNominal"))
    record.paid_amount = _to_decimal(cobranca.get("valorTotalRecebido"))
    record.status = _map_charge_status(str(cobranca.get("situacao") or ""))
    record.barcode = _normalize_optional_text(str(boleto.get("codigoBarras") or ""))
    record.inter_codigo_solicitacao = codigo_solicitacao
    record.inter_seu_numero = seu_numero
    record.inter_nosso_numero = _normalize_optional_text(str(boleto.get("nossoNumero") or ""))
    record.linha_digitavel = _normalize_optional_text(str(boleto.get("linhaDigitavel") or ""))
    record.pix_copia_e_cola = _normalize_optional_text(str(pix.get("pixCopiaECola") or ""))
    record.inter_txid = _normalize_optional_text(str(pix.get("txid") or ""))
    db.flush()
    return record, created


def sync_inter_statement(
    db: Session,
    company: Company,
    *,
    account_id: str | None,
    start_date: date,
    end_date: date,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    account, config = _resolve_inter_account(db, company, account_id)
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("statement"),
        filename=f"inter-extrato-{start_date.isoformat()}-{end_date.isoformat()}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        transactions = client.get_complete_statement(start_date, end_date)
    finally:
        client.close()

    inserted = 0
    duplicates = 0
    linked = 0
    for transaction in transactions:
        payload = _map_statement_to_transaction_payload(company.id, batch.id, account.id, transaction)
        existing = db.scalar(
            select(BankTransaction).where(
                BankTransaction.account_id == account.id,
                BankTransaction.fit_id == payload["fit_id"],
            )
        )
        if existing:
            duplicates += 1
            continue
        ofx_match = _find_existing_ofx_statement_match(db, account_id=account.id, payload=payload)
        if ofx_match:
            _adopt_inter_statement_identity(ofx_match, payload)
            linked += 1
            continue
        db.add(BankTransaction(**payload))
        inserted += 1

    batch.records_total = len(transactions)
    batch.records_valid = inserted + linked
    batch.records_invalid = duplicates
    batch.status = "processed"
    if duplicates or linked:
        details = []
        if duplicates:
            details.append(f"{duplicates} lancamentos do Inter ja existiam para esta conta.")
        if linked:
            details.append(f"{linked} lancamentos do Inter foram vinculados a movimentos OFX existentes.")
        batch.error_summary = " ".join(details)
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Extrato do Inter sincronizado com sucesso.")


def sync_inter_charges(
    db: Session,
    company: Company,
    *,
    account_id: str | None,
    start_date: date,
    end_date: date,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    account, config = _resolve_inter_account(db, company, account_id)
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("charge_sync"),
        filename=f"inter-cobrancas-{start_date.isoformat()}-{end_date.isoformat()}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        summaries = client.list_charges(start_date, end_date)
        created_count = 0
        updated_count = 0
        for summary in summaries:
            codigo_solicitacao = _normalize_optional_text(str(summary.get("codigoSolicitacao") or ""))
            detail = client.get_charge_detail(codigo_solicitacao) if codigo_solicitacao else {"cobranca": summary}
            _, created = _upsert_boleto_record(
                db,
                company_id=company.id,
                batch_id=batch.id,
                account_id=account.id,
                detail_payload=detail,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
    finally:
        client.close()

    batch.records_total = len(summaries)
    batch.records_valid = created_count + updated_count
    batch.records_invalid = 0
    batch.status = "processed"
    if updated_count:
        batch.error_summary = f"{updated_count} cobranca(s) do Inter foram atualizadas."
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Cobrancas do Inter sincronizadas com sucesso.")


def _load_boleto_config_map(db: Session, company_id: str) -> dict[str, BoletoCustomerConfig]:
    return {
        item.client_key: item
        for item in db.scalars(
            select(BoletoCustomerConfig).where(BoletoCustomerConfig.company_id == company_id)
        )
    }


def _build_phone_payload(config: BoletoCustomerConfig) -> dict[str, str]:
    phone_digits = _digits_only(config.mobile or config.phone_primary or config.phone_secondary)
    if len(phone_digits) < 10:
        return {}
    return {
        "ddd": phone_digits[:2],
        "telefone": phone_digits[2:11],
    }


def _build_standalone_phone_payload(phone: str | None) -> dict[str, str]:
    phone_digits = _digits_only(phone)
    if len(phone_digits) < 10:
        return {}
    return {
        "ddd": phone_digits[:2],
        "telefone": phone_digits[2:11],
    }


def _build_standalone_charge_code(
    *,
    client_name: str,
    due_date: date,
    amount: Decimal,
    description: str,
) -> str:
    raw = "|".join(
        [
            normalize_text(client_name),
            due_date.isoformat(),
            format(amount.quantize(Decimal("0.01")), "f"),
            normalize_text(description),
            datetime.now(timezone.utc).isoformat(),
        ]
    )
    return f"AVL{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12].upper()}"


def _build_standalone_charge_payload(
    *,
    customer: LinxCustomer,
    amount: Decimal,
    due_date: date,
    note: str | None,
) -> dict[str, Any]:
    resolved_name = _truncate_text(customer.display_name or customer.legal_name, 100)
    normalized_tax_id = _digits_only(customer.document_number)
    if len(normalized_tax_id) not in {11, 14}:
        raise ValueError("O cliente selecionado nao possui CPF/CNPJ valido na base Linx.")
    if not _truncate_text(customer.address_street, 200):
        raise ValueError("O cliente selecionado nao possui endereco valido na base Linx.")
    if not _truncate_text(customer.address_number, 40):
        raise ValueError("O cliente selecionado nao possui numero valido na base Linx.")
    if not _truncate_text(customer.neighborhood, 120):
        raise ValueError("O cliente selecionado nao possui bairro valido na base Linx.")
    if not _truncate_text(customer.city, 120):
        raise ValueError("O cliente selecionado nao possui cidade valida na base Linx.")
    if len(_truncate_text(customer.state, 2).upper()) != 2:
        raise ValueError("O cliente selecionado nao possui UF valida na base Linx.")
    zip_code = _digits_only(customer.zip_code)
    if len(zip_code) != 8:
        raise ValueError("O cliente selecionado nao possui CEP valido na base Linx.")
    description = _truncate_text(note, 100) or "Boleto avulso"
    payload = {
        "seuNumero": _build_standalone_charge_code(
            client_name=resolved_name,
            due_date=due_date,
            amount=amount,
            description=description,
        ),
        "valorNominal": format(amount.quantize(Decimal("0.01")), "f"),
        "dataVencimento": due_date.isoformat(),
        "numDiasAgenda": 30,
        "formasRecebimento": ["BOLETO"],
        "pagador": {
            "tipoPessoa": "FISICA" if len(normalized_tax_id) == 11 else "JURIDICA",
            "nome": resolved_name,
            "cpfCnpj": normalized_tax_id,
            "endereco": _truncate_text(customer.address_street, 200),
            "numero": _truncate_text(customer.address_number, 40),
            "complemento": _truncate_text(customer.address_complement, 160) or None,
            "bairro": _truncate_text(customer.neighborhood, 120),
            "cidade": _truncate_text(customer.city, 120),
            "uf": _truncate_text(customer.state, 2).upper(),
            "cep": zip_code[:8],
            **_build_standalone_phone_payload(customer.mobile or customer.phone_primary),
        },
        "mensagem": {
            "linha1": _truncate_text(description, 100),
        },
    }
    if customer.email and customer.email.strip():
        payload["pagador"]["email"] = customer.email.strip()[:160]
    return payload


def _resolve_standalone_customer(db: Session, *, company_id: str, client_name: str) -> LinxCustomer:
    normalized_name = normalize_text(client_name)
    customers = list(
        db.scalars(
            select(LinxCustomer).where(
                LinxCustomer.company_id == company_id,
                LinxCustomer.registration_type.in_(("C", "A")),
                LinxCustomer.is_active.is_(True),
            )
        )
    )
    exact_match: LinxCustomer | None = None
    prefix_match: LinxCustomer | None = None
    for customer in customers:
        names = [
            normalize_text(customer.display_name or ""),
            normalize_text(customer.legal_name or ""),
        ]
        if normalized_name in names:
            exact_match = customer
            break
        if not prefix_match and any(name.startswith(normalized_name) or normalized_name.startswith(name) for name in names if name):
            prefix_match = customer
    resolved = exact_match or prefix_match
    if not resolved:
        raise ValueError("Cliente nao encontrado na base Linx API.")
    return resolved


def _build_inter_charge_payload(item: Any, config: BoletoCustomerConfig, *, today: date) -> dict[str, Any]:
    due_date = _resolve_export_due_date(item, config, today)
    tax_id = _digits_only(config.tax_id)
    payload = {
        "seuNumero": _build_export_charge_code(item, config.client_code, bool(config.include_interest)),
        "valorNominal": format(Decimal(item.amount).quantize(Decimal("0.01")), "f"),
        "dataVencimento": due_date.isoformat(),
        "numDiasAgenda": 30,
        "formasRecebimento": ["BOLETO"],
        "pagador": {
            "tipoPessoa": "FISICA" if len(tax_id) == 11 else "JURIDICA",
            "nome": _truncate_text(item.client_name, 100),
            "cpfCnpj": tax_id,
            "endereco": _truncate_text(config.address_street, 200),
            "numero": _truncate_text(config.address_number, 40),
            "complemento": _truncate_text(config.address_complement, 160) or None,
            "bairro": _truncate_text(config.neighborhood, 120),
            "cidade": _truncate_text(config.city, 120),
            "uf": _truncate_text(config.state, 2).upper(),
            "cep": _digits_only(config.zip_code)[:8],
            **_build_phone_payload(config),
        },
    }
    return payload


def _find_existing_standalone_boleto_record(
    db: Session,
    *,
    company_id: str,
    codigo_solicitacao: str | None,
    seu_numero: str | None,
) -> StandaloneBoletoRecord | None:
    filters = []
    if codigo_solicitacao:
        filters.append(StandaloneBoletoRecord.inter_codigo_solicitacao == codigo_solicitacao)
        filters.append(StandaloneBoletoRecord.document_id == codigo_solicitacao)
    if seu_numero:
        filters.append(StandaloneBoletoRecord.inter_seu_numero == seu_numero)
        filters.append(StandaloneBoletoRecord.document_id == seu_numero)
    if not filters:
        return None
    return db.scalar(
        select(StandaloneBoletoRecord).where(
            StandaloneBoletoRecord.company_id == company_id,
            StandaloneBoletoRecord.bank == "INTER",
            or_(*filters),
        )
    )


def _upsert_standalone_boleto_record(
    db: Session,
    *,
    company_id: str,
    batch_id: str,
    account_id: str,
    detail_payload: dict[str, Any],
    client_name: str | None = None,
    tax_id: str | None = None,
    email: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    local_status: str | None = None,
    issue_date_override: date | None = None,
) -> tuple[StandaloneBoletoRecord, bool]:
    cobranca = detail_payload.get("cobranca") or {}
    boleto = detail_payload.get("boleto") or {}
    pix = detail_payload.get("pix") or {}
    pagador = cobranca.get("pagador") or {}

    codigo_solicitacao = _normalize_optional_text(str(cobranca.get("codigoSolicitacao") or ""))
    seu_numero = _normalize_optional_text(str(cobranca.get("seuNumero") or ""))
    resolved_client_name = (
        client_name
        or _normalize_optional_text(str(pagador.get("nome") or ""))
        or "Cliente avulso"
    )
    record = _find_existing_standalone_boleto_record(
        db,
        company_id=company_id,
        codigo_solicitacao=codigo_solicitacao,
        seu_numero=seu_numero,
    )
    created = record is None
    if record is None:
        record = StandaloneBoletoRecord(
            company_id=company_id,
            source_batch_id=batch_id,
            bank="INTER",
            client_key=normalize_text(resolved_client_name),
            client_name=resolved_client_name,
            document_id=seu_numero or codigo_solicitacao or f"AVL-{datetime.now().timestamp()}",
            local_status=local_status or "open",
        )
        db.add(record)

    record.source_batch_id = batch_id
    record.bank = "INTER"
    record.inter_account_id = account_id
    record.client_name = resolved_client_name
    record.client_key = normalize_text(resolved_client_name)
    record.tax_id = _digits_only(tax_id or str(pagador.get("cpfCnpj") or "")) or record.tax_id
    record.email = (email or record.email or "").strip() or record.email
    record.document_id = seu_numero or codigo_solicitacao or record.document_id
    record.issue_date = issue_date_override or _parse_date(str(cobranca.get("dataEmissao") or "")) or record.issue_date
    record.due_date = _parse_date(str(cobranca.get("dataVencimento") or "")) or record.due_date
    record.amount = _to_decimal(cobranca.get("valorNominal") or record.amount)
    record.paid_amount = _to_decimal(cobranca.get("valorTotalRecebido"))
    record.status = _map_charge_status(str(cobranca.get("situacao") or "")) or record.status
    record.description = description if description is not None else record.description
    record.notes = notes if notes is not None else record.notes
    record.barcode = _normalize_optional_text(str(boleto.get("codigoBarras") or "")) or record.barcode
    record.inter_codigo_solicitacao = codigo_solicitacao or record.inter_codigo_solicitacao
    record.inter_seu_numero = seu_numero or record.inter_seu_numero
    record.inter_nosso_numero = _normalize_optional_text(str(boleto.get("nossoNumero") or "")) or record.inter_nosso_numero
    record.linha_digitavel = _normalize_optional_text(str(boleto.get("linhaDigitavel") or "")) or record.linha_digitavel
    record.pix_copia_e_cola = _normalize_optional_text(str(pix.get("pixCopiaECola") or "")) or record.pix_copia_e_cola
    record.inter_txid = _normalize_optional_text(str(pix.get("txid") or "")) or record.inter_txid
    if local_status is not None:
        record.local_status = local_status
        record.downloaded_at = datetime.now(timezone.utc) if local_status == "downloaded" else None
    db.flush()
    return record, created


def create_standalone_inter_charge(
    db: Session,
    company: Company,
    *,
    account_id: str | None,
    client_name: str,
    amount: Decimal,
    due_date: date,
    notes: str | None,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    account, config = _resolve_inter_account(db, company, account_id)
    resolved_customer = _resolve_standalone_customer(db, company_id=company.id, client_name=client_name.strip())
    normalized_amount = Decimal(amount).quantize(Decimal("0.01"))
    payload = _build_standalone_charge_payload(
        customer=resolved_customer,
        amount=normalized_amount,
        due_date=due_date,
        note=(notes or "").strip() or None,
    )
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("standalone_charge_issue"),
        filename=f"inter-boleto-avulso-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        created_payload = client.create_charge(payload)
        codigo_solicitacao = _normalize_optional_text(
            str(
                created_payload.get("codigoSolicitacao")
                or (created_payload.get("cobranca") or {}).get("codigoSolicitacao")
                or ""
            )
        )
        detail = client.get_charge_detail(codigo_solicitacao) if codigo_solicitacao else created_payload
        _upsert_standalone_boleto_record(
            db,
            company_id=company.id,
            batch_id=batch.id,
            account_id=account.id,
            detail_payload=detail,
            client_name=resolved_customer.display_name or resolved_customer.legal_name,
            tax_id=resolved_customer.document_number,
            email=resolved_customer.email,
            description=(notes or "").strip() or "Boleto avulso",
            notes=(notes or "").strip() or None,
            local_status="open",
            issue_date_override=date.today(),
        )
    finally:
        client.close()

    batch.records_total = 1
    batch.records_valid = 1
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Boleto avulso emitido no Inter com sucesso.")


def sync_standalone_inter_charges(
    db: Session,
    company: Company,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    open_records = list(
        db.scalars(
            select(StandaloneBoletoRecord).where(
                StandaloneBoletoRecord.company_id == company.id,
                StandaloneBoletoRecord.local_status == "open",
                StandaloneBoletoRecord.bank == "INTER",
                StandaloneBoletoRecord.inter_codigo_solicitacao.is_not(None),
            )
        )
    )
    if not open_records:
        batch = _start_sync_batch(
            db,
            company.id,
            source_type=_resolve_batch_source_type("standalone_charge_sync"),
            filename=f"inter-boleto-avulso-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        )
        batch.records_total = 0
        batch.records_valid = 0
        batch.records_invalid = 0
        batch.status = "processed"
        db.commit()
        db.refresh(batch)
        return ImportResult(batch=batch, message="Nenhum boleto avulso em aberto para sincronizar.")

    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("standalone_charge_sync"),
        filename=f"inter-boleto-avulso-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    updated_count = 0
    for record in open_records:
        account, config = _resolve_pdf_download_account(db, company, record)
        client = InterApiClient(config, transport=transport)
        try:
            detail = client.get_charge_detail(str(record.inter_codigo_solicitacao))
            _upsert_standalone_boleto_record(
                db,
                company_id=company.id,
                batch_id=batch.id,
                account_id=account.id,
                detail_payload=detail,
                client_name=record.client_name,
                tax_id=record.tax_id,
                email=record.email,
                description=record.description,
                notes=record.notes,
                local_status=record.local_status,
                issue_date_override=record.issue_date,
            )
            updated_count += 1
        finally:
            client.close()

    batch.records_total = len(open_records)
    batch.records_valid = updated_count
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Boletos avulsos sincronizados com sucesso.")


def issue_inter_charges(
    db: Session,
    company: Company,
    *,
    account_id: str | None,
    selection_keys: list[str],
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    normalized_selection_keys = [item.strip() for item in selection_keys if item and item.strip()]
    if not normalized_selection_keys:
        raise ValueError("Selecione ao menos um boleto faltando para emitir no Inter.")

    account, config = _resolve_inter_account(db, company, account_id)
    dashboard = build_boleto_dashboard(db, company, include_all_monthly_missing=True)
    selected_items = [
        item for item in dashboard.missing_boletos if item.selection_key in normalized_selection_keys
    ]
    if len(selected_items) != len(set(normalized_selection_keys)):
        raise ValueError("Alguns boletos selecionados nao estao mais disponiveis para emissao.")

    config_map = _load_boleto_config_map(db, company.id)
    validation_errors: list[str] = []
    prepared_payloads: list[tuple[Any, dict[str, Any]]] = []
    today = date.today()

    for item in selected_items:
        customer_config = config_map.get(item.client_key)
        missing_fields = _validate_export_client_config(customer_config, item.client_name)
        if missing_fields:
            validation_errors.append(f"{item.client_name}: {', '.join(missing_fields)}")
            continue
        assert customer_config is not None
        prepared_payloads.append((item, _build_inter_charge_payload(item, customer_config, today=today)))

    if validation_errors:
        raise ValueError(
            "Complete os dados obrigatorios dos clientes antes de emitir no Inter: "
            + "; ".join(sorted(validation_errors))
        )

    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("charge_issue"),
        filename=f"inter-emissao-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        for _item, payload in prepared_payloads:
            created_payload = client.create_charge(payload)
            codigo_solicitacao = _normalize_optional_text(
                str(
                    created_payload.get("codigoSolicitacao")
                    or (created_payload.get("cobranca") or {}).get("codigoSolicitacao")
                    or ""
                )
            )
            detail = (
                client.get_charge_detail(codigo_solicitacao)
                if codigo_solicitacao
                else created_payload
            )
            _upsert_boleto_record(
                db,
                company_id=company.id,
                batch_id=batch.id,
                account_id=account.id,
                detail_payload=detail,
            )
    finally:
        client.close()

    batch.records_total = len(prepared_payloads)
    batch.records_valid = len(prepared_payloads)
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Boletos emitidos no Inter com sucesso.")


def _resolve_pdf_download_account(db: Session, company: Company, boleto: Any) -> tuple[Account, InterAccountConfig]:
    if boleto.inter_account_id:
        return _get_inter_account(db, company, boleto.inter_account_id)

    fallback_accounts = list(
        db.scalars(
            select(Account).where(
                Account.company_id == company.id,
                Account.inter_api_enabled.is_(True),
            )
        )
    )
    if not fallback_accounts:
        raise ValueError("Nenhuma conta Inter habilitada foi encontrada para este boleto.")
    if len(fallback_accounts) > 1:
        raise ValueError("Este boleto nao informa a conta Inter de origem. Sincronize novamente para habilitar o PDF.")
    account = fallback_accounts[0]
    return account, _load_inter_account_config(account)


def _load_inter_boleto_for_pdf(db: Session, company: Company, boleto_id: str) -> BoletoRecord:
    boleto = db.scalar(
        select(BoletoRecord).where(
            BoletoRecord.id == boleto_id,
            BoletoRecord.company_id == company.id,
            BoletoRecord.bank == "INTER",
        )
    )
    if not boleto:
        raise ValueError("Boleto Inter nao encontrado.")
    if not boleto.inter_codigo_solicitacao:
        raise ValueError("Este boleto nao possui codigo de solicitacao do Inter para gerar o PDF.")
    return boleto


def _load_inter_boleto_for_action(db: Session, company: Company, boleto_id: str) -> BoletoRecord:
    boleto = db.scalar(
        select(BoletoRecord).where(
            BoletoRecord.id == boleto_id,
            BoletoRecord.company_id == company.id,
            BoletoRecord.bank == "INTER",
        )
    )
    if not boleto:
        raise ValueError("Boleto Inter nao encontrado.")
    if not boleto.inter_codigo_solicitacao:
        raise ValueError("Este boleto nao possui codigo de solicitacao do Inter.")
    return boleto


def _load_standalone_boleto_for_pdf(db: Session, company: Company, boleto_id: str) -> StandaloneBoletoRecord:
    boleto = db.scalar(
        select(StandaloneBoletoRecord).where(
            StandaloneBoletoRecord.id == boleto_id,
            StandaloneBoletoRecord.company_id == company.id,
            StandaloneBoletoRecord.bank == "INTER",
        )
    )
    if not boleto:
        raise ValueError("Boleto avulso nao encontrado.")
    if not boleto.inter_codigo_solicitacao:
        raise ValueError("Este boleto avulso nao possui codigo de solicitacao do Inter.")
    return boleto


def download_inter_charge_pdf(
    db: Session,
    company: Company,
    *,
    boleto_id: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bytes, str]:
    boleto = _load_inter_boleto_for_pdf(db, company, boleto_id)
    _account, config = _resolve_pdf_download_account(db, company, boleto)
    client = InterApiClient(config, transport=transport)
    try:
        pdf_bytes = client.get_charge_pdf(str(boleto.inter_codigo_solicitacao))
    finally:
        client.close()

    filename = _sanitize_pdf_filename_fragment(
        f"{boleto.client_name}-{boleto.document_id or boleto.inter_codigo_solicitacao}",
        fallback=f"boleto-inter-{boleto.id}",
    )
    return pdf_bytes, f"{filename}.pdf"


def download_inter_charge_pdfs_zip(
    db: Session,
    company: Company,
    *,
    boleto_ids: list[str],
    transport: httpx.BaseTransport | None = None,
) -> tuple[bytes, str]:
    normalized_ids = [item.strip() for item in boleto_ids if item and item.strip()]
    if not normalized_ids:
        raise ValueError("Selecione ao menos um boleto para baixar.")

    output = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for boleto_id in normalized_ids:
            pdf_bytes, filename = download_inter_charge_pdf(db, company, boleto_id=boleto_id, transport=transport)
            stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
            candidate = filename
            suffix = 2
            while candidate in used_names:
                candidate = f"{stem}-{suffix}.pdf"
                suffix += 1
            used_names.add(candidate)
            archive.writestr(candidate, pdf_bytes)

    generated_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output.getvalue(), f"boletos-inter-{generated_at}.zip"


def cancel_inter_charge(
    db: Session,
    company: Company,
    *,
    boleto_id: str,
    motivo_cancelamento: str,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    boleto = _load_inter_boleto_for_action(db, company, boleto_id)
    account, config = _resolve_pdf_download_account(db, company, boleto)
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("charge_cancel"),
        filename=f"inter-cancelamento-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        client.cancel_charge(str(boleto.inter_codigo_solicitacao), motivo_cancelamento=motivo_cancelamento.strip())
        detail = client.get_charge_detail(str(boleto.inter_codigo_solicitacao))
        _upsert_boleto_record(
            db,
            company_id=company.id,
            batch_id=batch.id,
            account_id=account.id,
            detail_payload=detail,
        )
    finally:
        client.close()

    batch.records_total = 1
    batch.records_valid = 1
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Boleto do Inter cancelado com sucesso.")


def receive_inter_charge(
    db: Session,
    company: Company,
    *,
    boleto_id: str,
    pagar_com: str = "BOLETO",
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    boleto = _load_inter_boleto_for_action(db, company, boleto_id)
    account, config = _resolve_pdf_download_account(db, company, boleto)
    if config.environment != "sandbox":
        raise ValueError("A baixa manual via API do Inter esta disponivel apenas no sandbox.")

    batch = _start_sync_batch(
        db,
        company.id,
        source_type=_resolve_batch_source_type("charge_receive"),
        filename=f"inter-baixa-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        client.pay_charge(str(boleto.inter_codigo_solicitacao), pagar_com=pagar_com.strip().upper() or "BOLETO")
        detail = client.get_charge_detail(str(boleto.inter_codigo_solicitacao))
        _upsert_boleto_record(
            db,
            company_id=company.id,
            batch_id=batch.id,
            account_id=account.id,
            detail_payload=detail,
        )
    finally:
        client.close()

    batch.records_total = 1
    batch.records_valid = 1
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Baixa do boleto do Inter concluida com sucesso.")


def download_standalone_inter_charge_pdf(
    db: Session,
    company: Company,
    *,
    boleto_id: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bytes, str]:
    boleto = _load_standalone_boleto_for_pdf(db, company, boleto_id)
    _account, config = _resolve_pdf_download_account(db, company, boleto)
    client = InterApiClient(config, transport=transport)
    try:
        pdf_bytes = client.get_charge_pdf(str(boleto.inter_codigo_solicitacao))
    finally:
        client.close()

    filename = _sanitize_pdf_filename_fragment(
        f"{boleto.client_name}-{boleto.document_id or boleto.inter_codigo_solicitacao}",
        fallback=f"boleto-avulso-inter-{boleto.id}",
    )
    return pdf_bytes, f"{filename}.pdf"


def mark_standalone_boleto_downloaded(
    db: Session,
    company: Company,
    *,
    boleto_id: str,
) -> None:
    boleto = db.scalar(
        select(StandaloneBoletoRecord).where(
            StandaloneBoletoRecord.id == boleto_id,
            StandaloneBoletoRecord.company_id == company.id,
        )
    )
    if not boleto:
        raise ValueError("Boleto avulso nao encontrado.")
    boleto.local_status = "downloaded"
    boleto.downloaded_at = datetime.now(timezone.utc)
    db.commit()

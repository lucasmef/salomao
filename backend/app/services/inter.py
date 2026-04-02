from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.db.models.banking import BankTransaction
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord
from app.db.models.finance import Account
from app.db.models.imports import ImportBatch
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
        return f"INTER:{transaction_id}"
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
        "reference_number": _normalize_optional_text(str(transaction.get("idTransacao") or "")),
        "memo": " | ".join(memo_parts) if memo_parts else None,
        "name": title,
        "raw_payload": _json_dumps(transaction),
    }


def _map_charge_status(status: str | None) -> str:
    normalized = (status or "").strip().upper()
    if normalized in {"RECEBIDO", "MARCADO_RECEBIDO"}:
        return "Recebido por boleto"
    if normalized in {"CANCELADO", "EXPIRADO", "FALHA_EMISSAO"}:
        return "Cancelado"
    if normalized in {"A_RECEBER", "ATRASADO", "EM_PROCESSAMENTO", "PROTESTO"}:
        return "A receber"
    return status or ""


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

        return httpx.Client(
            base_url=base_url,
            timeout=30.0,
            cert=(cert_file.name, key_file.name),
        )

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
        with self._create_client() as client:
            response = client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()

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

    def create_charge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/cobranca/v3/cobrancas", json=payload)


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
    account_id: str,
    start_date: date,
    end_date: date,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    _account, config = _get_inter_account(db, company, account_id)
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=f"inter_statement:{account_id}",
        filename=f"inter-extrato-{start_date.isoformat()}-{end_date.isoformat()}",
    )
    client = InterApiClient(config, transport=transport)
    try:
        transactions = client.get_complete_statement(start_date, end_date)
    finally:
        client.close()

    inserted = 0
    duplicates = 0
    for transaction in transactions:
        payload = _map_statement_to_transaction_payload(company.id, batch.id, account_id, transaction)
        existing = db.scalar(
            select(BankTransaction).where(
                BankTransaction.account_id == account_id,
                BankTransaction.fit_id == payload["fit_id"],
            )
        )
        if existing:
            duplicates += 1
            continue
        db.add(BankTransaction(**payload))
        inserted += 1

    batch.records_total = len(transactions)
    batch.records_valid = inserted
    batch.records_invalid = duplicates
    batch.status = "processed"
    if duplicates:
        batch.error_summary = f"{duplicates} lancamentos do Inter ja existiam para esta conta."
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Extrato do Inter sincronizado com sucesso.")


def sync_inter_charges(
    db: Session,
    company: Company,
    *,
    account_id: str,
    start_date: date,
    end_date: date,
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    _account, config = _get_inter_account(db, company, account_id)
    batch = _start_sync_batch(
        db,
        company.id,
        source_type=f"boletos:inter:sync:{account_id}",
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
            _, created = _upsert_boleto_record(db, company_id=company.id, batch_id=batch.id, detail_payload=detail)
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


def _build_inter_charge_payload(item: Any, config: BoletoCustomerConfig, *, today: date) -> dict[str, Any]:
    due_date = _resolve_export_due_date(item, config, today)
    tax_id = _digits_only(config.tax_id)
    payload = {
        "seuNumero": _build_export_charge_code(item, config.client_code, bool(config.include_interest)),
        "valorNominal": format(Decimal(item.amount).quantize(Decimal("0.01")), "f"),
        "dataVencimento": due_date.isoformat(),
        "numDiasAgenda": 30,
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


def issue_inter_charges(
    db: Session,
    company: Company,
    *,
    account_id: str,
    selection_keys: list[str],
    transport: httpx.BaseTransport | None = None,
) -> ImportResult:
    normalized_selection_keys = [item.strip() for item in selection_keys if item and item.strip()]
    if not normalized_selection_keys:
        raise ValueError("Selecione ao menos um boleto faltando para emitir no Inter.")

    _account, config = _get_inter_account(db, company, account_id)
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
        source_type=f"boletos:inter:issue:{account_id}",
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
            _upsert_boleto_record(db, company_id=company.id, batch_id=batch.id, detail_payload=detail)
    finally:
        client.close()

    batch.records_total = len(prepared_payloads)
    batch.records_valid = len(prepared_payloads)
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="Boletos emitidos no Inter com sucesso.")

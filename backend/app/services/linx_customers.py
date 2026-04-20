from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.boleto import BoletoCustomerConfig
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer
from app.db.models.security import Company
from app.schemas.imports import ImportResult
from app.schemas.linx_customers import (
    LinxCustomerDirectoryItemRead,
    LinxCustomerDirectoryRead,
    LinxCustomerDirectorySummaryRead,
)
from app.services.import_parsers import fingerprint_bytes
from app.services.linx import LinxApiSettings, load_linx_api_settings

LINX_CUSTOMERS_SOURCE = "linx_customers"
LINX_CUSTOMERS_METHOD = "LinxClientesFornec"
LINX_CUSTOMERS_FULL_LOAD_START = date(2000, 1, 1)
LINX_WS_USERNAME = "linx_export"
LINX_WS_PASSWORD = "linx_export"
LINX_API_TIMEOUT_SECONDS = 60.0

BOLETO_REQUIRED_FIELDS = (
    "legal_name",
    "document_number",
    "address_street",
    "address_number",
    "neighborhood",
    "city",
    "state",
    "zip_code",
)


@dataclass(frozen=True)
class LinxCustomersSyncPlan:
    mode: str
    parameters: dict[str, str]


def preferred_linx_customer_name(legal_name: str | None, display_name: str | None) -> str:
    primary = _clean_text(legal_name)
    if primary:
        return primary
    secondary = _clean_text(display_name)
    if secondary:
        return secondary
    return "Cadastro Linx sem nome"


def missing_linx_customer_boleto_fields(customer: LinxCustomer) -> list[str]:
    missing: list[str] = []
    for field_name in BOLETO_REQUIRED_FIELDS:
        value = getattr(customer, field_name, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
    return missing


def normalize_linx_customer_row(row: dict[str, str]) -> dict[str, object]:
    linx_code = _parse_int(row.get("cod_cliente"))
    if linx_code is None:
        raise ValueError("Linha Linx sem cod_cliente.")

    legal_name = preferred_linx_customer_name(
        row.get("razao_cliente"),
        row.get("nome_cliente"),
    )
    display_name = _clean_text(row.get("nome_cliente"))
    if display_name == legal_name:
        display_name = None

    return {
        "portal": _parse_int(row.get("portal")),
        "linx_code": linx_code,
        "legal_name": legal_name,
        "display_name": display_name,
        "document_number": _digits_only(row.get("doc_cliente")),
        "birth_date": _parse_birth_date(row),
        "person_type": _normalize_single_char(row.get("tipo_cliente")),
        "registration_type": _normalize_single_char(row.get("tipo_cadastro")),
        "is_active": _parse_bool(row.get("ativo"), default=True),
        "address_street": _clean_text(row.get("endereco_cliente")),
        "address_number": _clean_text(row.get("numero_rua_cliente")),
        "address_complement": _clean_text(row.get("complement_end_cli")),
        "neighborhood": _clean_text(row.get("bairro_cliente")),
        "city": _clean_text(row.get("cidade_cliente")),
        "state": _normalize_state(row.get("uf_cliente")),
        "zip_code": _digits_only(row.get("cep_cliente")),
        "country": _clean_text(row.get("pais")),
        "phone_primary": _clean_text(row.get("fone_cliente")),
        "mobile": _clean_text(row.get("cel_cliente")),
        "email": _clean_text(row.get("email_cliente")),
        "state_registration": _clean_text(row.get("inscricao_estadual")),
        "municipal_registration": _clean_text(row.get("incricao_municipal")),
        "loyalty_card_number": _clean_text(row.get("cartao_fidelidade")),
        "convenio_registration": _clean_text(row.get("matricula_conveniado")),
        "anonymous_customer": _parse_bool(row.get("cliente_anonimo"), default=False),
        "credit_limit_inhouse": _parse_decimal(row.get("limite_compras")),
        "credit_limit_cash_card": _parse_decimal(row.get("limite_credito_compra")),
        "class_name": _clean_text(row.get("classe_cliente")),
        "notes": _clean_text(row.get("obs")),
        "source_code_ws": _clean_text(row.get("codigo_ws")),
        "linx_created_at": _parse_datetime(row.get("data_cadastro")),
        "linx_updated_at": _parse_datetime(row.get("dt_update")),
        "linx_row_timestamp": _parse_int(row.get("timestamp")),
    }


def sync_linx_customers(
    db: Session,
    company: Company,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    full_refresh: bool = False,
) -> ImportResult:
    settings = load_linx_api_settings(company)
    plan = _build_sync_plan(
        db,
        company_id=company.id,
        start_date=start_date,
        end_date=end_date,
        full_refresh=full_refresh,
    )
    response_bytes, rows = _fetch_linx_rows(
        settings,
        method_name=LINX_CUSTOMERS_METHOD,
        parameters=plan.parameters,
    )

    request_descriptor = json.dumps(
        {
            "method": LINX_CUSTOMERS_METHOD,
            "mode": plan.mode,
            "parameters": plan.parameters,
        },
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    batch, reused = _create_batch(
        db,
        company.id,
        LINX_CUSTOMERS_SOURCE,
        _build_batch_filename(plan.mode),
        request_descriptor + b"\n" + response_bytes,
    )
    if reused:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de clientes/fornecedores Linx ja processada anteriormente.",
        )

    normalized_by_code: dict[int, dict[str, object]] = {}
    skipped_rows = 0
    duplicate_rows = 0

    for row in rows:
        try:
            normalized = normalize_linx_customer_row(row)
        except ValueError:
            skipped_rows += 1
            continue
        linx_code = int(normalized["linx_code"])
        previous = normalized_by_code.get(linx_code)
        if previous is not None:
            duplicate_rows += 1
            if _row_version_key(normalized) <= _row_version_key(previous):
                continue
        normalized_by_code[linx_code] = normalized

    existing_by_code = {}
    if normalized_by_code:
        existing_by_code = {
            customer.linx_code: customer
            for customer in db.scalars(
                select(LinxCustomer).where(
                    LinxCustomer.company_id == company.id,
                    LinxCustomer.linx_code.in_(list(normalized_by_code)),
                )
            )
        }

    inserted = 0
    updated = 0
    unchanged = 0

    for linx_code, payload in normalized_by_code.items():
        existing = existing_by_code.get(linx_code)
        if existing is None:
            customer = LinxCustomer(
                company_id=company.id,
                source_batch_id=batch.id,
                last_seen_batch_id=batch.id,
                **payload,
            )
            db.add(customer)
            inserted += 1
            continue

        changed = _apply_customer_payload(existing, payload)
        if changed:
            updated += 1
        else:
            unchanged += 1
        existing.last_seen_batch_id = batch.id

    batch.records_total = len(rows)
    batch.records_valid = len(normalized_by_code)
    batch.records_invalid = skipped_rows + duplicate_rows
    batch.status = "processed"
    batch.error_summary = _build_error_summary(
        skipped_rows=skipped_rows,
        duplicate_rows=duplicate_rows,
    )
    db.commit()
    db.refresh(batch)

    if not rows:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de clientes/fornecedores Linx concluida sem alteracoes.",
        )

    message = (
        "Clientes/fornecedores Linx sincronizados com sucesso. "
        f"{inserted} novo(s), {updated} atualizado(s) e {unchanged} sem alteracao."
    )
    return ImportResult(batch=batch, message=message)


def list_linx_customer_directory(
    db: Session,
    company: Company,
) -> LinxCustomerDirectoryRead:
    customers = list(
        db.scalars(
            select(LinxCustomer)
            .where(LinxCustomer.company_id == company.id)
            .order_by(LinxCustomer.legal_name.asc(), LinxCustomer.linx_code.asc())
        )
    )
    boleto_configs = list(
        db.scalars(
            select(BoletoCustomerConfig)
            .where(BoletoCustomerConfig.company_id == company.id)
            .order_by(BoletoCustomerConfig.client_name.asc())
        )
    )
    configs_by_code: dict[str, BoletoCustomerConfig] = {}
    configs_by_name: dict[str, BoletoCustomerConfig] = {}
    for config in boleto_configs:
        normalized_code = _normalize_boleto_lookup_code(config.client_code)
        if normalized_code:
            configs_by_code.setdefault(normalized_code, config)
        normalized_name = _normalize_boleto_lookup_text(config.client_name)
        if normalized_name:
            configs_by_name.setdefault(normalized_name, config)

    items: list[LinxCustomerDirectoryItemRead] = []
    active_count = 0
    client_count = 0
    supplier_count = 0
    transporter_count = 0
    boleto_enabled_count = 0

    for customer in customers:
        registration_type = (customer.registration_type or "").upper() or None
        supports_boleto = registration_type in {"C", "A"}
        if customer.is_active:
            active_count += 1
        if registration_type in {"C", "A"}:
            client_count += 1
        if registration_type in {"F", "A"}:
            supplier_count += 1
        if registration_type == "T":
            transporter_count += 1

        config = _match_boleto_config(
            customer,
            configs_by_code=configs_by_code,
            configs_by_name=configs_by_name,
        )
        if supports_boleto and config and config.uses_boleto:
            boleto_enabled_count += 1

        items.append(
            LinxCustomerDirectoryItemRead(
                id=customer.id,
                linx_code=customer.linx_code,
                legal_name=customer.legal_name,
                display_name=customer.display_name,
                document_number=customer.document_number,
                birth_date=customer.birth_date,
                registration_type=registration_type,
                registration_type_label=_registration_type_label(registration_type),
                person_type=customer.person_type,
                person_type_label=_person_type_label(customer.person_type),
                is_active=customer.is_active,
                city=customer.city,
                state=customer.state,
                email=customer.email,
                phone_primary=customer.phone_primary,
                mobile=customer.mobile,
                uses_boleto=bool(config.uses_boleto) if config else False,
                mode=(config.mode or "individual") if config else "individual",
                boleto_due_day=config.boleto_due_day if config else None,
                include_interest=bool(config.include_interest) if config else False,
                notes=config.notes if config else None,
                supports_boleto_config=supports_boleto,
                has_boleto_config=config is not None,
                missing_boleto_fields=missing_linx_customer_boleto_fields(customer),
                linx_updated_at=customer.linx_updated_at,
            )
        )

    return LinxCustomerDirectoryRead(
        generated_at=datetime.now(timezone.utc),
        summary=LinxCustomerDirectorySummaryRead(
            total_count=len(items),
            client_count=client_count,
            supplier_count=supplier_count,
            transporter_count=transporter_count,
            active_count=active_count,
            boleto_enabled_count=boleto_enabled_count,
        ),
        items=items,
    )


def _build_sync_plan(
    db: Session,
    *,
    company_id: str,
    start_date: date | None,
    end_date: date | None,
    full_refresh: bool,
) -> LinxCustomersSyncPlan:
    today = date.today()
    period_end = end_date or start_date or today
    parameters = {
        "data_inicial": LINX_CUSTOMERS_FULL_LOAD_START.isoformat(),
        "data_fim": period_end.isoformat(),
    }

    if start_date or end_date:
        dt_start = start_date or period_end
        dt_end = end_date or period_end
        parameters["dt_update_inicial"] = dt_start.isoformat()
        parameters["dt_update_fim"] = dt_end.isoformat()

    if full_refresh or start_date or end_date:
        parameters["timestamp"] = "0"
        return LinxCustomersSyncPlan(mode="window" if (start_date or end_date) else "full", parameters=parameters)

    latest_timestamp = db.scalar(
        select(func.max(LinxCustomer.linx_row_timestamp)).where(LinxCustomer.company_id == company_id)
    )
    parameters["timestamp"] = str(int(latest_timestamp or 0))
    return LinxCustomersSyncPlan(mode="incremental", parameters=parameters)


def _fetch_linx_rows(
    settings: LinxApiSettings,
    *,
    method_name: str,
    parameters: dict[str, str],
) -> tuple[bytes, list[dict[str, str]]]:
    payload = _build_request_xml(settings, method_name=method_name, parameters=parameters)
    with httpx.Client(timeout=LINX_API_TIMEOUT_SECONDS) as client:
        try:
            response = client.post(
                settings.base_url,
                content=payload,
                headers={"Content-Type": "application/xml; charset=utf-8"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ValueError("Falha ao consultar o webservice Linx de clientes/fornecedores.") from error
    response_bytes = response.content
    return response_bytes, _parse_linx_rows(response_bytes)


def _build_request_xml(
    settings: LinxApiSettings,
    *,
    method_name: str,
    parameters: dict[str, str],
) -> bytes:
    root = ET.Element("LinxMicrovix")
    ET.SubElement(
        root,
        "Authentication",
        {"user": LINX_WS_USERNAME, "password": LINX_WS_PASSWORD},
    )
    response_format = ET.SubElement(root, "ResponseFormat")
    response_format.text = "xml"
    command = ET.SubElement(root, "Command")
    name = ET.SubElement(command, "Name")
    name.text = method_name
    parameter_root = ET.SubElement(command, "Parameters")

    ordered_parameters = {
        "chave": settings.api_key,
        "cnpjEmp": settings.cnpj,
        **parameters,
    }
    for parameter_name, parameter_value in ordered_parameters.items():
        node = ET.SubElement(parameter_root, "Parameter", {"id": parameter_name})
        node.text = str(parameter_value)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _parse_linx_rows(response_bytes: bytes) -> list[dict[str, str]]:
    xml_text = response_bytes.decode("utf-8-sig")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError("Resposta XML invalida do webservice Linx.") from error

    success = (root.findtext("./ResponseResult/ResponseSuccess") or "").strip().lower()
    if success != "true":
        error_message = (
            root.findtext("./ResponseResult/ResponseError/Message")
            or root.findtext("./ResponseResult/Message")
            or "A API Linx retornou uma falha sem mensagem."
        )
        raise ValueError(error_message.strip())

    header = [(_clean_text(node.text) or "") for node in root.findall("./ResponseData/C/D")]
    if not header:
        return []

    rows: list[dict[str, str]] = []
    for row_node in root.findall("./ResponseData/R"):
        values = [node.text or "" for node in row_node.findall("./D")]
        if len(values) < len(header):
            values.extend([""] * (len(header) - len(values)))
        elif len(values) > len(header):
            values = values[: len(header)]
        rows.append(dict(zip(header, values, strict=False)))
    return rows


def _find_existing_batch(
    db: Session,
    company_id: str,
    source_type: str,
    fingerprint: str,
) -> ImportBatch | None:
    return db.scalar(
        select(ImportBatch).where(
            ImportBatch.company_id == company_id,
            ImportBatch.source_type == source_type,
            ImportBatch.fingerprint == fingerprint,
            ImportBatch.status == "processed",
        )
    )


def _create_batch(
    db: Session,
    company_id: str,
    source_type: str,
    filename: str,
    content: bytes,
) -> tuple[ImportBatch, bool]:
    fingerprint = fingerprint_bytes(content)
    existing = _find_existing_batch(db, company_id, source_type, fingerprint)
    if existing is not None:
        return existing, True

    batch = ImportBatch(
        company_id=company_id,
        source_type=source_type,
        filename=filename,
        fingerprint=fingerprint,
        status="processing",
    )
    db.add(batch)
    db.flush()
    return batch, False


def _apply_customer_payload(
    customer: LinxCustomer,
    payload: dict[str, object],
) -> bool:
    changed = False
    for field_name, value in payload.items():
        if getattr(customer, field_name) != value:
            setattr(customer, field_name, value)
            changed = True
    return changed


def _build_batch_filename(mode: str) -> str:
    return f"linx-customers-{mode}.xml"


def _build_error_summary(*, skipped_rows: int, duplicate_rows: int) -> str | None:
    parts: list[str] = []
    if skipped_rows:
        parts.append(f"{skipped_rows} linha(s) foram ignoradas por falta de codigo.")
    if duplicate_rows:
        parts.append(f"{duplicate_rows} linha(s) duplicadas foram consolidadas pelo maior timestamp.")
    return " ".join(parts) or None


def _row_version_key(payload: dict[str, object]) -> tuple[int, str]:
    timestamp = int(payload.get("linx_row_timestamp") or 0)
    updated_at = payload.get("linx_updated_at")
    updated_key = updated_at.isoformat() if isinstance(updated_at, datetime) else ""
    return (timestamp, updated_key)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.replace("\xa0", " ").split())
    return cleaned or None


def _digits_only(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    digits = "".join(char for char in cleaned if char.isdigit())
    return digits or None


def _normalize_single_char(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return cleaned[:1].upper()


def _normalize_state(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return cleaned.upper()


def _row_value(row: dict[str, str], *candidate_keys: str) -> str | None:
    lowered = {
        str(key).strip().lower(): value
        for key, value in row.items()
    }
    for key in candidate_keys:
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _parse_bool(value: str | None, *, default: bool) -> bool:
    cleaned = (_clean_text(value) or "").strip().lower()
    if not cleaned:
        return default
    if cleaned in {"1", "s", "sim", "true", "t", "y", "yes"}:
        return True
    if cleaned in {"0", "n", "nao", "false", "f", "no"}:
        return False
    return default


def _parse_int(value: str | None) -> int | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_decimal(value: str | None) -> Decimal | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    normalized = cleaned.replace(".", "").replace(",", ".")
    if "." in cleaned and "," not in cleaned:
        normalized = cleaned
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _parse_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    candidates = [cleaned, cleaned.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass

    for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _parse_birth_date(row: dict[str, str]) -> date | None:
    return _parse_date(
        _row_value(
            row,
            "data_nascimento",
            "dt_nascimento",
            "data_nascimento_cliente",
            "dt_nascimento_cliente",
            "data_nasc",
            "dt_nasc",
            "nascimento",
        )
    )


def _parse_datetime(value: str | None) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _normalize_boleto_lookup_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.upper()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _normalize_boleto_lookup_code(value: str | int | None) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D+", "", raw)
    if digits:
        return digits.lstrip("0") or "0"
    return _normalize_boleto_lookup_text(raw)


def _match_boleto_config(
    customer: LinxCustomer,
    *,
    configs_by_code: dict[str, BoletoCustomerConfig],
    configs_by_name: dict[str, BoletoCustomerConfig],
) -> BoletoCustomerConfig | None:
    code_match = configs_by_code.get(_normalize_boleto_lookup_code(customer.linx_code))
    if code_match is not None:
        return code_match

    legal_name_match = configs_by_name.get(_normalize_boleto_lookup_text(customer.legal_name))
    if legal_name_match is not None:
        return legal_name_match

    display_name_match = configs_by_name.get(_normalize_boleto_lookup_text(customer.display_name))
    if display_name_match is not None:
        return display_name_match

    return None


def _registration_type_label(value: str | None) -> str:
    labels = {
        "C": "Cliente",
        "F": "Fornecedor",
        "A": "Cliente e fornecedor",
        "T": "Transportador",
    }
    return labels.get((value or "").upper(), "Nao informado")


def _person_type_label(value: str | None) -> str:
    labels = {
        "F": "Fisica",
        "J": "Juridica",
    }
    return labels.get((value or "").upper(), "Nao informado")

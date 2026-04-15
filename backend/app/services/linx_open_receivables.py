from __future__ import annotations

import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxOpenReceivable
from app.db.models.security import Company
from app.schemas.imports import ImportResult
from app.schemas.linx_open_receivables import (
    LinxOpenReceivableDirectoryRead,
    LinxOpenReceivableDirectorySummaryRead,
    LinxOpenReceivableListItemRead,
)
from app.services.linx import LinxApiSettings, load_linx_api_settings

LINX_OPEN_RECEIVABLES_SOURCE = "linx_open_receivables"
LINX_FATURAS_METHOD = "LinxFaturas"
LINX_WS_USERNAME = "linx_export"
LINX_WS_PASSWORD = "linx_export"
LINX_API_TIMEOUT_SECONDS = 90.0
LINX_FULL_LOAD_START = "2024-01-01 00:00:00"
LINX_PAGE_LIMIT = 5000


@dataclass(frozen=True)
class LinxOpenReceivablesSyncPlan:
    mode: str
    timestamp: int


def sync_linx_open_receivables(
    db: Session,
    company: Company,
    *,
    full_refresh: bool = False,
) -> ImportResult:
    settings = load_linx_api_settings(company)
    plan = _build_sync_plan(db, company_id=company.id, full_refresh=full_refresh)

    hasher = hashlib.sha256()
    hasher.update(
        json.dumps(
            {
                "source": LINX_OPEN_RECEIVABLES_SOURCE,
                "mode": plan.mode,
                "timestamp": plan.timestamp,
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    )

    rows = _collect_rows(settings, start_timestamp=plan.timestamp, hasher=hasher)
    normalized_by_code, duplicate_rows = _normalize_rows(rows)
    existing_by_code = _load_existing_rows(db, company_id=company.id, codes=set(normalized_by_code))

    fingerprint = hasher.hexdigest()
    existing_batch = _find_existing_batch(db, company.id, LINX_OPEN_RECEIVABLES_SOURCE, fingerprint)
    if existing_batch is not None:
        return ImportResult(
            batch=existing_batch,
            message="Sincronizacao de faturas a receber Linx ja processada anteriormente.",
        )

    batch = ImportBatch(
        company_id=company.id,
        source_type=LINX_OPEN_RECEIVABLES_SOURCE,
        filename=f"linx-open-receivables-{plan.mode}.xml",
        fingerprint=fingerprint,
        status="processing",
    )
    db.add(batch)
    db.flush()

    inserted = 0
    updated = 0
    removed = 0
    ignored = 0

    for linx_code, normalized in normalized_by_code.items():
        existing = existing_by_code.get(linx_code)
        if not normalized["qualifies"]:
            if existing is not None:
                db.delete(existing)
                removed += 1
            else:
                ignored += 1
            continue

        payload = dict(normalized["payload"])
        if existing is None:
            receivable = LinxOpenReceivable(
                company_id=company.id,
                source_batch_id=batch.id,
                last_seen_batch_id=batch.id,
                **payload,
            )
            db.add(receivable)
            inserted += 1
            continue

        changed = False
        for field_name, value in payload.items():
            if getattr(existing, field_name) != value:
                setattr(existing, field_name, value)
                changed = True
        existing.last_seen_batch_id = batch.id
        if changed:
            updated += 1

    batch.records_total = len(rows)
    batch.records_valid = inserted + updated + removed
    batch.records_invalid = duplicate_rows + ignored
    batch.status = "processed"
    batch.error_summary = _build_error_summary(duplicate_rows=duplicate_rows, ignored=ignored, removed=removed)
    db.commit()
    db.refresh(batch)

    if not rows:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de faturas a receber Linx concluida sem alteracoes.",
        )

    message = (
        "Faturas a receber Linx sincronizadas com sucesso. "
        f"{inserted} nova(s), {updated} atualizada(s) e {removed} removida(s) da base aberta."
    )
    return ImportResult(batch=batch, message=message)


def list_linx_open_receivables(
    db: Session,
    company: Company,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
) -> LinxOpenReceivableDirectoryRead:
    page = max(page, 1)
    page_size = min(max(page_size, 10), 200)

    filters = [LinxOpenReceivable.company_id == company.id]
    normalized_search = _clean_text(search)
    if normalized_search:
        pattern = f"%{normalized_search}%"
        filters.append(
            or_(
                cast(LinxOpenReceivable.linx_code, String).ilike(pattern),
                cast(LinxOpenReceivable.customer_code, String).ilike(pattern),
                LinxOpenReceivable.customer_name.ilike(pattern),
                LinxOpenReceivable.document_number.ilike(pattern),
                LinxOpenReceivable.identifier.ilike(pattern),
            )
        )

    total = int(
        db.scalar(select(func.count()).select_from(LinxOpenReceivable).where(*filters))
        or 0
    )

    items = list(
        db.scalars(
            select(LinxOpenReceivable)
            .where(*filters)
            .order_by(LinxOpenReceivable.due_date.asc(), LinxOpenReceivable.customer_name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)
    summary_row = db.execute(
        select(
            func.count(LinxOpenReceivable.id),
            func.sum(case((LinxOpenReceivable.due_date < today_start, 1), else_=0)),
            func.sum(
                case(
                    (
                        (LinxOpenReceivable.due_date >= today_start)
                        & (LinxOpenReceivable.due_date < tomorrow_start),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.coalesce(func.sum(LinxOpenReceivable.amount), 0),
        ).where(LinxOpenReceivable.company_id == company.id)
    ).one()

    return LinxOpenReceivableDirectoryRead(
        generated_at=datetime.now(timezone.utc),
        summary=LinxOpenReceivableDirectorySummaryRead(
            total_count=int(summary_row[0] or 0),
            overdue_count=int(summary_row[1] or 0),
            due_today_count=int(summary_row[2] or 0),
            total_amount=Decimal(summary_row[3] or 0),
        ),
        items=[
            LinxOpenReceivableListItemRead(
                id=item.id,
                linx_code=int(item.linx_code),
                customer_code=item.customer_code,
                customer_name=item.customer_name,
                issue_date=item.issue_date,
                due_date=item.due_date,
                amount=item.amount,
                paid_amount=item.paid_amount,
                document_number=item.document_number,
                document_series=item.document_series,
                installment_number=item.installment_number,
                installment_count=item.installment_count,
                identifier=item.identifier,
                payment_method_name=item.payment_method_name,
                payment_plan_code=item.payment_plan_code,
                linx_row_timestamp=item.linx_row_timestamp,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _build_sync_plan(db: Session, *, company_id: str, full_refresh: bool) -> LinxOpenReceivablesSyncPlan:
    has_any_row = bool(
        db.scalar(select(LinxOpenReceivable.id).where(LinxOpenReceivable.company_id == company_id).limit(1))
    )
    if full_refresh or not has_any_row:
        return LinxOpenReceivablesSyncPlan(mode="full", timestamp=0)

    latest_timestamp = int(
        db.scalar(
            select(func.max(LinxOpenReceivable.linx_row_timestamp)).where(LinxOpenReceivable.company_id == company_id)
        )
        or 0
    )
    return LinxOpenReceivablesSyncPlan(mode="incremental", timestamp=latest_timestamp)


def _collect_rows(
    settings: LinxApiSettings,
    *,
    start_timestamp: int,
    hasher: Any,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_timestamp = start_timestamp
    while True:
        params = {
            "data_inicial": LINX_FULL_LOAD_START,
            "data_fim": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": str(current_timestamp),
        }
        response_bytes, page_rows = _fetch_linx_rows(
            settings,
            method_name=LINX_FATURAS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, LINX_FATURAS_METHOD, params, response_bytes)
        if not page_rows:
            break
        rows.extend(page_rows)
        max_timestamp = max(_parse_int(row.get("timestamp")) or current_timestamp for row in page_rows)
        if max_timestamp <= current_timestamp or len(page_rows) < LINX_PAGE_LIMIT:
            break
        current_timestamp = max_timestamp
    return rows


def _normalize_rows(rows: list[dict[str, str]]) -> tuple[dict[int, dict[str, object]], int]:
    normalized_by_code: dict[int, dict[str, object]] = {}
    duplicate_rows = 0
    for row in rows:
        linx_code = _parse_int(row.get("codigo_fatura"))
        if linx_code is None:
            continue
        normalized = {
            "qualifies": _row_qualifies(row),
            "payload": _normalize_row_payload(row),
            "timestamp": _parse_int(row.get("timestamp")) or 0,
        }
        previous = normalized_by_code.get(linx_code)
        if previous is not None:
            duplicate_rows += 1
            if int(normalized["timestamp"]) <= int(previous["timestamp"]):
                continue
        normalized_by_code[linx_code] = normalized
    return normalized_by_code, duplicate_rows


def _row_qualifies(row: dict[str, str]) -> bool:
    receber_pagar = (_clean_text(row.get("receber_pagar")) or "").upper()
    forma_pgto = _normalize_text_key(row.get("forma_pgto"))
    data_baixa = _clean_text(row.get("data_baixa"))
    cancelado = (_clean_text(row.get("cancelado")) or "N").upper()
    excluido = (_clean_text(row.get("excluido")) or "N").upper()
    if (
        receber_pagar == "R"
        and forma_pgto == "crediario"
        and not data_baixa
        and cancelado != "S"
        and excluido != "S"
    ):
        return True
    return (
        receber_pagar == "R"
        and forma_pgto == "crediário".lower()
        and not data_baixa
        and cancelado != "S"
        and excluido != "S"
    )


def _normalize_row_payload(row: dict[str, str]) -> dict[str, object]:
    linx_code = _parse_int(row.get("codigo_fatura"))
    if linx_code is None:
        raise ValueError("Linha Linx sem codigo_fatura.")
    return {
        "portal": _parse_int(row.get("portal")),
        "company_code": _parse_int(row.get("empresa")),
        "linx_code": linx_code,
        "customer_code": _parse_int(row.get("cod_cliente")),
        "customer_name": _clean_text(row.get("nome_cliente")) or f"Cliente {linx_code}",
        "issue_date": _parse_datetime(row.get("data_emissao")),
        "due_date": _parse_datetime(row.get("data_vencimento")),
        "amount": _parse_decimal(row.get("valor_fatura")),
        "paid_amount": _parse_decimal(row.get("valor_pago")),
        "discount_amount": _parse_decimal(row.get("valor_desconto")),
        "interest_amount": _parse_decimal(row.get("valor_juros")),
        "document_number": _clean_text(row.get("documento")),
        "document_series": _clean_text(row.get("serie")),
        "installment_number": _parse_int(row.get("ordem_parcela")),
        "installment_count": _parse_int(row.get("qtde_parcelas")),
        "identifier": _clean_text(row.get("identificador")),
        "payment_method_name": _clean_text(row.get("forma_pgto")),
        "payment_plan_code": _parse_int(row.get("plano")),
        "seller_code": _parse_int(row.get("vendedor")),
        "observation": _clean_text(row.get("observacao")),
        "linx_row_timestamp": _parse_int(row.get("timestamp")),
    }


def _load_existing_rows(
    db: Session,
    *,
    company_id: str,
    codes: set[int],
) -> dict[int, LinxOpenReceivable]:
    if not codes:
        return {}
    return {
        int(item.linx_code): item
        for item in db.scalars(
            select(LinxOpenReceivable).where(
                LinxOpenReceivable.company_id == company_id,
                LinxOpenReceivable.linx_code.in_(sorted(codes)),
            )
        )
    }


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


def _build_error_summary(*, duplicate_rows: int, ignored: int, removed: int) -> str | None:
    parts: list[str] = []
    if duplicate_rows:
        parts.append(f"{duplicate_rows} linha(s) duplicadas foram consolidadas pelo maior timestamp.")
    if ignored:
        parts.append(f"{ignored} linha(s) alteradas nao se enquadraram no filtro de crediario em aberto.")
    if removed:
        parts.append(f"{removed} fatura(s) deixaram de estar em aberto e foram removidas da base espelho.")
    return " ".join(parts) or None


def _update_fingerprint(hasher: Any, method_name: str, parameters: dict[str, str], response_bytes: bytes) -> None:
    hasher.update(method_name.encode("utf-8"))
    hasher.update(b"\n")
    hasher.update(json.dumps(parameters, sort_keys=True, ensure_ascii=True).encode("utf-8"))
    hasher.update(b"\n")
    hasher.update(response_bytes)
    hasher.update(b"\n")


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
            raise ValueError(f"Falha ao consultar o webservice Linx ({method_name}).") from error
    response_bytes = response.content
    return response_bytes, _parse_linx_rows(response_bytes)


def _build_request_xml(
    settings: LinxApiSettings,
    *,
    method_name: str,
    parameters: dict[str, str],
) -> bytes:
    root = ET.Element("LinxMicrovix")
    ET.SubElement(root, "Authentication", {"user": LINX_WS_USERNAME, "password": LINX_WS_PASSWORD})
    response_format = ET.SubElement(root, "ResponseFormat")
    response_format.text = "xml"
    command = ET.SubElement(root, "Command")
    ET.SubElement(command, "Name").text = method_name
    parameter_root = ET.SubElement(command, "Parameters")
    for parameter_name, parameter_value in {"chave": settings.api_key, "cnpjEmp": settings.cnpj, **parameters}.items():
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


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.replace("\xa0", " ").split())
    return cleaned or None


def _normalize_text_key(value: str | None) -> str:
    cleaned = _clean_text(value) or ""
    normalized = unicodedata.normalize("NFKD", cleaned)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_accents.strip().lower()


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


def _parse_datetime(value: str | None) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None

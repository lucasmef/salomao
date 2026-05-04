from __future__ import annotations

import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import String, and_, case, cast, delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer, LinxMovement, LinxProduct
from app.db.models.security import Company
from app.schemas.imports import ImportResult
from app.schemas.linx_movements import (
    LinxMovementDirectoryRead,
    LinxMovementDirectorySummaryRead,
    LinxMovementListItemRead,
    LinxSalesReportItemRead,
    LinxSalesReportRead,
    LinxSalesReportSummaryRead,
)
from app.services.linx import LinxApiSettings, load_linx_api_settings

LINX_MOVEMENTS_SOURCE = "linx_movements"
LINX_MOVEMENTS_METHOD = "LinxMovimento"
LINX_WS_USERNAME = "linx_export"
LINX_WS_PASSWORD = "linx_export"
LINX_API_TIMEOUT_SECONDS = 90.0
LINX_FULL_LOAD_START = "2020-01-01 00:00:00"
LINX_PAGE_LIMIT = 5000
LINX_EXISTING_LOOKUP_CHUNK_SIZE = 5000

NATURE_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "5.102": ("sale", "sale"),
    "36": ("sale", "sale"),
    "1.201": ("sale", "sale_return"),
    "38": ("sale", "sale_return"),
    "1.102": ("purchase", "purchase"),
    "33": ("purchase", "purchase_return"),
    "46": ("purchase", "purchase_return"),
}

NATURE_DESCRIPTION_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "S - VENDA DE MERCADORIA": ("sale", "sale"),
    "S - NOVA VENDA DE MERCADORIA": ("sale", "sale"),
    "D - DEVOLUCAO DE VENDA DE MERCADORIA": ("sale", "sale_return"),
    "E - COMPRA DE MERCADORIAS": ("purchase", "purchase"),
    "D - DEVOLUCAO DE COMPRA": ("purchase", "purchase_return"),
    "D - DEVOLUCAO DE COMPRA SEM DESTAQUE": ("purchase", "purchase_return"),
}


@dataclass(frozen=True)
class LinxMovementsSyncPlan:
    mode: str
    timestamp: int
    clear_existing: bool


def sync_linx_movements(
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
                "source": LINX_MOVEMENTS_SOURCE,
                "mode": plan.mode,
                "timestamp": plan.timestamp,
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    )

    rows = _collect_rows(settings, start_timestamp=plan.timestamp, hasher=hasher)
    normalized_by_transaction, duplicate_rows = _normalize_rows(rows)

    fingerprint = hasher.hexdigest()
    existing_batch = _find_existing_batch(db, company.id, LINX_MOVEMENTS_SOURCE, fingerprint)
    if existing_batch is not None:
        return ImportResult(
            batch=existing_batch,
            message="Sincronizacao de movimentos Linx ja processada anteriormente.",
        )

    existing_by_transaction = {}
    if plan.clear_existing and rows:
        db.execute(delete(LinxMovement).where(LinxMovement.company_id == company.id))
        db.flush()
    else:
        existing_by_transaction = _load_existing_rows(
            db,
            company_id=company.id,
            transactions=set(normalized_by_transaction),
        )

    batch = ImportBatch(
        company_id=company.id,
        source_type=LINX_MOVEMENTS_SOURCE,
        filename=f"linx-movements-{plan.mode}.xml",
        fingerprint=fingerprint,
        status="processing",
    )
    db.add(batch)
    db.flush()

    inserted = 0
    updated = 0
    removed = 0
    ignored = 0

    for linx_transaction, normalized in normalized_by_transaction.items():
        existing = existing_by_transaction.get(linx_transaction)
        if not normalized["qualifies"]:
            if existing is not None:
                db.delete(existing)
                removed += 1
            else:
                ignored += 1
            continue

        payload = dict(normalized["payload"])
        if existing is None:
            movement = LinxMovement(
                company_id=company.id,
                source_batch_id=batch.id,
                last_seen_batch_id=batch.id,
                **payload,
            )
            db.add(movement)
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
    batch.error_summary = _build_error_summary(
        duplicate_rows=duplicate_rows,
        ignored=ignored,
        removed=removed,
        cleared=plan.clear_existing and bool(rows),
    )
    db.commit()
    db.refresh(batch)

    if not rows:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de movimentos Linx concluida sem alteracoes.",
        )

    message = (
        "Movimentos Linx sincronizados com sucesso. "
        f"{inserted} novo(s), {updated} atualizado(s) e {removed} removido(s)."
    )
    return ImportResult(batch=batch, message=message)


def list_linx_movements(
    db: Session,
    company: Company,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    group: str = "all",
    movement_type: str = "all",
) -> LinxMovementDirectoryRead:
    page = max(page, 1)
    page_size = min(max(page_size, 10), 200)

    base_filters = [LinxMovement.company_id == company.id]
    filtered_filters = list(base_filters)

    normalized_group = (group or "all").strip().lower()
    if normalized_group in {"sale", "purchase"}:
        filtered_filters.append(LinxMovement.movement_group == normalized_group)

    normalized_type = (movement_type or "all").strip().lower()
    if normalized_type in {"sale", "sale_return", "purchase", "purchase_return"}:
        filtered_filters.append(LinxMovement.movement_type == normalized_type)

    join_condition = and_(
        LinxProduct.company_id == LinxMovement.company_id,
        LinxProduct.linx_code == LinxMovement.product_code,
    )

    normalized_search = _clean_text(search)
    if normalized_search:
        pattern = f"%{normalized_search}%"
        filtered_filters.append(
            or_(
                cast(LinxMovement.linx_transaction, String).ilike(pattern),
                LinxMovement.document_number.ilike(pattern),
                LinxMovement.identifier.ilike(pattern),
                cast(LinxMovement.product_code, String).ilike(pattern),
                LinxMovement.nature_description.ilike(pattern),
                LinxProduct.description.ilike(pattern),
                LinxProduct.reference.ilike(pattern),
                LinxProduct.collection_name.ilike(pattern),
            )
        )

    total = int(
        db.scalar(
            select(func.count())
            .select_from(LinxMovement)
            .outerjoin(LinxProduct, join_condition)
            .where(*filtered_filters)
        )
        or 0
    )

    rows = db.execute(
        select(
            LinxMovement,
            LinxProduct.description,
            LinxProduct.reference,
            LinxProduct.collection_name,
        )
        .outerjoin(LinxProduct, join_condition)
        .where(*filtered_filters)
        .order_by(LinxMovement.launch_date.desc(), LinxMovement.linx_transaction.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    summary_row = db.execute(
        select(
            func.count(LinxMovement.id),
            func.coalesce(
                func.sum(
                    case((LinxMovement.movement_type == "sale", LinxMovement.total_amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "sale_return", LinxMovement.total_amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "purchase", LinxMovement.total_amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            LinxMovement.movement_type == "purchase_return",
                            LinxMovement.total_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*base_filters)
    ).one()

    return LinxMovementDirectoryRead(
        generated_at=datetime.now(timezone.utc),
        summary=LinxMovementDirectorySummaryRead(
            total_count=int(summary_row[0] or 0),
            sales_total_amount=Decimal(summary_row[1] or 0),
            sales_return_total_amount=Decimal(summary_row[2] or 0),
            purchases_total_amount=Decimal(summary_row[3] or 0),
            purchase_returns_total_amount=Decimal(summary_row[4] or 0),
        ),
        items=[
            LinxMovementListItemRead(
                id=item.id,
                linx_transaction=int(item.linx_transaction),
                movement_group=item.movement_group,
                movement_type=item.movement_type,
                document_number=item.document_number,
                document_series=item.document_series,
                identifier=item.identifier,
                issue_date=item.issue_date,
                launch_date=item.launch_date,
                customer_code=item.customer_code,
                product_code=int(item.product_code) if item.product_code is not None else None,
                product_description=product_description,
                product_reference=product_reference,
                collection_name=collection_name,
                quantity=item.quantity,
                cost_price=item.cost_price,
                unit_price=item.unit_price,
                net_amount=item.net_amount,
                total_amount=item.total_amount,
                item_discount_amount=item.item_discount_amount,
                nature_code=item.nature_code,
                nature_description=item.nature_description,
                cfop_description=item.cfop_description,
                linx_updated_at=item.linx_updated_at,
                linx_row_timestamp=item.linx_row_timestamp,
            )
            for item, product_description, product_reference, collection_name in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_linx_sales_report(
    db: Session,
    company: Company,
    *,
    page: int = 1,
    page_size: int = 50,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
) -> LinxSalesReportRead:
    page = max(page, 1)
    page_size = min(max(page_size, 10), 200)
    movement_date = func.coalesce(LinxMovement.issue_date, LinxMovement.launch_date)
    base_filters = [
        LinxMovement.company_id == company.id,
        LinxMovement.movement_group == "sale",
        LinxMovement.canceled.is_(False),
        LinxMovement.excluded.is_(False),
    ]
    if start_date:
        base_filters.append(func.date(movement_date) >= start_date)
    if end_date:
        base_filters.append(func.date(movement_date) <= end_date)

    customer_join = and_(
        LinxCustomer.company_id == LinxMovement.company_id,
        LinxCustomer.linx_code == LinxMovement.customer_code,
    )
    normalized_search = _clean_text(search)
    if normalized_search:
        pattern = f"%{normalized_search}%"
        base_filters.append(
            or_(
                LinxMovement.document_number.ilike(pattern),
                cast(LinxMovement.customer_code, String).ilike(pattern),
                LinxCustomer.legal_name.ilike(pattern),
                LinxCustomer.display_name.ilike(pattern),
            )
        )

    gross_expr = func.coalesce(
        func.sum(
            case((LinxMovement.movement_type == "sale", LinxMovement.total_amount), else_=0)
        ),
        0,
    )
    returns_expr = func.coalesce(
        func.sum(
            case((LinxMovement.movement_type == "sale_return", LinxMovement.total_amount), else_=0)
        ),
        0,
    )
    quantity_expr = func.coalesce(func.sum(LinxMovement.quantity), 0)
    document_number_expr = func.coalesce(LinxMovement.document_number, "")
    document_series_expr = func.coalesce(LinxMovement.document_series, "")
    grouped = (
        select(
            document_number_expr.label("document_number"),
            document_series_expr.label("document_series"),
            LinxMovement.customer_code.label("customer_code"),
            func.min(LinxMovement.issue_date).label("issue_date"),
            func.min(LinxMovement.launch_date).label("launch_date"),
            func.count(LinxMovement.id).label("item_count"),
            quantity_expr.label("quantity"),
            gross_expr.label("gross_amount"),
            returns_expr.label("returns_amount"),
            (gross_expr - returns_expr).label("net_amount"),
            func.max(func.coalesce(LinxCustomer.display_name, LinxCustomer.legal_name)).label(
                "customer_name"
            ),
        )
        .select_from(LinxMovement)
        .outerjoin(LinxCustomer, customer_join)
        .where(*base_filters)
        .group_by(
            document_number_expr,
            document_series_expr,
            LinxMovement.customer_code,
        )
    ).subquery()

    total = int(db.scalar(select(func.count()).select_from(grouped)) or 0)
    rows = db.execute(
        select(
            grouped.c.document_number,
            grouped.c.document_series,
            grouped.c.customer_code,
            grouped.c.issue_date,
            grouped.c.launch_date,
            grouped.c.item_count,
            grouped.c.quantity,
            grouped.c.gross_amount,
            grouped.c.returns_amount,
            grouped.c.net_amount,
            grouped.c.customer_name,
        )
        .order_by(
            grouped.c.launch_date.desc(),
            grouped.c.issue_date.desc(),
            grouped.c.document_number.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).mappings().all()
    summary_row = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(grouped.c.quantity), 0),
            func.coalesce(func.sum(grouped.c.gross_amount), 0),
            func.coalesce(func.sum(grouped.c.returns_amount), 0),
            func.coalesce(func.sum(grouped.c.net_amount), 0),
        ).select_from(grouped)
    ).one()

    return LinxSalesReportRead(
        generated_at=datetime.now(timezone.utc),
        summary=LinxSalesReportSummaryRead(
            total_invoices=int(summary_row[0] or 0),
            total_quantity=Decimal(summary_row[1] or 0),
            gross_amount=Decimal(summary_row[2] or 0),
            returns_amount=Decimal(summary_row[3] or 0),
            net_amount=Decimal(summary_row[4] or 0),
        ),
        items=[
            LinxSalesReportItemRead(
                key=f"{row.document_number}|{row.document_series}|{row.customer_code}",
                document_number=row.document_number or None,
                document_series=row.document_series or None,
                customer_code=row.customer_code,
                customer_name=row.customer_name,
                issue_date=row.issue_date,
                launch_date=row.launch_date,
                item_count=int(row.item_count or 0),
                quantity=Decimal(row.quantity or 0),
                gross_amount=Decimal(row.gross_amount or 0),
                returns_amount=Decimal(row.returns_amount or 0),
                net_amount=Decimal(row.net_amount or 0),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _build_sync_plan(
    db: Session,
    *,
    company_id: str,
    full_refresh: bool,
) -> LinxMovementsSyncPlan:
    has_any_row = bool(
        db.scalar(select(LinxMovement.id).where(LinxMovement.company_id == company_id).limit(1))
    )
    if full_refresh or not has_any_row:
        return LinxMovementsSyncPlan(
            mode="full",
            timestamp=0,
            clear_existing=full_refresh or not has_any_row,
        )

    latest_timestamp = int(
        db.scalar(
            select(func.max(LinxMovement.linx_row_timestamp)).where(
                LinxMovement.company_id == company_id
            )
        )
        or 0
    )
    return LinxMovementsSyncPlan(
        mode="incremental",
        timestamp=latest_timestamp,
        clear_existing=False,
    )


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
            method_name=LINX_MOVEMENTS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, LINX_MOVEMENTS_METHOD, params, response_bytes)
        if not page_rows:
            break
        rows.extend(page_rows)
        max_timestamp = max(
            _parse_int(row.get("timestamp")) or current_timestamp for row in page_rows
        )
        if max_timestamp <= current_timestamp:
            break
        current_timestamp = max_timestamp
    return rows


def _normalize_rows(rows: list[dict[str, str]]) -> tuple[dict[int, dict[str, object]], int]:
    normalized_by_transaction: dict[int, dict[str, object]] = {}
    duplicate_rows = 0
    for row in rows:
        linx_transaction = _parse_int(row.get("transacao"))
        if linx_transaction is None:
            continue
        normalized = {
            "qualifies": _row_qualifies(row),
            "payload": _normalize_row_payload(row),
            "timestamp": _parse_int(row.get("timestamp")) or 0,
        }
        previous = normalized_by_transaction.get(linx_transaction)
        if previous is not None:
            duplicate_rows += 1
            if int(normalized["timestamp"]) <= int(previous["timestamp"]):
                continue
        normalized_by_transaction[linx_transaction] = normalized
    return normalized_by_transaction, duplicate_rows


def _row_qualifies(row: dict[str, str]) -> bool:
    movement_group, movement_type = _classify_nature(row)
    if movement_group == "other" or movement_type == "other":
        return False
    if (_clean_text(row.get("cancelado")) or "N").upper() == "S":
        return False
    if (_clean_text(row.get("excluido")) or "N").upper() == "S":
        return False
    return _parse_int(row.get("cod_produto")) is not None


def _normalize_row_payload(row: dict[str, str]) -> dict[str, object]:
    linx_transaction = _parse_int(row.get("transacao"))
    if linx_transaction is None:
        raise ValueError("Linha Linx sem transacao.")

    nature_code = (_clean_text(row.get("cod_natureza_operacao")) or "").strip()
    movement_group, movement_type = _classify_nature(row)

    return {
        "portal": _parse_int(row.get("portal")),
        "company_code": _parse_int(row.get("empresa")),
        "linx_transaction": linx_transaction,
        "document_number": _clean_text(row.get("documento")),
        "document_series": _clean_text(row.get("serie")),
        "identifier": _clean_text(row.get("identificador")),
        "movement_group": movement_group,
        "movement_type": movement_type,
        "operation_code": (_clean_text(row.get("operacao")) or "").strip() or None,
        "transaction_type_code": (_clean_text(row.get("tipo_transacao")) or "").strip() or None,
        "nature_code": nature_code or None,
        "nature_description": _clean_text(row.get("natureza_operacao")),
        "cfop_code": _parse_int(row.get("id_cfop")),
        "cfop_description": _clean_text(row.get("desc_cfop")),
        "issue_date": _parse_datetime(row.get("data_documento")),
        "launch_date": _parse_datetime(row.get("data_lancamento")),
        "linx_updated_at": _parse_datetime(row.get("dt_update")),
        "customer_code": _parse_int(row.get("codigo_cliente")),
        "seller_code": _parse_int(row.get("cod_vendedor")),
        "product_code": _parse_int(row.get("cod_produto")),
        "product_barcode": _clean_text(row.get("cod_barra")),
        "quantity": _parse_decimal(row.get("quantidade")),
        "cost_price": _parse_decimal(row.get("preco_custo")),
        "unit_price": _parse_decimal(row.get("preco_unitario")),
        "net_amount": _parse_decimal(row.get("valor_liquido")),
        "total_amount": _parse_decimal(row.get("valor_total")),
        "discount_amount": _parse_decimal(row.get("desconto")),
        "item_discount_amount": _parse_decimal(row.get("desconto_total_item")),
        "canceled": _parse_bool(row.get("cancelado")),
        "excluded": _parse_bool(row.get("excluido")),
        "line_order": _parse_int(row.get("ordem")),
        "note": _clean_text(row.get("obs")),
        "linx_row_timestamp": _parse_int(row.get("timestamp")),
    }


def _classify_nature(row: dict[str, str]) -> tuple[str, str]:
    nature_code = (_clean_text(row.get("cod_natureza_operacao")) or "").strip()
    if nature_code in NATURE_CLASSIFICATION:
        return NATURE_CLASSIFICATION[nature_code]

    normalized_description = _normalize_nature_description(row.get("natureza_operacao"))
    if normalized_description in NATURE_DESCRIPTION_CLASSIFICATION:
        return NATURE_DESCRIPTION_CLASSIFICATION[normalized_description]

    return ("other", "other")


def _normalize_nature_description(value: str | None) -> str:
    cleaned = (_clean_text(value) or "").replace("–", "-")
    if not cleaned:
        return ""
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized_hyphen = ascii_only.replace("D-", "D - ")
    return " ".join(normalized_hyphen.upper().split())


def _load_existing_rows(
    db: Session,
    *,
    company_id: str,
    transactions: set[int],
) -> dict[int, LinxMovement]:
    if not transactions:
        return {}

    existing: dict[int, LinxMovement] = {}
    transaction_list = sorted(transactions)
    for start_index in range(0, len(transaction_list), LINX_EXISTING_LOOKUP_CHUNK_SIZE):
        chunk = transaction_list[start_index : start_index + LINX_EXISTING_LOOKUP_CHUNK_SIZE]
        for item in db.scalars(
            select(LinxMovement).where(
                LinxMovement.company_id == company_id,
                LinxMovement.linx_transaction.in_(chunk),
            )
        ):
            existing[int(item.linx_transaction)] = item
    return existing


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


def _build_error_summary(
    *,
    duplicate_rows: int,
    ignored: int,
    removed: int,
    cleared: bool,
) -> str | None:
    parts: list[str] = []
    if cleared:
        parts.append("A base local de movimentos foi recriada no full refresh.")
    if duplicate_rows:
        parts.append(
            f"{duplicate_rows} linha(s) duplicadas foram consolidadas pelo maior timestamp."
        )
    if ignored:
        parts.append(f"{ignored} linha(s) nao se enquadraram nas naturezas monitoradas.")
    if removed:
        parts.append(
            f"{removed} linha(s) deixaram de se enquadrar e foram removidas da base espelho."
        )
    return " ".join(parts) or None


def _update_fingerprint(
    hasher: Any,
    method_name: str,
    parameters: dict[str, str],
    response_bytes: bytes,
) -> None:
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
    request_parameters = {
        "chave": settings.api_key,
        "cnpjEmp": settings.cnpj,
        **parameters,
    }
    for parameter_name, parameter_value in request_parameters.items():
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


def _parse_bool(value: str | None) -> bool:
    cleaned = (_clean_text(value) or "").strip().upper()
    return cleaned in {"1", "S", "TRUE"}

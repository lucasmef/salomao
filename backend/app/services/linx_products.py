from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer, LinxProduct
from app.db.models.security import Company
from app.schemas.imports import ImportResult
from app.schemas.linx_products import (
    LinxProductDirectoryRead,
    LinxProductDirectorySummaryRead,
    LinxProductListItemRead,
    LinxProductSearchRead,
)
from app.services.linx import LinxApiSettings, load_linx_api_settings

LINX_PRODUCTS_SOURCE = "linx_products"
LINX_PRODUCTS_METHOD = "LinxProdutos"
LINX_PRODUCTS_DETAILS_METHOD = "LinxProdutosDetalhes"
LINX_CUSTOMERS_METHOD = "LinxClientesFornec"
LINX_WS_USERNAME = "linx_export"
LINX_WS_PASSWORD = "linx_export"
LINX_API_TIMEOUT_SECONDS = 90.0
LINX_FULL_LOAD_START = date(2000, 1, 1)
LINX_FULL_LOAD_START_DATETIME = "2000-01-01 00:00:00"
PRODUCTS_PAGE_LIMIT = 5000
PRODUCT_DETAILS_PAGE_LIMIT = 5000
MAX_PRODUCT_SEARCH_CANDIDATES = 800
MAX_PRODUCT_SEARCH_RESULTS = 60


@dataclass(frozen=True)
class LinxProductsSyncPlan:
    mode: str
    product_timestamp: int
    detail_timestamp: int


def sync_linx_products(
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
                "source": LINX_PRODUCTS_SOURCE,
                "mode": plan.mode,
                "product_timestamp": plan.product_timestamp,
                "detail_timestamp": plan.detail_timestamp,
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    )

    product_rows = _collect_product_rows(settings, start_timestamp=plan.product_timestamp, hasher=hasher)
    detail_rows = _collect_detail_rows(settings, start_timestamp=plan.detail_timestamp, hasher=hasher)

    normalized_products, product_duplicate_rows = _normalize_product_rows(product_rows)
    normalized_details, detail_duplicate_rows = _normalize_detail_rows(detail_rows)

    touched_codes = set(normalized_products) | set(normalized_details)
    existing_by_code = _load_existing_products(db, company_id=company.id, codes=touched_codes)

    missing_master_codes = sorted(
        code for code in touched_codes if code not in normalized_products and code not in existing_by_code
    )
    fallback_products = _fetch_products_by_code(settings, missing_master_codes, hasher=hasher)
    for code, payload in fallback_products.items():
        normalized_products.setdefault(code, payload)

    supplier_codes: set[int] = {
        int(payload["supplier_code"])
        for payload in normalized_products.values()
        if payload.get("supplier_code") is not None
    }
    supplier_codes.update(
        int(existing.supplier_code)
        for code, existing in existing_by_code.items()
        if code in touched_codes and existing.supplier_code is not None
    )
    supplier_names = _resolve_supplier_names(
        db,
        company_id=company.id,
        settings=settings,
        supplier_codes=supplier_codes,
        hasher=hasher,
    )

    fingerprint = hasher.hexdigest()
    existing_batch = _find_existing_batch(db, company.id, LINX_PRODUCTS_SOURCE, fingerprint)
    if existing_batch is not None:
        return ImportResult(
            batch=existing_batch,
            message="Sincronizacao de produtos Linx ja processada anteriormente.",
        )

    batch = ImportBatch(
        company_id=company.id,
        source_type=LINX_PRODUCTS_SOURCE,
        filename=f"linx-products-{plan.mode}.xml",
        fingerprint=fingerprint,
        status="processing",
    )
    db.add(batch)
    db.flush()

    inserted = 0
    updated = 0
    unchanged = 0
    skipped_missing_master = 0

    for linx_code in sorted(touched_codes):
        master_payload = normalized_products.get(linx_code)
        detail_payload = normalized_details.get(linx_code)
        existing = existing_by_code.get(linx_code)

        supplier_code = None
        if master_payload is not None:
            supplier_code = master_payload.get("supplier_code")
        elif existing is not None:
            supplier_code = existing.supplier_code

        supplier_name = None
        if supplier_code is not None:
            supplier_name = supplier_names.get(int(supplier_code))

        if existing is None and master_payload is None:
            skipped_missing_master += 1
            continue

        if existing is None:
            product = LinxProduct(
                company_id=company.id,
                source_batch_id=batch.id,
                last_seen_batch_id=batch.id,
                linx_code=linx_code,
                description=str(master_payload["description"]),
            )
            _apply_product_payload(product, master_payload=master_payload, detail_payload=detail_payload)
            if supplier_name:
                product.supplier_name = supplier_name
            db.add(product)
            inserted += 1
            continue

        changed = _apply_product_payload(existing, master_payload=master_payload, detail_payload=detail_payload)
        if supplier_name and existing.supplier_name != supplier_name:
            existing.supplier_name = supplier_name
            changed = True
        existing.last_seen_batch_id = batch.id
        if changed:
            updated += 1
        else:
            unchanged += 1

    batch.records_total = len(product_rows) + len(detail_rows) + len(fallback_products)
    batch.records_valid = inserted + updated + unchanged
    batch.records_invalid = product_duplicate_rows + detail_duplicate_rows + skipped_missing_master
    batch.status = "processed"
    batch.error_summary = _build_error_summary(
        product_duplicate_rows=product_duplicate_rows,
        detail_duplicate_rows=detail_duplicate_rows,
        skipped_missing_master=skipped_missing_master,
    )
    db.commit()
    db.refresh(batch)

    if not touched_codes:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de produtos Linx concluida sem alteracoes.",
        )

    message = (
        "Produtos Linx sincronizados com sucesso. "
        f"{inserted} novo(s), {updated} atualizado(s) e {unchanged} sem alteracao."
    )
    return ImportResult(batch=batch, message=message)


def list_linx_products(
    db: Session,
    company: Company,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    status: str = "all",
) -> LinxProductDirectoryRead:
    page = max(page, 1)
    page_size = min(max(page_size, 10), 200)

    base_filters = [LinxProduct.company_id == company.id]
    filtered_filters = list(base_filters)

    normalized_status = (status or "all").strip().lower()
    if normalized_status == "active":
        filtered_filters.append(LinxProduct.is_active.is_(True))
    elif normalized_status == "inactive":
        filtered_filters.append(LinxProduct.is_active.is_(False))

    normalized_search = _clean_text(search)
    if normalized_search:
        pattern = f"%{normalized_search}%"
        filtered_filters.append(
            or_(
                cast(LinxProduct.linx_code, String).ilike(pattern),
                LinxProduct.description.ilike(pattern),
                LinxProduct.reference.ilike(pattern),
                LinxProduct.barcode.ilike(pattern),
                LinxProduct.supplier_name.ilike(pattern),
                LinxProduct.collection_name.ilike(pattern),
            )
        )

    total = int(
        db.scalar(
            select(func.count())
            .select_from(LinxProduct)
            .where(*filtered_filters)
        )
        or 0
    )

    items = list(
        db.scalars(
            select(LinxProduct)
            .where(*filtered_filters)
            .order_by(LinxProduct.description.asc(), LinxProduct.linx_code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    summary_row = db.execute(
        select(
            func.count(LinxProduct.id),
            func.sum(case((LinxProduct.is_active.is_(True), 1), else_=0)),
            func.sum(case((LinxProduct.is_active.is_(False), 1), else_=0)),
            func.sum(case((LinxProduct.supplier_name.is_not(None), 1), else_=0)),
            func.sum(case((LinxProduct.collection_name.is_not(None), 1), else_=0)),
        ).where(*base_filters)
    ).one()

    return LinxProductDirectoryRead(
        generated_at=datetime.now(timezone.utc),
        summary=LinxProductDirectorySummaryRead(
            total_count=int(summary_row[0] or 0),
            active_count=int(summary_row[1] or 0),
            inactive_count=int(summary_row[2] or 0),
            with_supplier_count=int(summary_row[3] or 0),
            with_collection_count=int(summary_row[4] or 0),
        ),
        items=[_serialize_linx_product(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


def search_linx_products(
    db: Session,
    company: Company,
    *,
    query: str,
    limit: int = 20,
) -> LinxProductSearchRead:
    normalized_query = _normalize_search_text(query)
    tokens = _tokenize_search_query(normalized_query)
    safe_limit = min(max(limit, 1), MAX_PRODUCT_SEARCH_RESULTS)
    if not normalized_query or not tokens:
        return LinxProductSearchRead(
            generated_at=datetime.now(timezone.utc),
            query=query,
            total=0,
            items=[],
        )

    candidates = _load_search_candidates(db, company_id=company.id, tokens=tokens)
    scored_candidates: list[tuple[float, LinxProduct]] = []
    for candidate in candidates:
        score = _score_product_search(candidate, normalized_query=normalized_query, tokens=tokens)
        if score <= 0:
            continue
        scored_candidates.append((score, candidate))

    scored_candidates.sort(
        key=lambda item: (
            -item[0],
            0 if (item[1].stock_quantity or Decimal("0")) > 0 else 1,
            -float(item[1].stock_quantity or 0),
            0 if item[1].is_active else 1,
            item[1].description.lower(),
            int(item[1].linx_code),
        )
    )

    return LinxProductSearchRead(
        generated_at=datetime.now(timezone.utc),
        query=query,
        total=len(scored_candidates),
        items=[_serialize_linx_product(item) for _score, item in scored_candidates[:safe_limit]],
    )


def _build_sync_plan(
    db: Session,
    *,
    company_id: str,
    full_refresh: bool,
) -> LinxProductsSyncPlan:
    has_any_product = bool(
        db.scalar(select(LinxProduct.id).where(LinxProduct.company_id == company_id).limit(1))
    )
    if full_refresh or not has_any_product:
        return LinxProductsSyncPlan(mode="full", product_timestamp=0, detail_timestamp=0)

    product_timestamp = int(
        db.scalar(select(func.max(LinxProduct.linx_row_timestamp)).where(LinxProduct.company_id == company_id)) or 0
    )
    detail_timestamp = int(
        db.scalar(
            select(func.max(LinxProduct.linx_detail_row_timestamp)).where(LinxProduct.company_id == company_id)
        )
        or 0
    )
    return LinxProductsSyncPlan(
        mode="incremental",
        product_timestamp=product_timestamp,
        detail_timestamp=detail_timestamp,
    )


def _serialize_linx_product(item: LinxProduct) -> LinxProductListItemRead:
    return LinxProductListItemRead(
        id=item.id,
        linx_code=int(item.linx_code),
        description=item.description,
        reference=item.reference,
        barcode=item.barcode,
        unit=item.unit,
        brand_name=item.brand_name,
        line_name=item.line_name,
        sector_name=item.sector_name,
        supplier_code=item.supplier_code,
        supplier_name=item.supplier_name,
        collection_id=item.collection_id,
        collection_name=item.collection_name,
        collection_name_raw=item.collection_name_raw,
        price_cost=item.price_cost,
        price_sale=item.price_sale,
        stock_quantity=item.stock_quantity,
        is_active=item.is_active,
        linx_updated_at=item.linx_updated_at,
    )


def _normalize_search_text(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _tokenize_search_query(normalized_query: str) -> list[str]:
    tokens = [token for token in normalized_query.split(" ") if token]
    return [token for token in tokens if token.isdigit() or len(token) >= 2]


def _search_patterns_for_token(token: str) -> list[str]:
    patterns = [token]
    if len(token) >= 4:
        patterns.append(token[:3])
    return list(dict.fromkeys(patterns))


def _search_field_clauses(token: str) -> list[object]:
    clauses: list[object] = []
    for pattern_token in _search_patterns_for_token(token):
        like_pattern = f"%{pattern_token}%"
        clauses.extend(
            [
                cast(LinxProduct.linx_code, String).ilike(like_pattern),
                LinxProduct.description.ilike(like_pattern),
                LinxProduct.reference.ilike(like_pattern),
                LinxProduct.brand_name.ilike(like_pattern),
                LinxProduct.collection_name.ilike(like_pattern),
                LinxProduct.barcode.ilike(like_pattern),
                LinxProduct.supplier_name.ilike(like_pattern),
            ]
        )
    return clauses


def _load_search_candidates(db: Session, *, company_id: str, tokens: list[str]) -> list[LinxProduct]:
    primary_filters = [or_(*_search_field_clauses(token)) for token in tokens]
    primary_candidates = list(
        db.scalars(
            select(LinxProduct)
            .where(LinxProduct.company_id == company_id, and_(*primary_filters))
            .order_by(LinxProduct.is_active.desc(), LinxProduct.description.asc(), LinxProduct.linx_code.asc())
            .limit(MAX_PRODUCT_SEARCH_CANDIDATES)
        )
    )
    if primary_candidates:
        return primary_candidates

    fallback_candidates = list(
        db.scalars(
            select(LinxProduct)
            .where(
                LinxProduct.company_id == company_id,
                or_(*[clause for token in tokens for clause in _search_field_clauses(token)]),
            )
            .order_by(LinxProduct.is_active.desc(), LinxProduct.description.asc(), LinxProduct.linx_code.asc())
            .limit(MAX_PRODUCT_SEARCH_CANDIDATES)
        )
    )
    return fallback_candidates


def _field_token_score(token: str, field_words: list[str]) -> float:
    best_score = 0.0
    for word in field_words:
        if token == word:
            return 1.0
        if word.startswith(token):
            best_score = max(best_score, 0.94)
            continue
        if token in word:
            best_score = max(best_score, 0.84)
            continue
        if len(token) < 4:
            continue
        ratio = SequenceMatcher(None, token, word).ratio()
        if ratio >= 0.78:
            best_score = max(best_score, ratio * 0.74)
    return best_score


def _score_product_search(product: LinxProduct, *, normalized_query: str, tokens: list[str]) -> float:
    field_values = {
        "description": _normalize_search_text(product.description),
        "reference": _normalize_search_text(product.reference),
        "brand_name": _normalize_search_text(product.brand_name),
        "collection_name": _normalize_search_text(product.collection_name),
        "barcode": _normalize_search_text(product.barcode),
        "linx_code": _normalize_search_text(str(product.linx_code)),
        "supplier_name": _normalize_search_text(product.supplier_name),
    }
    field_weights = {
        "description": 1.35,
        "brand_name": 1.15,
        "reference": 1.0,
        "collection_name": 0.9,
        "barcode": 1.05,
        "linx_code": 1.1,
        "supplier_name": 0.7,
    }
    combined_text = " ".join(value for value in field_values.values() if value)
    if not combined_text:
        return 0.0

    token_score_total = 0.0
    for token in tokens:
        best_token_score = 0.0
        for field_name, field_value in field_values.items():
            if not field_value:
                continue
            field_words = field_value.split(" ")
            field_score = _field_token_score(token, field_words) * field_weights[field_name]
            best_token_score = max(best_token_score, field_score)
        if best_token_score <= 0:
            return 0.0
        token_score_total += best_token_score

    score = token_score_total * 100
    if normalized_query in combined_text:
        score += 60
    if field_values["description"] and normalized_query in field_values["description"]:
        score += 24
    if field_values["brand_name"] and any(token in field_values["brand_name"] for token in tokens):
        score += 12
    if product.is_active:
        score += 4
    return score


def _collect_product_rows(
    settings: LinxApiSettings,
    *,
    start_timestamp: int,
    hasher: Any,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_timestamp = start_timestamp
    while True:
        params = {
            "dt_update_inicio": LINX_FULL_LOAD_START_DATETIME,
            "dt_update_fim": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filtrar_empresa": "1",
            "timestamp": str(current_timestamp),
        }
        response_bytes, page_rows = _fetch_linx_rows(
            settings,
            method_name=LINX_PRODUCTS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, LINX_PRODUCTS_METHOD, params, response_bytes)
        if not page_rows:
            break
        rows.extend(page_rows)
        max_timestamp = max(_parse_int(row.get("timestamp")) or current_timestamp for row in page_rows)
        if max_timestamp <= current_timestamp or len(page_rows) < PRODUCTS_PAGE_LIMIT:
            break
        current_timestamp = max_timestamp
    return rows


def _collect_detail_rows(
    settings: LinxApiSettings,
    *,
    start_timestamp: int,
    hasher: Any,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_timestamp = start_timestamp
    while True:
        params = {
            "data_mov_ini": LINX_FULL_LOAD_START.isoformat(),
            "data_mov_fim": date.today().isoformat(),
            "retornar_saldo_zero": "1",
            "timestamp": str(current_timestamp),
        }
        response_bytes, page_rows = _fetch_linx_rows(
            settings,
            method_name=LINX_PRODUCTS_DETAILS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, LINX_PRODUCTS_DETAILS_METHOD, params, response_bytes)
        if not page_rows:
            break
        rows.extend(page_rows)
        max_timestamp = max(_parse_int(row.get("timestamp")) or current_timestamp for row in page_rows)
        if max_timestamp <= current_timestamp or len(page_rows) < PRODUCT_DETAILS_PAGE_LIMIT:
            break
        current_timestamp = max_timestamp
    return rows


def _fetch_products_by_code(
    settings: LinxApiSettings,
    codes: list[int],
    *,
    hasher: Any,
) -> dict[int, dict[str, object]]:
    payloads: dict[int, dict[str, object]] = {}
    for code in codes:
        params = {
            "dt_update_inicio": LINX_FULL_LOAD_START_DATETIME,
            "dt_update_fim": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filtrar_empresa": "1",
            "cod_produto": str(code),
            "timestamp": "0",
        }
        response_bytes, rows = _fetch_linx_rows(
            settings,
            method_name=LINX_PRODUCTS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, f"{LINX_PRODUCTS_METHOD}:fallback", params, response_bytes)
        if not rows:
            continue
        normalized = normalize_linx_product_row(rows[0])
        payloads[code] = normalized
    return payloads


def _resolve_supplier_names(
    db: Session,
    *,
    company_id: str,
    settings: LinxApiSettings,
    supplier_codes: set[int],
    hasher: Any,
) -> dict[int, str]:
    if not supplier_codes:
        return {}

    names = {
        int(customer.linx_code): customer.legal_name
        for customer in db.scalars(
            select(LinxCustomer).where(
                LinxCustomer.company_id == company_id,
                LinxCustomer.linx_code.in_(sorted(supplier_codes)),
            )
        )
    }
    missing_codes = sorted(code for code in supplier_codes if code not in names)
    if not missing_codes:
        return names

    today = date.today().isoformat()
    for code in missing_codes:
        params = {
            "data_inicial": LINX_FULL_LOAD_START.isoformat(),
            "data_fim": today,
            "cod_cliente": str(code),
            "timestamp": "0",
        }
        response_bytes, rows = _fetch_linx_rows(
            settings,
            method_name=LINX_CUSTOMERS_METHOD,
            parameters=params,
        )
        _update_fingerprint(hasher, f"{LINX_CUSTOMERS_METHOD}:supplier", params, response_bytes)
        if not rows:
            continue
        legal_name = _clean_text(rows[0].get("razao_cliente")) or _clean_text(rows[0].get("nome_cliente"))
        if legal_name:
            names[code] = legal_name
    return names


def normalize_linx_product_row(row: dict[str, str]) -> dict[str, object]:
    linx_code = _parse_int(row.get("cod_produto"))
    if linx_code is None:
        raise ValueError("Linha Linx sem cod_produto.")

    collection_name_raw = _clean_text(row.get("desc_colecao"))
    return {
        "portal": _parse_int(row.get("portal")),
        "linx_code": linx_code,
        "barcode": _clean_text(row.get("cod_barra")),
        "description": _clean_text(row.get("nome")) or f"Produto Linx {linx_code}",
        "reference": _clean_text(row.get("referencia")),
        "unit": _clean_text(row.get("unidade")),
        "color_name": _clean_text(row.get("desc_cor")),
        "size_name": _clean_text(row.get("desc_tamanho")),
        "sector_name": _clean_text(row.get("desc_setor")),
        "line_name": _clean_text(row.get("desc_linha")),
        "brand_name": _clean_text(row.get("desc_marca")),
        "supplier_code": _parse_int(row.get("cod_fornecedor")),
        "collection_id": _parse_int(row.get("id_colecao")),
        "collection_name_raw": collection_name_raw,
        "collection_name": normalize_collection_name(collection_name_raw),
        "is_active": (_clean_text(row.get("desativado")) or "N").upper() != "S",
        "ncm": _clean_text(row.get("ncm")),
        "cest": _clean_text(row.get("cest")),
        "auxiliary_code": _clean_text(row.get("cod_auxiliar")),
        "linx_created_at": _parse_datetime(row.get("dt_inclusao")),
        "linx_updated_at": _parse_datetime(row.get("dt_update")),
        "linx_row_timestamp": _parse_int(row.get("timestamp")),
    }


def normalize_collection_name(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return re.sub(r"^1\s*-\s*", "", cleaned).strip() or None


def _normalize_detail_rows(rows: list[dict[str, str]]) -> tuple[dict[int, dict[str, object]], int]:
    normalized_by_code: dict[int, dict[str, object]] = {}
    duplicate_rows = 0
    for row in rows:
        linx_code = _parse_int(row.get("cod_produto"))
        if linx_code is None:
            continue
        normalized = {
            "stock_quantity": _parse_decimal(row.get("quantidade")),
            "price_cost": _parse_decimal(row.get("preco_custo")),
            "price_sale": _parse_decimal(row.get("preco_venda")),
            "average_cost": _parse_decimal(row.get("custo_medio")),
            "detail_company_code": _parse_int(row.get("empresa")),
            "detail_location": _clean_text(row.get("localizacao")),
            "linx_detail_row_timestamp": _parse_int(row.get("timestamp")),
        }
        previous = normalized_by_code.get(linx_code)
        if previous is not None:
            duplicate_rows += 1
            if int(normalized.get("linx_detail_row_timestamp") or 0) <= int(
                previous.get("linx_detail_row_timestamp") or 0
            ):
                continue
        normalized_by_code[linx_code] = normalized
    return normalized_by_code, duplicate_rows


def _normalize_product_rows(rows: list[dict[str, str]]) -> tuple[dict[int, dict[str, object]], int]:
    normalized_by_code: dict[int, dict[str, object]] = {}
    duplicate_rows = 0
    for row in rows:
        try:
            normalized = normalize_linx_product_row(row)
        except ValueError:
            continue
        linx_code = int(normalized["linx_code"])
        previous = normalized_by_code.get(linx_code)
        if previous is not None:
            duplicate_rows += 1
            if int(normalized.get("linx_row_timestamp") or 0) <= int(previous.get("linx_row_timestamp") or 0):
                continue
        normalized_by_code[linx_code] = normalized
    return normalized_by_code, duplicate_rows


def _load_existing_products(
    db: Session,
    *,
    company_id: str,
    codes: set[int],
) -> dict[int, LinxProduct]:
    if not codes:
        return {}
    return {
        int(product.linx_code): product
        for product in db.scalars(
            select(LinxProduct).where(
                LinxProduct.company_id == company_id,
                LinxProduct.linx_code.in_(sorted(codes)),
            )
        )
    }


def _apply_product_payload(
    product: LinxProduct,
    *,
    master_payload: dict[str, object] | None,
    detail_payload: dict[str, object] | None,
) -> bool:
    changed = False
    for payload in (master_payload, detail_payload):
        if payload is None:
            continue
        for field_name, value in payload.items():
            if getattr(product, field_name) != value:
                setattr(product, field_name, value)
                changed = True
    return changed


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
    product_duplicate_rows: int,
    detail_duplicate_rows: int,
    skipped_missing_master: int,
) -> str | None:
    parts: list[str] = []
    if product_duplicate_rows:
        parts.append(f"{product_duplicate_rows} linha(s) duplicadas do cadastro foram consolidadas.")
    if detail_duplicate_rows:
        parts.append(f"{detail_duplicate_rows} linha(s) duplicadas de detalhes foram consolidadas.")
    if skipped_missing_master:
        parts.append(
            f"{skipped_missing_master} produto(s) com detalhe alterado foram ignorados por falta de cadastro base."
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

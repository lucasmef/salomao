from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock
from time import monotonic
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.statuses import OPEN_STATUS, OPEN_STATUS_QUERY_VALUES, normalize_open_alias
from app.db.models.finance import Category, FinancialEntry
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxMovement, LinxProduct, PurchasePayableTitle
from app.db.models.purchasing import (
    CollectionSeason,
    PurchaseBrand,
    PurchaseBrandSupplier,
    PurchaseDelivery,
    PurchaseInstallment,
    PurchaseInvoice,
    PurchasePlan,
    PurchasePlanSupplier,
    PurchaseReturn,
    Supplier,
)
from app.db.models.security import Company, User
from app.schemas.financial_entry import FinancialEntryCreate
from app.schemas.imports import ImportResult
from app.schemas.purchase_planning import (
    CollectionSeasonCreate,
    CollectionSeasonRead,
    CollectionSeasonUpdate,
    PurchaseBrandCreate,
    PurchaseBrandRead,
    PurchaseBrandUpdate,
    PurchaseInstallmentCandidate,
    PurchaseInstallmentDraft,
    PurchaseInstallmentRead,
    PurchaseInvoiceCreate,
    PurchaseInvoiceDraft,
    PurchaseInvoiceRead,
    PurchasePlanCreate,
    PurchasePlanningMonthlyProjection,
    PurchasePlanningCostRow,
    PurchasePlanningOverview,
    PurchasePlanningRow,
    PurchasePlanningSummary,
    PurchasePlanningUngroupedSupplier,
    PurchasePlanRead,
    PurchasePlanUpdate,
    PurchaseReturnCreate,
    PurchaseReturnRead,
    PurchaseReturnUpdate,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from app.services.audit import write_audit_log
from app.services.category_catalog import ensure_category_catalog
from app.services.import_parsers import (
    ParsedPurchasePayableRow,
    fingerprint_bytes,
    normalize_label,
    parse_date_br,
    parse_decimal_pt_br,
    parse_purchase_payable_rows,
)
from app.services.linx import download_linx_purchase_payables_report
from app.services.linx import LinxApiSettings, load_linx_api_settings

TWO_PLACES = Decimal("0.01")
HISTORICAL_COLLECTION_START_YEAR = 2020
LINX_PURCHASE_PAYABLES_API_SOURCE = "linx_purchase_payables_api"
LINX_PURCHASE_PAYABLES_API_METHOD = "LinxFaturas"
LINX_PURCHASE_PAYABLES_API_TAG = "linx_purchase_payables_api"
LINX_PURCHASE_PAYABLES_API_MIN_ISSUE_DATE = date(2026, 3, 10)
LINX_PURCHASE_PAYABLES_API_FULL_LOAD_START = "2026-03-10 00:00:00"
LINX_PURCHASE_PAYABLES_API_PAGE_LIMIT = 5000
LINX_PURCHASE_PAYABLES_API_TIMEOUT_SECONDS = 90.0
LINX_WS_USERNAME = "linx_export"
LINX_WS_PASSWORD = "linx_export"
CURRENT_YEAR_PURCHASE_PLANNING_CACHE_TTL_SECONDS = 86400
HISTORICAL_PURCHASE_PLANNING_CACHE_TTL_SECONDS = 604800
MAX_PURCHASE_PLANNING_CACHE_ITEMS = 24
SEASON_LABELS = {
    "summer": "Verao",
    "winter": "Inverno",
}
SEASON_PHASE_LABELS = {
    "main": "Principal",
    "high": "Alto",
}
PURCHASE_RETURN_STATUS_FLOW = (
    "request_open",
    "factory_pending",
    "send",
    "sent_waiting_analysis",
    "refund_approved",
    "refunded",
)
PURCHASE_RETURN_STATUS_LABELS = {
    "request_open": "Abrir solicitacao",
    "factory_pending": "Aguardando fabrica",
    "send": "Enviar",
    "sent_waiting_analysis": "Enviado/Aguardando Analise",
    "refund_approved": "Reembolso aprovado",
    "refunded": "Reembolsado",
}
PURCHASE_RETURN_STATUS_ALIASES = {
    "requestopen": "request_open",
    "abrirsolicitacao": "request_open",
    "factorypending": "factory_pending",
    "aguardandofabrica": "factory_pending",
    "send": "send",
    "envia": "send",
    "sentwaitinganalysis": "sent_waiting_analysis",
    "enviadoaguardandoanalise": "sent_waiting_analysis",
    "refundapproved": "refund_approved",
    "reembolsoaprovado": "refund_approved",
    "refunded": "refunded",
    "reembolsado": "refunded",
}
PURCHASE_RETURN_APPROVAL_STATUS = "refund_approved"


@dataclass(slots=True)
class PurchasePlanningFilters:
    year: int | None = None
    brand_id: str | None = None
    supplier_id: str | None = None
    collection_id: str | None = None
    status: str | None = None


@dataclass(slots=True)
class PurchasePlanningOverviewCacheEntry:
    expires_at: float
    payload: PurchasePlanningOverview


_purchase_planning_overview_cache: dict[tuple[str, str, str, str, str, str, str], PurchasePlanningOverviewCacheEntry] = {}
_purchase_planning_overview_cache_lock = Lock()


@dataclass(slots=True)
class LinxApiPurchasePayableRow:
    linx_code: int
    issue_date: date | None
    payable_code: str | None
    company_code: str | None
    due_date: date | None
    installment_label: str | None
    installment_number: int | None
    installments_total: int | None
    original_amount: Decimal
    amount_with_charges: Decimal
    supplier_name: str
    supplier_code: str | None
    document_number: str | None
    document_series: str | None
    status: str
    paid_amount: Decimal
    settled_date: date | None
    canceled: bool
    excluded: bool
    row_timestamp: int | None
    observation: str | None


def _money(value: Decimal | int | float | None) -> Decimal:
    raw = Decimal(value or 0)
    return raw.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _today() -> date:
    return date.today()


def _purchase_planning_cache_ttl_seconds(filters: PurchasePlanningFilters, *, today: date | None = None) -> int:
    reference_day = today or date.today()
    if filters.year is None or filters.year == reference_day.year:
        return CURRENT_YEAR_PURCHASE_PLANNING_CACHE_TTL_SECONDS
    return HISTORICAL_PURCHASE_PLANNING_CACHE_TTL_SECONDS


def _purchase_planning_cache_key(
    company_id: str,
    filters: PurchasePlanningFilters,
    mode: str,
) -> tuple[str, str, str, str, str, str, str]:
    normalized_mode = normalize_label(mode) or "summary"
    return (
        company_id,
        normalized_mode,
        str(filters.year or ""),
        filters.brand_id or "",
        filters.supplier_id or "",
        filters.collection_id or "",
        filters.status or "",
    )


def _prune_purchase_planning_overview_cache(now: float) -> None:
    expired_keys = [key for key, entry in _purchase_planning_overview_cache.items() if entry.expires_at <= now]
    for key in expired_keys:
        _purchase_planning_overview_cache.pop(key, None)
    if len(_purchase_planning_overview_cache) <= MAX_PURCHASE_PLANNING_CACHE_ITEMS:
        return
    keys_by_expiry = sorted(_purchase_planning_overview_cache.items(), key=lambda item: item[1].expires_at)
    for key, _entry in keys_by_expiry[: len(_purchase_planning_overview_cache) - MAX_PURCHASE_PLANNING_CACHE_ITEMS]:
        _purchase_planning_overview_cache.pop(key, None)


def clear_purchase_planning_overview_cache(company_id: str | None = None) -> None:
    with _purchase_planning_overview_cache_lock:
        if company_id is None:
            _purchase_planning_overview_cache.clear()
            return
        keys_to_remove = [key for key in _purchase_planning_overview_cache if key[0] == company_id]
        for key in keys_to_remove:
            _purchase_planning_overview_cache.pop(key, None)


def _resolve_effective_purchase_planning_filters(
    db: Session,
    company_id: str,
    filters: PurchasePlanningFilters,
) -> PurchasePlanningFilters:
    effective_year = filters.year
    if filters.collection_id:
        collection = db.get(CollectionSeason, filters.collection_id)
        if collection and collection.company_id == company_id and collection.season_year:
            effective_year = collection.season_year
    return PurchasePlanningFilters(
        year=effective_year,
        brand_id=filters.brand_id,
        supplier_id=filters.supplier_id,
        collection_id=filters.collection_id,
        status=filters.status,
    )

def _normalize_reporting_brand_name(name: str | None) -> str:
    norm = normalize_label(name or "Desconhecida")
    if "viviane" in norm:
        return "viviane"
    if "tricot" in norm:
        return "tricot"
    if "veste" in norm:
        return "veste"
    return norm


def _normalize_purchase_return_status(value: str | None) -> str:
    normalized_value = normalize_label(value or "")
    resolved = PURCHASE_RETURN_STATUS_ALIASES.get(normalized_value)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Status da devolucao invalido")
    return resolved


def _purchase_return_status_label(status_value: str) -> str:
    return PURCHASE_RETURN_STATUS_LABELS.get(status_value, status_value)


def _purchase_return_status_index(status_value: str) -> int:
    return PURCHASE_RETURN_STATUS_FLOW.index(status_value)


def _validate_purchase_return_status_transition(current_status: str | None, next_status: str) -> str:
    normalized_next_status = _normalize_purchase_return_status(next_status)
    return normalized_next_status


def _normalize_season_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_label(value)
    aliases = {
        "summer": "summer",
        "verao": "summer",
        "winter": "winter",
        "inverno": "winter",
    }
    return aliases.get(normalized)


def _normalize_season_phase(value: str | None) -> str:
    if not value:
        return "main"
    normalized = normalize_label(value)
    aliases = {
        "main": "main",
        "principal": "main",
        "base": "main",
        "high": "high",
        "alto": "high",
    }
    return aliases.get(normalized, "main")


def _season_label(season_type: str | None, season_year: int | None) -> str | None:
    normalized_type = _normalize_season_type(season_type)
    if not normalized_type or not season_year:
        return None
    return f"{SEASON_LABELS[normalized_type]} {season_year}"


def _season_phase_label(season_phase: str | None) -> str:
    return SEASON_PHASE_LABELS.get(_normalize_season_phase(season_phase), "Principal")


def _infer_collection_structure(
    name: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[int | None, str | None, str]:
    normalized_name = normalize_label(name or "")
    season_type = None
    if "inverno" in normalized_name:
        season_type = "winter"
    elif "verao" in normalized_name:
        season_type = "summer"

    season_year = start_date.year if start_date else (end_date.year if end_date else None)
    season_phase = "high" if "alto" in normalized_name else "main"
    return season_year, season_type, season_phase


def _collection_name(collection: CollectionSeason | None) -> str | None:
    if collection is None:
        return None
    return _season_label(collection.season_type, collection.season_year) or collection.name


def _normalize_collection_lookup_key(value: str | None) -> str:
    normalized = normalize_label(value or "")
    if normalized.startswith("1"):
        normalized = normalized[1:].lstrip("-").strip()
    return normalized


def _resolve_reporting_collection_by_date(
    collections: list[CollectionSeason],
    reference_date: date | datetime | None,
) -> CollectionSeason | None:
    if reference_date is None:
        return None
    target_date = reference_date.date() if isinstance(reference_date, datetime) else reference_date
    for collection in collections:
        if collection.start_date <= target_date <= collection.end_date:
            return collection
    return None


def _is_past_collection(collection: CollectionSeason | None, *, today: date) -> bool:
    if collection is None:
        return False
    return collection.end_date < today


def _season_window(year: int, season_type: str) -> tuple[date, date]:
    normalized_type = _normalize_season_type(season_type)
    if normalized_type == "winter":
        return date(year, 1, 1), date(year, 7, 1)
    return date(year, 7, 1), date(year, 12, 31)


def _digits_only(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    return digits or None


def _strip_supplier_code_prefix(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"^\s*\d+\s+(?=\S)", "", value).strip()


def _canonical_supplier_name(value: str | None) -> str:
    stripped = _strip_supplier_code_prefix(value)
    return stripped or (value or "").strip()


def _supplier_lookup_keys(value: str | None) -> set[str]:
    candidates = {normalize_label(value or "")}
    stripped = _strip_supplier_code_prefix(value)
    if stripped:
        candidates.add(normalize_label(stripped))
    return {candidate for candidate in candidates if candidate}


def _build_supplier_brand_name_lookup(db: Session, company_id: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    rows = db.execute(
        select(Supplier.name, PurchaseBrand.name)
        .select_from(PurchaseBrandSupplier)
        .join(Supplier, Supplier.id == PurchaseBrandSupplier.supplier_id)
        .join(PurchaseBrand, PurchaseBrand.id == PurchaseBrandSupplier.brand_id)
        .where(PurchaseBrandSupplier.company_id == company_id)
        .order_by(PurchaseBrand.created_at.asc(), PurchaseBrandSupplier.created_at.asc())
    ).all()
    for supplier_name, brand_name in rows:
        for lookup_key in _supplier_lookup_keys(supplier_name):
            lookup.setdefault(lookup_key, str(brand_name))
    return lookup


def _normalize_linx_purchase_status(value: str | None) -> str:
    normalized = normalize_label(value or "")
    if not normalized:
        return "Em aberto"
    if "aberto" in normalized:
        return "Em aberto"
    if "baix" in normalized or "liquid" in normalized or "pag" in normalized:
        return "Baixado"
    return value.strip() if value else "Em aberto"


def _linx_purchase_payable_is_open(row: ParsedPurchasePayableRow) -> bool:
    return "aberto" in normalize_label(row.status)


def _linx_purchase_payable_source_reference(row: ParsedPurchasePayableRow) -> str:
    payload = "|".join(
        [
            row.payable_code or "",
            row.company_code or "",
            row.document_number or "",
            row.document_series or "",
            row.installment_label or "",
            row.due_date.isoformat() if row.due_date else "",
            f"{_money(row.amount_with_charges):.2f}",
            normalize_label(row.supplier_name),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:40]


def _linx_purchase_invoice_group_key(row: ParsedPurchasePayableRow) -> tuple[str, str, str]:
    return (
        normalize_label(row.supplier_name),
        (row.document_number or "").strip(),
        (row.document_series or "").strip(),
    )


def _month_key(value: date | None) -> str:
    if value is None:
        return "Sem vencimento"
    return f"{value.year:04d}-{value.month:02d}"


def _local_tag(value: str) -> str:
    return value.split("}", 1)[-1]


def _find_text(root: ElementTree.Element | None, *names: str) -> str | None:
    if root is None:
        return None
    wanted = set(names)
    for node in root.iter():
        if _local_tag(node.tag) in wanted and node.text:
            text = node.text.strip()
            if text:
                return text
    return None


def _findall(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local_tag(node.tag) == name]


def _extract_first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def _extract_last_money_value(text: str) -> str | None:
    matches = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", text)
    return matches[-1] if matches else None


def _extract_total_amount_from_text(raw_text: str) -> Decimal:
    direct_match = (
        _extract_first(r"V\.?\s*Total da Nota\s+([0-9\.\,]+)", raw_text)
        or _extract_first(r"V\.?\s*Total da Nota\s*\n[^\n]*\n([0-9\.\,]+)", raw_text)
    )
    if direct_match:
        return parse_decimal_pt_br(direct_match)

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not re.search(r"V\.?\s*Total da Nota", line, re.IGNORECASE):
            continue
        for candidate in lines[index : min(index + 4, len(lines))]:
            amount = _extract_last_money_value(candidate)
            if amount:
                return parse_decimal_pt_br(amount)
    return Decimal("0.00")


def _extract_supplier_name(raw_text: str) -> str | None:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        normalized = normalize_label(line)
        if "destinat" in normalized and "remetente" in normalized:
            if index + 1 < len(lines):
                return lines[index + 1]
    match = re.search(
        r"Destinat.{0,5}rio/Remetente\s+([^\n\r]+)",
        raw_text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _extract_installments_from_text(raw_text: str) -> list[PurchaseInstallmentDraft]:
    installments: list[PurchaseInstallmentDraft] = []
    pattern = re.compile(
        r"(?P<label>\d{3,})\s+(?P<due>\d{2}/\d{2}/\d{2,4})\s+(?P<amount>\d{1,3}(?:\.\d{3})*,\d{2})"
    )
    for index, match in enumerate(pattern.finditer(raw_text), start=1):
        due_date = parse_date_br(match.group("due"))
        amount = parse_decimal_pt_br(match.group("amount"))
        installments.append(
            PurchaseInstallmentDraft(
                installment_number=index,
                installment_label=match.group("label"),
                due_date=due_date,
                amount=amount,
            )
        )
    return installments


def _sum_installment_amounts(installments: list[PurchaseInstallmentDraft]) -> Decimal:
    return _money(sum((installment.amount for installment in installments), Decimal("0.00")))


def _build_installments_from_term(
    payment_term: str | None,
    total_amount: Decimal,
    base_date: date | None,
) -> list[PurchaseInstallmentDraft]:
    if not payment_term or base_date is None:
        return []
    normalized = normalize_label(payment_term)
    day_match = re.search(r"(\d+)\s*dias?", normalized)
    if day_match:
        due_date = base_date + timedelta(days=max(int(day_match.group(1)), 0))
        return [
            PurchaseInstallmentDraft(
                installment_number=1,
                installment_label=payment_term,
                due_date=due_date,
                amount=_money(total_amount),
            )
        ]

    count_match = re.search(r"(\d+)\s*[xX]", payment_term)
    if not count_match:
        return []

    count = min(max(int(count_match.group(1)), 1), 10)
    amount = _money(total_amount / count)
    installments: list[PurchaseInstallmentDraft] = []
    remaining = _money(total_amount)
    for index in range(1, count + 1):
        due_date = date(base_date.year, base_date.month, min(base_date.day, 28))
        month = due_date.month - 1 + index
        year = due_date.year + month // 12
        month = month % 12 + 1
        due_date = date(year, month, min(due_date.day, 28))
        installment_amount = amount if index < count else remaining
        installments.append(
            PurchaseInstallmentDraft(
                installment_number=index,
                installment_label=f"{index}/{count}",
                due_date=due_date,
                amount=installment_amount,
            )
        )
        remaining = _money(remaining - installment_amount)
    return installments


def parse_purchase_invoice_text(raw_text: str) -> PurchaseInvoiceDraft:
    normalized_text = raw_text.replace("\r", "\n")
    supplier_name = _canonical_supplier_name(_extract_supplier_name(normalized_text)) or "Fornecedor nao identificado"
    invoice_number = _extract_first(r"Nota Fiscal:\s*([0-9]+)", normalized_text)
    series = _extract_first(r"S.{0,2}rie:\s*([0-9A-Za-z]+)", normalized_text)
    issue_date_raw = (_extract_first(r"Data de emiss.{0,2}o:\s*([0-9/]+)", normalized_text) or "").split("-", 1)[0].strip()
    entry_date_raw = (_extract_first(r"Data de entrada/sa.{0,2}da:\s*([0-9/]+)", normalized_text) or "").split("-", 1)[0].strip()
    payment_description = _extract_first(r"Forma de Pagamento:\s*([^\n\r]+)", normalized_text)
    nfe_key = _digits_only(_extract_first(r"Chave NF-e:\s*([0-9 ]+)", normalized_text))

    issue_date = parse_date_br(issue_date_raw) if issue_date_raw else None
    entry_date = parse_date_br(entry_date_raw) if entry_date_raw else None

    total_amount = _extract_total_amount_from_text(normalized_text)
    installments = _extract_installments_from_text(normalized_text)
    if not installments:
        installments = _build_installments_from_term(payment_description, total_amount, entry_date or issue_date)
    elif total_amount <= 0:
        total_amount = _sum_installment_amounts(installments)

    return PurchaseInvoiceDraft(
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        series=series,
        nfe_key=nfe_key,
        issue_date=issue_date,
        entry_date=entry_date,
        total_amount=total_amount,
        payment_description=payment_description,
        payment_term=payment_description,
        raw_text=raw_text,
        installments=installments,
    )


def parse_purchase_invoice_xml(content: bytes) -> PurchaseInvoiceDraft:
    root = ElementTree.fromstring(content)
    emit = next((node for node in root.iter() if _local_tag(node.tag) == "emit"), None)
    supplier_name = _canonical_supplier_name(_find_text(emit, "xNome")) or "Fornecedor nao identificado"
    invoice_number = _find_text(root, "nNF")
    series = _find_text(root, "serie")
    issue_date_raw = _find_text(root, "dhEmi", "dEmi")
    entry_date_raw = _find_text(root, "dhSaiEnt", "dSaiEnt")
    issue_date = None
    entry_date = None
    if issue_date_raw:
        issue_date = datetime.fromisoformat(issue_date_raw.replace("Z", "+00:00")).date() if "T" in issue_date_raw else parse_date_br(issue_date_raw)
    if entry_date_raw:
        entry_date = datetime.fromisoformat(entry_date_raw.replace("Z", "+00:00")).date() if "T" in entry_date_raw else parse_date_br(entry_date_raw)
    payment_description = _find_text(root, "xPag")
    total_amount = Decimal((_find_text(root, "vNF") or "0").replace(",", "."))
    inf_nfe = next((node for node in root.iter() if _local_tag(node.tag) == "infNFe"), None)
    nfe_key = _digits_only(inf_nfe.attrib.get("Id", "").replace("NFe", "")) if inf_nfe is not None else None

    installments: list[PurchaseInstallmentDraft] = []
    for index, dup in enumerate(_findall(root, "dup"), start=1):
        installments.append(
            PurchaseInstallmentDraft(
                installment_number=index,
                installment_label=_find_text(dup, "nDup"),
                due_date=parse_date_br(_find_text(dup, "dVenc") or ""),
                amount=Decimal((_find_text(dup, "vDup") or "0").replace(",", ".")),
            )
        )
    if not installments:
        installments = _build_installments_from_term(payment_description, total_amount, entry_date or issue_date)
    elif total_amount <= 0:
        total_amount = _sum_installment_amounts(installments)

    return PurchaseInvoiceDraft(
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        series=series,
        nfe_key=nfe_key,
        issue_date=issue_date,
        entry_date=entry_date,
        total_amount=_money(total_amount),
        payment_description=payment_description,
        payment_term=payment_description,
        raw_xml=content.decode("utf-8", errors="ignore"),
        installments=installments,
    )


def _validate_supplier(db: Session, company_id: str, supplier_id: str | None) -> Supplier | None:
    if not supplier_id:
        return None
    supplier = db.get(Supplier, supplier_id)
    if not supplier or supplier.company_id != company_id:
        raise HTTPException(status_code=404, detail="Fornecedor nao encontrado")
    return supplier


def _validate_collection(db: Session, company_id: str, collection_id: str | None) -> CollectionSeason | None:
    if not collection_id:
        return None
    collection = db.get(CollectionSeason, collection_id)
    if not collection or collection.company_id != company_id:
        raise HTTPException(status_code=404, detail="Colecao nao encontrada")
    return collection


def _validate_brand(db: Session, company_id: str, brand_id: str | None) -> PurchaseBrand | None:
    if not brand_id:
        return None
    brand = db.get(PurchaseBrand, brand_id)
    if not brand or brand.company_id != company_id:
        raise HTTPException(status_code=404, detail="Marca nao encontrada")
    return brand


def _resolve_collection(
    db: Session,
    company_id: str,
    collection_id: str | None,
    issue_date: date | None,
    ) -> CollectionSeason | None:
    explicit = _validate_collection(db, company_id, collection_id)
    if explicit:
        return explicit
    if issue_date is None:
        return None
    return db.scalar(
        select(CollectionSeason)
        .where(
            CollectionSeason.company_id == company_id,
            CollectionSeason.is_active.is_(True),
            CollectionSeason.start_date <= issue_date,
            CollectionSeason.end_date >= issue_date,
        )
        .order_by(CollectionSeason.start_date.desc())
    )


def _brand_for_supplier(db: Session, company_id: str, supplier_id: str | None) -> PurchaseBrand | None:
    if not supplier_id:
        return None
    link = db.scalar(
        select(PurchaseBrandSupplier)
        .join(PurchaseBrand, PurchaseBrand.id == PurchaseBrandSupplier.brand_id)
        .where(
            PurchaseBrandSupplier.company_id == company_id,
            PurchaseBrandSupplier.supplier_id == supplier_id,
            PurchaseBrand.is_active.is_(True),
        )
        .order_by(PurchaseBrand.name.asc())
    )
    if not link:
        return None
    return db.get(PurchaseBrand, link.brand_id)


def _brand_supplier_ids(db: Session, company_id: str, brand_id: str | None) -> list[str]:
    if not brand_id:
        return []
    return list(
        db.scalars(
            select(PurchaseBrandSupplier.supplier_id).where(
                PurchaseBrandSupplier.company_id == company_id,
                PurchaseBrandSupplier.brand_id == brand_id,
            )
        )
    )


def _normalize_supplier_ids(supplier_id: str | None, supplier_ids: list[str] | None) -> list[str]:
    unique_supplier_ids: list[str] = []
    seen: set[str] = set()
    for value in [supplier_id, *(supplier_ids or [])]:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_supplier_ids.append(value)
    return unique_supplier_ids


def _plan_suppliers(plan: PurchasePlan) -> list[Supplier]:
    linked_suppliers: list[Supplier] = []
    seen: set[str] = set()
    for link in getattr(plan, "plan_suppliers", []) or []:
        supplier = link.supplier
        if not supplier or supplier.id in seen:
            continue
        seen.add(supplier.id)
        linked_suppliers.append(supplier)
    if plan.supplier and plan.supplier.id not in seen:
        linked_suppliers.insert(0, plan.supplier)
    return linked_suppliers


def _plan_supplier_ids(plan: PurchasePlan) -> list[str]:
    return [supplier.id for supplier in _plan_suppliers(plan)]


def _filter_cashflow_plans(
    db: Session,
    company_id: str,
    plans: list[PurchasePlan],
) -> list[PurchasePlan]:
    if not plans:
        return []

    brand_linked_supplier_ids = set(
        db.scalars(
            select(PurchaseBrandSupplier.supplier_id).where(
                PurchaseBrandSupplier.company_id == company_id,
            )
        )
    )

    filtered: list[PurchasePlan] = []
    today = _today()
    for plan in plans:
        if plan.status == "imported":
            continue
        if plan.collection is None or _is_past_collection(plan.collection, today=today):
            continue
        supplier_ids = _plan_supplier_ids(plan)
        if not plan.brand_id and any(supplier_id in brand_linked_supplier_ids for supplier_id in supplier_ids):
            continue
        filtered.append(plan)
    return filtered


def _find_matching_supplier(
    db: Session,
    company_id: str,
    *,
    supplier_name: str,
    supplier_document: str | None,
    exclude_supplier_id: str | None = None,
) -> Supplier | None:
    document_number = _digits_only(supplier_document)
    if document_number:
        supplier = db.scalar(
            select(Supplier).where(
                Supplier.company_id == company_id,
                Supplier.document_number == document_number,
            )
        )
        if supplier and supplier.id != exclude_supplier_id:
            return supplier

    wanted_keys = _supplier_lookup_keys(supplier_name)
    if not wanted_keys:
        return None

    suppliers = list(
        db.scalars(
            select(Supplier).where(
                Supplier.company_id == company_id,
            )
        )
    )
    for supplier in suppliers:
        if exclude_supplier_id and supplier.id == exclude_supplier_id:
            continue
        if wanted_keys & _supplier_lookup_keys(supplier.name):
            return supplier
    return None


def _find_matching_purchase_plan(
    db: Session,
    company_id: str,
    *,
    supplier_id: str,
    collection_id: str | None,
    season_phase: str | None = None,
    issue_date: date | None,
    exclude_plan_id: str | None = None,
) -> PurchasePlan | None:
    plans = (
        db.execute(
            select(PurchasePlan)
            .where(
                PurchasePlan.company_id == company_id,
                or_(
                    PurchasePlan.supplier_id == supplier_id,
                    PurchasePlan.plan_suppliers.any(PurchasePlanSupplier.supplier_id == supplier_id),
                ),
            )
            .options(
                joinedload(PurchasePlan.collection),
                joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
                joinedload(PurchasePlan.supplier),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    candidates: list[PurchasePlan] = []
    for plan in plans:
        if exclude_plan_id and plan.id == exclude_plan_id:
            continue
        if collection_id and plan.collection_id == collection_id:
            candidates.append(plan)
            continue
        if issue_date and plan.collection and plan.collection.start_date <= issue_date <= plan.collection.end_date:
            candidates.append(plan)

    if not candidates:
        return None

    candidates.sort(
        key=lambda plan: (
            plan.status == "imported",
            _normalize_season_phase(plan.season_phase) != _normalize_season_phase(season_phase),
            plan.collection_id != collection_id if collection_id else True,
            plan.order_date or date.max,
            plan.created_at,
        )
    )
    return candidates[0]


def _ensure_plan_suppliers_available(
    db: Session,
    company_id: str,
    supplier_ids: list[str],
    *,
    current_plan_id: str | None = None,
) -> None:
    return


def _sync_plan_suppliers(db: Session, company_id: str, plan: PurchasePlan, supplier_ids: list[str]) -> None:
    unique_supplier_ids = _normalize_supplier_ids(None, supplier_ids)
    for supplier_id in unique_supplier_ids:
        _validate_supplier(db, company_id, supplier_id)
    _ensure_plan_suppliers_available(db, company_id, unique_supplier_ids, current_plan_id=plan.id)

    existing_links = list(
        db.scalars(
            select(PurchasePlanSupplier).where(
                PurchasePlanSupplier.company_id == company_id,
                PurchasePlanSupplier.plan_id == plan.id,
            )
        )
    )
    existing_by_supplier = {link.supplier_id: link for link in existing_links}

    for supplier_id in unique_supplier_ids:
        if supplier_id in existing_by_supplier:
            continue
        db.add(
            PurchasePlanSupplier(
                company_id=company_id,
                plan_id=plan.id,
                supplier_id=supplier_id,
            )
        )

    for link in existing_links:
        if link.supplier_id not in unique_supplier_ids:
            db.delete(link)

    plan.supplier_id = unique_supplier_ids[0] if unique_supplier_ids else None


def _find_or_create_supplier(
    db: Session,
    company_id: str,
    *,
    supplier_id: str | None,
    supplier_name: str,
    supplier_document: str | None,
) -> Supplier:
    explicit = _validate_supplier(db, company_id, supplier_id)
    if explicit:
        return explicit

    document_number = _digits_only(supplier_document)
    supplier = _find_matching_supplier(
        db,
        company_id,
        supplier_name=supplier_name,
        supplier_document=document_number,
    )
    if supplier:
        if document_number and not supplier.document_number:
            supplier.document_number = document_number
        return supplier

    canonical_name = _canonical_supplier_name(supplier_name)
    supplier = Supplier(
        company_id=company_id,
        name=canonical_name,
        document_number=document_number,
        payment_basis="delivery",
        has_purchase_invoices=False,
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier


def _serialize_supplier(supplier: Supplier) -> SupplierRead:
    return SupplierRead.model_validate(supplier)


def _serialize_brand(db: Session, brand: PurchaseBrand) -> PurchaseBrandRead:
    links = list(
        db.scalars(
            select(PurchaseBrandSupplier)
            .where(
                PurchaseBrandSupplier.company_id == brand.company_id,
                PurchaseBrandSupplier.brand_id == brand.id,
            )
            .order_by(PurchaseBrandSupplier.created_at.asc())
        )
    )
    suppliers = []
    supplier_ids: list[str] = []
    for link in links:
        supplier = db.get(Supplier, link.supplier_id)
        if not supplier:
            continue
        supplier_ids.append(supplier.id)
        suppliers.append(_serialize_supplier(supplier))
    return PurchaseBrandRead(
        id=brand.id,
        name=brand.name,
        supplier_ids=supplier_ids,
        suppliers=suppliers,
        default_payment_term=brand.default_payment_term,
        notes=brand.notes,
        is_active=brand.is_active,
    )


def _serialize_collection(collection: CollectionSeason) -> CollectionSeasonRead:
    season_label = _season_label(collection.season_type, collection.season_year) or collection.name
    return CollectionSeasonRead(
        id=collection.id,
        name=season_label,
        season_year=collection.season_year or collection.start_date.year,
        season_type=_normalize_season_type(collection.season_type) or "summer",
        season_label=season_label,
        start_date=collection.start_date,
        end_date=collection.end_date,
        notes=collection.notes,
        is_active=collection.is_active,
    )


def _serialize_purchase_return(purchase_return: PurchaseReturn) -> PurchaseReturnRead:
    return PurchaseReturnRead(
        id=purchase_return.id,
        supplier_id=purchase_return.supplier_id,
        supplier_name=purchase_return.supplier.name if purchase_return.supplier else None,
        return_date=purchase_return.return_date,
        amount=_money(purchase_return.amount),
        invoice_number=purchase_return.invoice_number,
        status=_normalize_purchase_return_status(purchase_return.status),
        notes=purchase_return.notes,
        refund_entry_id=purchase_return.refund_entry_id,
    )


def _purchase_return_refund_category_id(db: Session, company_id: str) -> str:
    return ensure_category_catalog(db, company_id)["Devolucoes de Compra"].id


def _purchase_return_refund_title(purchase_return: PurchaseReturn, supplier_name: str | None) -> str:
    base_title = f"Reembolso devolucao compra - {supplier_name or 'Fornecedor'}"
    if purchase_return.invoice_number:
        return f"{base_title} NF {purchase_return.invoice_number}"
    return base_title


def _sync_purchase_return_refund_entry(
    db: Session,
    company: Company,
    purchase_return: PurchaseReturn,
    *,
    supplier_name: str | None,
) -> None:
    if not purchase_return.refund_entry_id:
        return
    entry = db.get(FinancialEntry, purchase_return.refund_entry_id)
    if entry is None or entry.company_id != company.id or entry.is_deleted:
        purchase_return.refund_entry_id = None
        return
    if normalize_open_alias(entry.status) != OPEN_STATUS:
        return
    entry.category_id = _purchase_return_refund_category_id(db, company.id)
    entry.supplier_id = purchase_return.supplier_id
    entry.entry_type = "income"
    entry.title = _purchase_return_refund_title(purchase_return, supplier_name)
    entry.description = "Recebivel gerado automaticamente ao aprovar devolucao de compra"
    entry.notes = purchase_return.notes
    entry.counterparty_name = supplier_name
    entry.document_number = purchase_return.invoice_number
    entry.principal_amount = _money(purchase_return.amount)
    entry.total_amount = _money(purchase_return.amount)
    entry.source_system = "purchase_return_workflow"
    entry.source_reference = purchase_return.id


def _ensure_purchase_return_refund_entry(
    db: Session,
    company: Company,
    purchase_return: PurchaseReturn,
    actor_user: User,
    *,
    supplier_name: str | None,
) -> None:
    from app.services.finance_ops import create_entry

    _sync_purchase_return_refund_entry(
        db,
        company,
        purchase_return,
        supplier_name=supplier_name,
    )
    if purchase_return.refund_entry_id:
        return

    today = _today()
    entry = create_entry(
        db,
        company,
        FinancialEntryCreate(
            category_id=_purchase_return_refund_category_id(db, company.id),
            supplier_id=purchase_return.supplier_id,
            entry_type="income",
            status=OPEN_STATUS,
            title=_purchase_return_refund_title(purchase_return, supplier_name),
            description="Recebivel gerado automaticamente ao aprovar devolucao de compra",
            notes=purchase_return.notes,
            counterparty_name=supplier_name,
            document_number=purchase_return.invoice_number,
            issue_date=today,
            competence_date=today,
            due_date=today,
            principal_amount=_money(purchase_return.amount),
            total_amount=_money(purchase_return.amount),
            source_system="purchase_return_workflow",
            source_reference=purchase_return.id,
        ),
        actor_user,
    )
    purchase_return.refund_entry_id = entry.id


def _remove_purchase_return_refund_entry(
    db: Session,
    company: Company,
    purchase_return: PurchaseReturn,
    actor_user: User,
) -> None:
    from app.services.finance_ops import delete_entry

    if not purchase_return.refund_entry_id:
        return
    refund_entry = db.get(FinancialEntry, purchase_return.refund_entry_id)
    if refund_entry is None or refund_entry.company_id != company.id or refund_entry.is_deleted:
        purchase_return.refund_entry_id = None
        return
    if normalize_open_alias(refund_entry.status) not in {OPEN_STATUS, "cancelled"} or Decimal(refund_entry.paid_amount or 0) > Decimal("0.00"):
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel voltar o status enquanto a fatura de reembolso ja possui movimentacao",
        )
    delete_entry(db, company, refund_entry.id, actor_user)
    purchase_return.refund_entry_id = None


def list_suppliers(db: Session, company: Company) -> list[SupplierRead]:
    suppliers = list(
        db.scalars(
            select(Supplier)
            .where(Supplier.company_id == company.id)
            .order_by(Supplier.is_active.desc(), Supplier.name.asc())
        )
    )
    return [_serialize_supplier(item) for item in suppliers]


def list_purchase_invoice_suppliers(db: Session, company: Company) -> list[SupplierRead]:
    suppliers = list(
        db.scalars(
            select(Supplier)
            .where(
                Supplier.company_id == company.id,
                Supplier.has_purchase_invoices.is_(True),
                Supplier.ignore_in_purchase_planning.is_(False),
            )
            .order_by(Supplier.is_active.desc(), Supplier.name.asc())
        )
    )
    return [_serialize_supplier(item) for item in suppliers]


def create_supplier(db: Session, company: Company, payload: SupplierCreate, actor_user: User) -> SupplierRead:
    canonical_name = _canonical_supplier_name(payload.name)
    existing_supplier = _find_matching_supplier(
        db,
        company.id,
        supplier_name=canonical_name,
        supplier_document=None,
    )
    if existing_supplier:
        raise HTTPException(
            status_code=409,
            detail=f'Fornecedor "{existing_supplier.name}" ja cadastrado.',
        )
    supplier_payload = payload.model_dump()
    supplier_payload["name"] = canonical_name
    supplier = Supplier(company_id=company.id, **supplier_payload)
    supplier.document_number = None
    supplier.payment_basis = "delivery"
    db.add(supplier)
    db.flush()
    write_audit_log(
        db,
        action="create_supplier",
        entity_name="supplier",
        entity_id=supplier.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={"name": supplier.name},
    )
    return _serialize_supplier(supplier)


def update_supplier(db: Session, company: Company, supplier_id: str, payload: SupplierUpdate, actor_user: User) -> SupplierRead:
    supplier = _validate_supplier(db, company.id, supplier_id)
    assert supplier is not None
    canonical_name = _canonical_supplier_name(payload.name)
    existing_supplier = _find_matching_supplier(
        db,
        company.id,
        supplier_name=canonical_name,
        supplier_document=None,
        exclude_supplier_id=supplier.id,
    )
    if existing_supplier:
        raise HTTPException(
            status_code=409,
            detail=f'Fornecedor "{existing_supplier.name}" ja cadastrado.',
        )
    before_state = {
        "name": supplier.name,
        "payment_term": supplier.default_payment_term,
    }
    payload_data = payload.model_dump(exclude_unset=True)
    payload_data["name"] = canonical_name
    for field_name, value in payload_data.items():
        setattr(supplier, field_name, value)
    supplier.document_number = None
    supplier.payment_basis = "delivery"
    db.flush()
    write_audit_log(
        db,
        action="update_supplier",
        entity_name="supplier",
        entity_id=supplier.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={
            "name": supplier.name,
            "payment_term": supplier.default_payment_term,
        },
    )
    return _serialize_supplier(supplier)


def delete_supplier(db: Session, company: Company, supplier_id: str, actor_user: User) -> None:
    supplier = _validate_supplier(db, company.id, supplier_id)
    assert supplier is not None

    linked_brand = db.scalar(
        select(func.count(PurchaseBrandSupplier.id)).where(
            PurchaseBrandSupplier.company_id == company.id,
            PurchaseBrandSupplier.supplier_id == supplier.id,
        )
    ) or 0
    linked_plan = db.scalar(
        select(func.count(PurchasePlan.id)).where(
            PurchasePlan.company_id == company.id,
            PurchasePlan.supplier_id == supplier.id,
        )
    ) or 0
    linked_plan_links = db.scalar(
        select(func.count(PurchasePlanSupplier.id)).where(
            PurchasePlanSupplier.company_id == company.id,
            PurchasePlanSupplier.supplier_id == supplier.id,
        )
    ) or 0
    linked_invoice = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == company.id,
            PurchaseInvoice.supplier_id == supplier.id,
        )
    ) or 0
    linked_delivery = db.scalar(
        select(func.count(PurchaseDelivery.id)).where(
            PurchaseDelivery.company_id == company.id,
            PurchaseDelivery.supplier_id == supplier.id,
        )
    ) or 0
    linked_return = db.scalar(
        select(func.count(PurchaseReturn.id)).where(
            PurchaseReturn.company_id == company.id,
            PurchaseReturn.supplier_id == supplier.id,
        )
    ) or 0
    linked_entry = db.scalar(
        select(func.count(FinancialEntry.id)).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.supplier_id == supplier.id,
            FinancialEntry.is_deleted.is_(False),
        )
    ) or 0
    if linked_brand or linked_plan or linked_plan_links or linked_invoice or linked_delivery or linked_return or linked_entry:
        raise HTTPException(
            status_code=409,
            detail="Fornecedor ja possui vinculos no planejamento ou financeiro. Inative em vez de excluir.",
        )

    before_state = _serialize_supplier(supplier).model_dump()
    db.delete(supplier)
    write_audit_log(
        db,
        action="delete_supplier",
        entity_name="supplier",
        entity_id=supplier.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
    )


def list_brands(db: Session, company: Company) -> list[PurchaseBrandRead]:
    brands = list(
        db.scalars(
            select(PurchaseBrand)
            .where(PurchaseBrand.company_id == company.id)
            .order_by(PurchaseBrand.is_active.desc(), PurchaseBrand.name.asc())
        )
    )
    return [_serialize_brand(db, brand) for brand in brands]


def _sync_brand_suppliers(db: Session, company_id: str, brand_id: str, supplier_ids: list[str]) -> None:
    unique_supplier_ids: list[str] = []
    seen: set[str] = set()
    for supplier_id in supplier_ids:
        if not supplier_id or supplier_id in seen:
            continue
        _validate_supplier(db, company_id, supplier_id)
        seen.add(supplier_id)
        unique_supplier_ids.append(supplier_id)

    existing_links = list(
        db.scalars(
            select(PurchaseBrandSupplier).where(
                PurchaseBrandSupplier.company_id == company_id,
                PurchaseBrandSupplier.brand_id == brand_id,
            )
        )
    )
    existing_by_supplier = {link.supplier_id: link for link in existing_links}

    for supplier_id in unique_supplier_ids:
        conflicting_link = db.scalar(
            select(PurchaseBrandSupplier).where(
                PurchaseBrandSupplier.company_id == company_id,
                PurchaseBrandSupplier.supplier_id == supplier_id,
                PurchaseBrandSupplier.brand_id != brand_id,
            )
        )
        if conflicting_link:
            conflicting_brand = db.get(PurchaseBrand, conflicting_link.brand_id)
            supplier = db.get(Supplier, supplier_id)
            raise HTTPException(
                status_code=409,
                detail=(
                    f'O fornecedor "{supplier.name if supplier else supplier_id}" ja esta vinculado '
                    f'a marca "{conflicting_brand.name if conflicting_brand else "outra marca"}".'
                ),
            )
        if supplier_id in existing_by_supplier:
            continue
        db.add(
            PurchaseBrandSupplier(
                company_id=company_id,
                brand_id=brand_id,
                supplier_id=supplier_id,
            )
        )

    for link in existing_links:
        if link.supplier_id not in seen:
            db.delete(link)


def create_brand(db: Session, company: Company, payload: PurchaseBrandCreate, actor_user: User) -> PurchaseBrandRead:
    brand = PurchaseBrand(
        company_id=company.id,
        name=payload.name,
        default_payment_term=payload.default_payment_term,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(brand)
    db.flush()
    _sync_brand_suppliers(db, company.id, brand.id, payload.supplier_ids)
    db.flush()
    write_audit_log(
        db,
        action="create_purchase_brand",
        entity_name="purchase_brand",
        entity_id=brand.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "name": brand.name,
            "supplier_ids": payload.supplier_ids,
            "default_payment_term": brand.default_payment_term,
        },
    )
    return _serialize_brand(db, brand)


def update_brand(
    db: Session,
    company: Company,
    brand_id: str,
    payload: PurchaseBrandUpdate,
    actor_user: User,
) -> PurchaseBrandRead:
    brand = _validate_brand(db, company.id, brand_id)
    assert brand is not None
    before_state = _serialize_brand(db, brand).model_dump()
    brand.name = payload.name
    brand.default_payment_term = payload.default_payment_term
    brand.notes = payload.notes
    brand.is_active = payload.is_active
    _sync_brand_suppliers(db, company.id, brand.id, payload.supplier_ids)
    db.flush()
    write_audit_log(
        db,
        action="update_purchase_brand",
        entity_name="purchase_brand",
        entity_id=brand.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_serialize_brand(db, brand).model_dump(),
    )
    return _serialize_brand(db, brand)


def delete_brand(
    db: Session,
    company: Company,
    brand_id: str,
    actor_user: User,
) -> None:
    brand = _validate_brand(db, company.id, brand_id)
    assert brand is not None

    linked_plans = db.scalar(
        select(func.count(PurchasePlan.id)).where(
            PurchasePlan.company_id == company.id,
            PurchasePlan.brand_id == brand.id,
        )
    ) or 0
    linked_invoices = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == company.id,
            PurchaseInvoice.brand_id == brand.id,
        )
    ) or 0
    linked_deliveries = db.scalar(
        select(func.count(PurchaseDelivery.id)).where(
            PurchaseDelivery.company_id == company.id,
            PurchaseDelivery.brand_id == brand.id,
        )
    ) or 0

    if linked_plans or linked_invoices or linked_deliveries:
        raise HTTPException(
            status_code=409,
            detail="Marca ja possui movimentacoes vinculadas. Inative a marca em vez de excluir.",
        )

    before_state = _serialize_brand(db, brand).model_dump()
    links = list(
        db.scalars(
            select(PurchaseBrandSupplier).where(
                PurchaseBrandSupplier.company_id == company.id,
                PurchaseBrandSupplier.brand_id == brand.id,
            )
        )
    )
    for link in links:
        db.delete(link)
    db.delete(brand)
    db.flush()
    write_audit_log(
        db,
        action="delete_purchase_brand",
        entity_name="purchase_brand",
        entity_id=brand_id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"deleted": True},
    )


def list_collections(db: Session, company: Company) -> list[CollectionSeasonRead]:
    collections = list(
        db.scalars(
            select(CollectionSeason)
            .where(CollectionSeason.company_id == company.id)
            .order_by(CollectionSeason.season_year.desc().nullslast(), CollectionSeason.start_date.desc(), CollectionSeason.name.asc())
        )
    )
    return [_serialize_collection(item) for item in collections]


def ensure_historical_purchase_collections(
    db: Session,
    company: Company,
    *,
    start_year: int = HISTORICAL_COLLECTION_START_YEAR,
    end_year: int | None = None,
) -> list[CollectionSeason]:
    target_end_year = end_year or _today().year
    collections_by_key = {
        (collection.season_year, _normalize_season_type(collection.season_type)): collection
        for collection in db.scalars(
            select(CollectionSeason).where(CollectionSeason.company_id == company.id)
        )
    }

    ensured_collections: list[CollectionSeason] = []
    for season_year in range(start_year, target_end_year + 1):
        for season_type in ("winter", "summer"):
            window_start, window_end = _season_window(season_year, season_type)
            collection = collections_by_key.get((season_year, season_type))
            if collection is None:
                collection = CollectionSeason(
                    company_id=company.id,
                    name=_season_label(season_type, season_year) or "Colecao",
                    season_year=season_year,
                    season_type=season_type,
                    start_date=window_start,
                    end_date=window_end,
                    notes=None,
                    is_active=True,
                )
                db.add(collection)
                db.flush()
                collections_by_key[(season_year, season_type)] = collection
            else:
                collection.name = _season_label(season_type, season_year) or collection.name
                collection.season_year = season_year
                collection.season_type = season_type
                collection.start_date = window_start
                collection.end_date = window_end
            ensured_collections.append(collection)

    db.flush()
    return ensured_collections


def assign_historical_purchase_collections(db: Session, company: Company) -> int:
    repaired_count = 0

    def resolve_by_reference(reference_date: date | None) -> CollectionSeason | None:
        return _resolve_collection(db, company.id, None, reference_date) if reference_date else None

    plans = db.execute(
        select(PurchasePlan).where(
            PurchasePlan.company_id == company.id,
            PurchasePlan.collection_id.is_(None),
        )
    ).scalars()
    for plan in plans:
        collection = resolve_by_reference(plan.order_date or plan.expected_delivery_date)
        if collection is None:
            continue
        plan.collection_id = collection.id
        plan.season_phase = "main"
        repaired_count += 1

    invoices = db.execute(
        select(PurchaseInvoice).where(
            PurchaseInvoice.company_id == company.id,
            PurchaseInvoice.collection_id.is_(None),
        )
    ).scalars()
    for invoice in invoices:
        collection = resolve_by_reference(invoice.issue_date or invoice.entry_date)
        if collection is None:
            continue
        invoice.collection_id = collection.id
        invoice.season_phase = "main"
        repaired_count += 1

    deliveries = db.execute(
        select(PurchaseDelivery).where(
            PurchaseDelivery.company_id == company.id,
            PurchaseDelivery.collection_id.is_(None),
        )
    ).scalars()
    for delivery in deliveries:
        collection = resolve_by_reference(delivery.delivery_date)
        if collection is None:
            continue
        delivery.collection_id = collection.id
        delivery.season_phase = "main"
        repaired_count += 1

    entries = db.execute(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.collection_id.is_(None),
            FinancialEntry.is_deleted.is_(False),
        ).options(
            joinedload(FinancialEntry.category),
            joinedload(FinancialEntry.purchase_invoice),
        )
    ).scalars()
    for entry in entries:
        if not _is_purchase_entry(entry):
            continue
        reference_date = entry.issue_date or entry.competence_date or entry.due_date
        collection = resolve_by_reference(reference_date)
        if collection is None:
            continue
        entry.collection_id = collection.id
        entry.season_phase = "main"
        repaired_count += 1

    if repaired_count:
        db.flush()
    return repaired_count


def _validate_collection_uniqueness(
    db: Session,
    company_id: str,
    *,
    season_year: int,
    season_type: str,
    current_collection_id: str | None = None,
) -> None:
    stmt = select(CollectionSeason).where(
        CollectionSeason.company_id == company_id,
        CollectionSeason.season_year == season_year,
        CollectionSeason.season_type == season_type,
    )
    if current_collection_id:
        stmt = stmt.where(CollectionSeason.id != current_collection_id)
    existing_collection = db.scalar(stmt)
    if existing_collection is not None:
        raise HTTPException(
            status_code=409,
            detail=f'A colecao "{_season_label(season_type, season_year) or existing_collection.name}" ja esta cadastrada.',
        )


def create_collection(db: Session, company: Company, payload: CollectionSeasonCreate, actor_user: User) -> CollectionSeasonRead:
    season_type = _normalize_season_type(payload.season_type)
    if season_type is None:
        raise HTTPException(status_code=422, detail="Colecao invalida")
    _validate_collection_uniqueness(
        db,
        company.id,
        season_year=payload.season_year,
        season_type=season_type,
    )
    collection_name = _season_label(season_type, payload.season_year)
    collection = CollectionSeason(
        company_id=company.id,
        name=collection_name or (payload.name or "Colecao"),
        season_year=payload.season_year,
        season_type=season_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(collection)
    db.flush()
    write_audit_log(
        db,
        action="create_collection",
        entity_name="collection_season",
        entity_id=collection.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "name": collection.name,
            "season_year": collection.season_year,
            "season_type": collection.season_type,
            "start_date": collection.start_date.isoformat(),
            "end_date": collection.end_date.isoformat(),
        },
    )
    return _serialize_collection(collection)


def update_collection(
    db: Session,
    company: Company,
    collection_id: str,
    payload: CollectionSeasonUpdate,
    actor_user: User,
) -> CollectionSeasonRead:
    collection = _validate_collection(db, company.id, collection_id)
    assert collection is not None
    season_type = _normalize_season_type(payload.season_type)
    if season_type is None:
        raise HTTPException(status_code=422, detail="Colecao invalida")
    _validate_collection_uniqueness(
        db,
        company.id,
        season_year=payload.season_year,
        season_type=season_type,
        current_collection_id=collection.id,
    )
    before_state = {
        "name": collection.name,
        "season_year": collection.season_year,
        "season_type": collection.season_type,
        "start_date": collection.start_date.isoformat(),
        "end_date": collection.end_date.isoformat(),
    }
    collection.name = _season_label(season_type, payload.season_year) or (payload.name or collection.name)
    collection.season_year = payload.season_year
    collection.season_type = season_type
    collection.start_date = payload.start_date
    collection.end_date = payload.end_date
    collection.notes = payload.notes
    collection.is_active = payload.is_active
    db.flush()
    write_audit_log(
        db,
        action="update_collection",
        entity_name="collection_season",
        entity_id=collection.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={
            "name": collection.name,
            "season_year": collection.season_year,
            "season_type": collection.season_type,
            "start_date": collection.start_date.isoformat(),
            "end_date": collection.end_date.isoformat(),
        },
    )
    return _serialize_collection(collection)


def delete_collection(
    db: Session,
    company: Company,
    collection_id: str,
    actor_user: User,
) -> None:
    collection = _validate_collection(db, company.id, collection_id)
    assert collection is not None

    linked_plans = db.scalar(
        select(func.count(PurchasePlan.id)).where(
            PurchasePlan.company_id == company.id,
            PurchasePlan.collection_id == collection.id,
        )
    ) or 0
    linked_invoices = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == company.id,
            PurchaseInvoice.collection_id == collection.id,
        )
    ) or 0
    linked_deliveries = db.scalar(
        select(func.count(PurchaseDelivery.id)).where(
            PurchaseDelivery.company_id == company.id,
            PurchaseDelivery.collection_id == collection.id,
        )
    ) or 0
    linked_entries = db.scalar(
        select(func.count(FinancialEntry.id)).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.collection_id == collection.id,
            FinancialEntry.is_deleted.is_(False),
        )
    ) or 0
    if linked_plans or linked_invoices or linked_deliveries or linked_entries:
        raise HTTPException(
            status_code=409,
            detail="Colecao ja possui vinculos no planejamento ou financeiro. Inative em vez de excluir.",
        )

    before_state = _serialize_collection(collection).model_dump()
    db.delete(collection)
    write_audit_log(
        db,
        action="delete_collection",
        entity_name="collection_season",
        entity_id=collection.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
    )


def list_purchase_returns(
    db: Session,
    company: Company,
    *,
    year: int | None = None,
    limit: int = 200,
) -> list[PurchaseReturnRead]:
    stmt = select(PurchaseReturn).where(PurchaseReturn.company_id == company.id)
    if year:
        stmt = stmt.where(
            PurchaseReturn.return_date >= date(year, 1, 1),
            PurchaseReturn.return_date <= date(year, 12, 31),
        )
    returns = (
        db.execute(
            stmt.order_by(PurchaseReturn.return_date.desc(), PurchaseReturn.created_at.desc())
            .limit(limit)
            .options(joinedload(PurchaseReturn.supplier))
        )
        .scalars()
        .all()
    )
    return [_serialize_purchase_return(item) for item in returns]


def create_purchase_return(
    db: Session,
    company: Company,
    payload: PurchaseReturnCreate,
    actor_user: User,
) -> PurchaseReturnRead:
    supplier = _validate_supplier(db, company.id, payload.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=422, detail="Fornecedor obrigatorio")
    normalized_status = _validate_purchase_return_status_transition(None, payload.status)
    invoice_number = payload.invoice_number.strip() if payload.invoice_number else None

    purchase_return = PurchaseReturn(
        company_id=company.id,
        supplier_id=supplier.id,
        return_date=payload.return_date,
        amount=_money(payload.amount),
        invoice_number=invoice_number or None,
        status=normalized_status,
        notes=payload.notes,
    )
    db.add(purchase_return)
    db.flush()
    if _purchase_return_status_index(normalized_status) >= _purchase_return_status_index(PURCHASE_RETURN_APPROVAL_STATUS):
        _ensure_purchase_return_refund_entry(
            db,
            company,
            purchase_return,
            actor_user,
            supplier_name=supplier.name,
        )
        db.flush()
    purchase_return = db.scalar(
        select(PurchaseReturn)
        .where(PurchaseReturn.id == purchase_return.id)
        .options(joinedload(PurchaseReturn.supplier))
    )
    assert purchase_return is not None
    write_audit_log(
        db,
        action="create_purchase_return",
        entity_name="purchase_return",
        entity_id=purchase_return.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "supplier_id": purchase_return.supplier_id,
            "return_date": purchase_return.return_date.isoformat(),
            "amount": f"{purchase_return.amount:.2f}",
            "invoice_number": purchase_return.invoice_number,
            "status": purchase_return.status,
        },
    )
    return _serialize_purchase_return(purchase_return)


def update_purchase_return(
    db: Session,
    company: Company,
    purchase_return_id: str,
    payload: PurchaseReturnUpdate,
    actor_user: User,
) -> PurchaseReturnRead:
    purchase_return = db.scalar(
        select(PurchaseReturn)
        .where(PurchaseReturn.id == purchase_return_id, PurchaseReturn.company_id == company.id)
        .options(joinedload(PurchaseReturn.supplier))
    )
    if purchase_return is None:
        raise HTTPException(status_code=404, detail="Devolucao de compra nao encontrada")

    supplier = _validate_supplier(db, company.id, payload.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=422, detail="Fornecedor obrigatorio")

    before_state = _serialize_purchase_return(purchase_return).model_dump(mode="json")
    next_status = _validate_purchase_return_status_transition(purchase_return.status, payload.status)
    purchase_return.supplier_id = supplier.id
    purchase_return.supplier = supplier
    purchase_return.return_date = payload.return_date
    purchase_return.amount = _money(payload.amount)
    purchase_return.invoice_number = payload.invoice_number.strip() if payload.invoice_number else None
    purchase_return.status = next_status
    purchase_return.notes = payload.notes
    if _purchase_return_status_index(next_status) >= _purchase_return_status_index(PURCHASE_RETURN_APPROVAL_STATUS):
        _ensure_purchase_return_refund_entry(
            db,
            company,
            purchase_return,
            actor_user,
            supplier_name=supplier.name,
        )
    else:
        _remove_purchase_return_refund_entry(
            db,
            company,
            purchase_return,
            actor_user,
        )
    db.flush()
    write_audit_log(
        db,
        action="update_purchase_return",
        entity_name="purchase_return",
        entity_id=purchase_return.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_serialize_purchase_return(purchase_return).model_dump(mode="json"),
    )
    return _serialize_purchase_return(purchase_return)


def delete_purchase_return(
    db: Session,
    company: Company,
    purchase_return_id: str,
    actor_user: User,
) -> None:
    from app.services.finance_ops import delete_entry

    purchase_return = db.scalar(
        select(PurchaseReturn)
        .where(PurchaseReturn.id == purchase_return_id, PurchaseReturn.company_id == company.id)
        .options(joinedload(PurchaseReturn.supplier))
    )
    if purchase_return is None:
        raise HTTPException(status_code=404, detail="Devolucao de compra nao encontrada")

    before_state = _serialize_purchase_return(purchase_return).model_dump(mode="json")
    if purchase_return.refund_entry_id:
        refund_entry = db.get(FinancialEntry, purchase_return.refund_entry_id)
        if refund_entry is not None and refund_entry.company_id == company.id and not refund_entry.is_deleted:
            delete_entry(db, company, refund_entry.id, actor_user)
    db.delete(purchase_return)
    db.flush()
    write_audit_log(
        db,
        action="delete_purchase_return",
        entity_name="purchase_return",
        entity_id=purchase_return_id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"deleted": True},
    )


def _match_entry_to_plan(
    entry: FinancialEntry,
    *,
    plan_supplier_names: dict[str, set[str]],
    plan_periods: dict[str, tuple[date, date]],
) -> str | None:
    entry_date = entry.issue_date or entry.competence_date or entry.due_date
    if entry_date is None:
        return None
    normalized_candidates = {
        normalize_label(value)
        for value in [
            entry.supplier.name if entry.supplier else None,
            entry.counterparty_name,
            entry.title,
        ]
        if value
    }
    if not normalized_candidates:
        return None
    for plan_id, supplier_names in plan_supplier_names.items():
        period_start, period_end = plan_periods[plan_id]
        if entry_date < period_start or entry_date > period_end:
            continue
        if any(
            supplier_name == candidate or supplier_name in candidate
            for supplier_name in supplier_names
            for candidate in normalized_candidates
        ):
            return plan_id
    return None


def _match_invoice_to_plan(
    invoice: PurchaseInvoice,
    *,
    plan_supplier_names: dict[str, set[str]],
    plan_supplier_ids: dict[str, set[str]],
    plan_periods: dict[str, tuple[date, date]],
) -> str | None:
    invoice_date = invoice.issue_date or invoice.entry_date
    if invoice_date is None:
        return None
    normalized_candidates = {
        normalize_label(value)
        for value in [
            invoice.supplier.name if invoice.supplier else None,
        ]
        if value
    }
    for plan_id, (period_start, period_end) in plan_periods.items():
        if invoice_date < period_start or invoice_date > period_end:
            continue
        if invoice.supplier_id and invoice.supplier_id in plan_supplier_ids.get(plan_id, set()):
            return plan_id
        supplier_names = plan_supplier_names.get(plan_id, set())
        if any(
            supplier_name == candidate or supplier_name in candidate or candidate in supplier_name
            for supplier_name in supplier_names
            for candidate in normalized_candidates
        ):
            return plan_id
    return None


def _match_entry_to_registered_supplier(
    entry: FinancialEntry,
    *,
    registered_suppliers: dict[str, Supplier],
) -> Supplier | None:
    if entry.supplier and entry.supplier.name:
        return entry.supplier
    normalized_candidates = {
        normalize_label(value)
        for value in [
            entry.counterparty_name,
            entry.title,
        ]
        if value
    }
    if not normalized_candidates:
        return None
    for normalized_name, supplier in registered_suppliers.items():
        if any(
            normalized_name == candidate or normalized_name in candidate or candidate in normalized_name
            for candidate in normalized_candidates
        ):
            return supplier
    return None


def _is_purchase_entry(entry: FinancialEntry) -> bool:
    if entry.purchase_invoice_id or entry.purchase_installment_id or entry.source_system == "purchase_invoice":
        return True
    category = entry.category
    if category is None:
        return False
    normalized_labels = {
        normalize_label(value)
        for value in [category.name, category.report_group, category.report_subgroup]
        if value
    }
    return any("compra" in label for label in normalized_labels)


def _build_plan_financial_totals(
    db: Session,
    company_id: str,
    plans: list[PurchasePlan],
) -> tuple[dict[str, dict[str, Decimal]], list[PurchasePlanningUngroupedSupplier]]:
    if not plans:
        return {}, []

    totals_by_plan_id: dict[str, dict[str, Decimal]] = {}
    plan_supplier_names: dict[str, set[str]] = {}
    plan_supplier_ids: dict[str, set[str]] = {}
    plan_periods: dict[str, tuple[date, date]] = {}
    plan_collection_names: dict[str, str | None] = {}
    min_period_start: date | None = None
    max_period_end: date | None = None
    for plan in plans:
        totals_by_plan_id[plan.id] = {"received_amount": Decimal("0.00")}
        if not plan.collection:
            continue
        supplier_names = {
            normalize_label(supplier.name)
            for supplier in _plan_suppliers(plan)
            if supplier.name
        }
        supplier_ids = {supplier.id for supplier in _plan_suppliers(plan) if supplier.id}
        if not supplier_names and not supplier_ids:
            continue
        plan_supplier_names[plan.id] = supplier_names
        plan_supplier_ids[plan.id] = supplier_ids
        plan_periods[plan.id] = (plan.collection.start_date, plan.collection.end_date)
        plan_collection_names[plan.id] = _collection_name(plan.collection)
        min_period_start = plan.collection.start_date if min_period_start is None else min(min_period_start, plan.collection.start_date)
        max_period_end = plan.collection.end_date if max_period_end is None else max(max_period_end, plan.collection.end_date)

    if min_period_start is None or max_period_end is None:
        return (
            {
                plan.id: {
                    "received_amount": Decimal("0.00"),
                    "amount_to_receive": _money(plan.purchased_amount),
                }
                for plan in plans
            },
            [],
        )

    invoices = list(
        db.scalars(
            select(PurchaseInvoice)
            .where(
                PurchaseInvoice.company_id == company_id,
                func.coalesce(PurchaseInvoice.issue_date, PurchaseInvoice.entry_date) >= min_period_start,
                func.coalesce(PurchaseInvoice.issue_date, PurchaseInvoice.entry_date) <= max_period_end,
            )
            .options(
                joinedload(PurchaseInvoice.supplier),
                joinedload(PurchaseInvoice.collection),
            )
        )
    )
    for invoice in invoices:
        net_received_amount = _money(invoice.total_amount)
        if net_received_amount <= 0:
            continue
        direct_plan_id = invoice.purchase_plan_id
        if direct_plan_id in totals_by_plan_id:
            totals_by_plan_id.setdefault(direct_plan_id, {"received_amount": Decimal("0.00")})
            totals_by_plan_id[direct_plan_id]["received_amount"] += net_received_amount
            continue
        matched_plan_id = _match_invoice_to_plan(
            invoice,
            plan_supplier_names=plan_supplier_names,
            plan_supplier_ids=plan_supplier_ids,
            plan_periods=plan_periods,
        )
        if matched_plan_id:
            totals_by_plan_id.setdefault(matched_plan_id, {"received_amount": Decimal("0.00")})
            totals_by_plan_id[matched_plan_id]["received_amount"] += net_received_amount

    brand_linked_supplier_ids = set(
        db.scalars(
            select(PurchaseBrandSupplier.supplier_id).where(
                PurchaseBrandSupplier.company_id == company_id,
            )
        )
    )
    registered_suppliers = {
        normalize_label(supplier.name): supplier
        for supplier in db.scalars(
            select(Supplier).where(
                Supplier.company_id == company_id,
            )
        )
        if supplier.name
    }
    ungrouped_entries: dict[tuple[str, str | None, date, date], dict[str, Decimal | int | str | date | None]] = {}
    entries = list(
        db.scalars(
            select(FinancialEntry)
            .where(
                FinancialEntry.company_id == company_id,
                FinancialEntry.entry_type == "expense",
                FinancialEntry.status.in_([OPEN_STATUS, "planned", "partial", "settled"]),
                FinancialEntry.is_deleted.is_(False),
                func.coalesce(FinancialEntry.issue_date, FinancialEntry.competence_date, FinancialEntry.due_date) >= min_period_start,
                func.coalesce(FinancialEntry.issue_date, FinancialEntry.competence_date, FinancialEntry.due_date) <= max_period_end,
            )
            .options(
                joinedload(FinancialEntry.category),
                joinedload(FinancialEntry.supplier),
                joinedload(FinancialEntry.purchase_invoice),
            )
        )
    )
    for entry in entries:
        entry_date = entry.issue_date or entry.competence_date or entry.due_date
        if entry_date is None:
            continue
        if not _is_purchase_entry(entry):
            continue
        registered_supplier = _match_entry_to_registered_supplier(
            entry,
            registered_suppliers=registered_suppliers,
        )
        matched_supplier_plan_id = _match_entry_to_plan(
            entry,
            plan_supplier_names=plan_supplier_names,
            plan_periods=plan_periods,
        )
        if (
            matched_supplier_plan_id is not None
            and registered_supplier is not None
            and registered_supplier.id in plan_supplier_ids.get(matched_supplier_plan_id, set())
            and not entry.purchase_invoice_id
            and not entry.purchase_installment_id
            and entry.source_system != "purchase_invoice"
        ):
            totals_by_plan_id.setdefault(matched_supplier_plan_id, {"received_amount": Decimal("0.00")})
            totals_by_plan_id[matched_supplier_plan_id]["received_amount"] += _money(entry.total_amount)

        matching_plan_id = None
        if entry.collection_id:
            matching_plan_id = next(
                (
                    plan.id
                    for plan in plans
                    if plan.collection_id == entry.collection_id
                ),
                None,
            )
        if matching_plan_id is None:
            matching_plan_id = next(
                (
                    plan_id
                    for plan_id, (period_start, period_end) in plan_periods.items()
                    if period_start <= entry_date <= period_end
                ),
                None,
            )
        if matching_plan_id is None:
            continue
        if not registered_supplier:
            continue
        if registered_supplier.id in brand_linked_supplier_ids:
            continue
        period_start, period_end = plan_periods[matching_plan_id]
        collection_name = plan_collection_names.get(matching_plan_id)
        key = (registered_supplier.name, collection_name, period_start, period_end)
        bucket = ungrouped_entries.setdefault(
            key,
            {
                "supplier_label": registered_supplier.name,
                "collection_name": collection_name,
                "period_start": period_start,
                "period_end": period_end,
                "entry_count": 0,
                "total_amount": Decimal("0.00"),
            }
        )
        bucket["entry_count"] = int(bucket["entry_count"]) + 1
        bucket["total_amount"] = Decimal(bucket["total_amount"]) + _money(entry.total_amount)

    result: dict[str, dict[str, Decimal]] = {}
    for plan in plans:
        received_amount = _money(totals_by_plan_id.get(plan.id, {}).get("received_amount", Decimal("0.00")))
        amount_to_receive = _money(max(_money(plan.purchased_amount) - received_amount, Decimal("0.00")))
        result[plan.id] = {
            "received_amount": received_amount,
            "amount_to_receive": amount_to_receive,
        }
    return (
        result,
        sorted(
            [
                PurchasePlanningUngroupedSupplier(
                    supplier_label=str(item["supplier_label"]),
                    collection_name=str(item["collection_name"]) if item["collection_name"] else None,
                    season_label=str(item["collection_name"]) if item["collection_name"] else None,
                    period_start=item["period_start"] if isinstance(item["period_start"], date) else None,
                    period_end=item["period_end"] if isinstance(item["period_end"], date) else None,
                    entry_count=int(item["entry_count"]),
                    total_amount=_money(Decimal(item["total_amount"])),
                )
                for item in ungrouped_entries.values()
            ],
            key=lambda item: (item.collection_name or "", item.supplier_label),
        ),
    )


def _build_supplier_season_totals(
    db: Session,
    company_id: str,
) -> dict[tuple[str, int, str], Decimal]:
    invoice_totals: dict[tuple[str, int, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    for invoice in db.execute(
        select(PurchaseInvoice)
        .where(PurchaseInvoice.company_id == company_id)
        .options(joinedload(PurchaseInvoice.collection))
    ).scalars():
        if not invoice.supplier_id or invoice.collection is None:
            continue
        season_year = invoice.collection.season_year
        season_type = _normalize_season_type(invoice.collection.season_type)
        if not season_year or not season_type:
            continue
        key = (invoice.supplier_id, season_year, season_type)
        invoice_totals[key] += _money(invoice.total_amount)

    plan_totals: dict[tuple[str, int, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    for plan in db.execute(
        select(PurchasePlan)
        .where(PurchasePlan.company_id == company_id)
        .options(
            joinedload(PurchasePlan.collection),
            joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
            joinedload(PurchasePlan.supplier),
        )
    ).unique().scalars():
        if plan.collection is None:
            continue
        season_year = plan.collection.season_year
        season_type = _normalize_season_type(plan.collection.season_type)
        if not season_year or not season_type:
            continue
        supplier_ids = _plan_supplier_ids(plan)
        if not supplier_ids:
            continue
        amount_per_supplier = _money(Decimal(plan.purchased_amount or 0) / Decimal(len(supplier_ids)))
        remaining = _money(plan.purchased_amount)
        for index, supplier_id in enumerate(supplier_ids, start=1):
            allocated_amount = amount_per_supplier if index < len(supplier_ids) else remaining
            remaining = _money(remaining - allocated_amount)
            key = (supplier_id, season_year, season_type)
            plan_totals[key] += _money(allocated_amount)

    totals: dict[tuple[str, int, str], Decimal] = {}
    for key in set(invoice_totals) | set(plan_totals):
        totals[key] = _money(max(invoice_totals.get(key, Decimal("0.00")), plan_totals.get(key, Decimal("0.00"))))
    return totals


def _season_metrics_for_plan(
    plan: PurchasePlan,
    season_totals: dict[tuple[str, int, str], Decimal],
) -> dict[str, Decimal]:
    if plan.collection is None or not plan.collection.season_year or not plan.collection.season_type:
        return {
            "prior_year_same_season_amount": Decimal("0.00"),
            "current_year_same_season_amount": Decimal("0.00"),
            "current_year_other_seasons_amount": Decimal("0.00"),
            "suggested_remaining_amount": Decimal("0.00"),
        }

    season_year = plan.collection.season_year
    season_type = _normalize_season_type(plan.collection.season_type)
    if season_type is None:
        return {
            "prior_year_same_season_amount": Decimal("0.00"),
            "current_year_same_season_amount": Decimal("0.00"),
            "current_year_other_seasons_amount": Decimal("0.00"),
            "suggested_remaining_amount": Decimal("0.00"),
        }

    prior_year_amount = Decimal("0.00")
    current_year_amount = Decimal("0.00")
    other_seasons_amount = Decimal("0.00")
    for supplier_id in _plan_supplier_ids(plan):
        prior_year_amount += season_totals.get((supplier_id, season_year - 1, season_type), Decimal("0.00"))
        current_year_amount += season_totals.get((supplier_id, season_year, season_type), Decimal("0.00"))
        for other_type in SEASON_LABELS:
            if other_type == season_type:
                continue
            other_seasons_amount += season_totals.get((supplier_id, season_year, other_type), Decimal("0.00"))

    return {
        "prior_year_same_season_amount": _money(prior_year_amount),
        "current_year_same_season_amount": _money(current_year_amount),
        "current_year_other_seasons_amount": _money(other_seasons_amount),
        "suggested_remaining_amount": _money(max(prior_year_amount - current_year_amount, Decimal("0.00"))),
    }


def _serialize_plan(
    plan: PurchasePlan,
    *,
    received_amount: Decimal | None = None,
    amount_to_receive: Decimal | None = None,
    season_metrics: dict[str, Decimal] | None = None,
) -> PurchasePlanRead:
    suppliers = _plan_suppliers(plan)
    supplier_names = [supplier.name for supplier in suppliers]
    collection_name = _collection_name(plan.collection)
    season_metrics = season_metrics or {}
    return PurchasePlanRead(
        id=plan.id,
        brand_id=plan.brand_id,
        supplier_id=plan.supplier_id,
        supplier_ids=[supplier.id for supplier in suppliers],
        collection_id=plan.collection_id,
        season_phase=_normalize_season_phase(plan.season_phase),
        title=plan.title,
        order_date=plan.order_date,
        expected_delivery_date=plan.expected_delivery_date,
        purchased_amount=_money(plan.purchased_amount),
        payment_term=plan.payment_term,
        status=plan.status,
        notes=plan.notes,
        brand_name=plan.brand.name if plan.brand else None,
        supplier_name=", ".join(supplier_names) if supplier_names else None,
        supplier_names=supplier_names,
        collection_name=collection_name,
        season_year=plan.collection.season_year if plan.collection else None,
        season_type=_normalize_season_type(plan.collection.season_type) if plan.collection else None,
        season_label=collection_name,
        season_phase_label=_season_phase_label(plan.season_phase),
        billing_deadline=plan.collection.end_date if plan.collection else None,
        received_amount=_money(received_amount),
        amount_to_receive=_money(amount_to_receive),
        prior_year_same_season_amount=_money(season_metrics.get("prior_year_same_season_amount")),
        current_year_same_season_amount=_money(season_metrics.get("current_year_same_season_amount")),
        current_year_other_seasons_amount=_money(season_metrics.get("current_year_other_seasons_amount")),
        suggested_remaining_amount=_money(season_metrics.get("suggested_remaining_amount")),
    )


def list_purchase_plans(db: Session, company: Company, limit: int = 100) -> list[PurchasePlanRead]:
    plans = (
        db.execute(
            select(PurchasePlan)
            .where(PurchasePlan.company_id == company.id)
            .order_by(PurchasePlan.order_date.desc().nullslast(), PurchasePlan.created_at.desc())
            .limit(limit)
            .options(
                joinedload(PurchasePlan.brand),
                joinedload(PurchasePlan.supplier),
                joinedload(PurchasePlan.collection),
                joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    financial_totals, _ = _build_plan_financial_totals(db, company.id, plans)
    season_totals = _build_supplier_season_totals(db, company.id)
    return [
        _serialize_plan(
            item,
            received_amount=financial_totals.get(item.id, {}).get("received_amount"),
            amount_to_receive=financial_totals.get(item.id, {}).get("amount_to_receive"),
            season_metrics=_season_metrics_for_plan(item, season_totals),
        )
        for item in plans
    ]


def create_purchase_plan(db: Session, company: Company, payload: PurchasePlanCreate, actor_user: User) -> PurchasePlanRead:
    _validate_brand(db, company.id, payload.brand_id)
    _validate_collection(db, company.id, payload.collection_id)
    supplier_ids = _normalize_supplier_ids(payload.supplier_id, payload.supplier_ids)
    for supplier_id in supplier_ids:
        _validate_supplier(db, company.id, supplier_id)
    plan_data = payload.model_dump(exclude={"supplier_ids"})
    plan_data["supplier_id"] = supplier_ids[0] if supplier_ids else None
    plan_data["season_phase"] = _normalize_season_phase(payload.season_phase)
    plan = PurchasePlan(company_id=company.id, **plan_data)
    plan.purchased_amount = _money(payload.purchased_amount)
    db.add(plan)
    db.flush()
    _sync_plan_suppliers(db, company.id, plan, supplier_ids)
    db.flush()
    plan = db.get(PurchasePlan, plan.id)
    assert plan is not None
    write_audit_log(
        db,
        action="create_purchase_plan",
        entity_name="purchase_plan",
        entity_id=plan.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "title": plan.title,
            "purchased_amount": f"{plan.purchased_amount:.2f}",
            "status": plan.status,
            "season_phase": plan.season_phase,
        },
    )
    financial_totals, _ = _build_plan_financial_totals(db, company.id, [plan])
    season_totals = _build_supplier_season_totals(db, company.id)
    return _serialize_plan(
        plan,
        received_amount=financial_totals.get(plan.id, {}).get("received_amount"),
        amount_to_receive=financial_totals.get(plan.id, {}).get("amount_to_receive"),
        season_metrics=_season_metrics_for_plan(plan, season_totals),
    )


def update_purchase_plan(
    db: Session,
    company: Company,
    plan_id: str,
    payload: PurchasePlanUpdate,
    actor_user: User,
) -> PurchasePlanRead:
    plan = db.get(PurchasePlan, plan_id)
    if not plan or plan.company_id != company.id:
        raise HTTPException(status_code=404, detail="Posicao de compra nao encontrada")
    _validate_brand(db, company.id, payload.brand_id)
    _validate_collection(db, company.id, payload.collection_id)
    supplier_ids = _normalize_supplier_ids(payload.supplier_id, payload.supplier_ids)
    for supplier_id in supplier_ids:
        _validate_supplier(db, company.id, supplier_id)
    before_state = {
        "title": plan.title,
        "purchased_amount": f"{plan.purchased_amount:.2f}",
        "status": plan.status,
        "season_phase": plan.season_phase,
    }
    for field_name, value in payload.model_dump(exclude={"supplier_ids"}).items():
        if field_name == "season_phase":
            setattr(plan, field_name, _normalize_season_phase(value))
            continue
        setattr(plan, field_name, value)
    _sync_plan_suppliers(db, company.id, plan, supplier_ids)
    plan.purchased_amount = _money(payload.purchased_amount)
    db.flush()
    write_audit_log(
        db,
        action="update_purchase_plan",
        entity_name="purchase_plan",
        entity_id=plan.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={
            "title": plan.title,
            "purchased_amount": f"{plan.purchased_amount:.2f}",
            "status": plan.status,
            "season_phase": plan.season_phase,
        },
    )
    financial_totals, _ = _build_plan_financial_totals(db, company.id, [plan])
    season_totals = _build_supplier_season_totals(db, company.id)
    return _serialize_plan(
        plan,
        received_amount=financial_totals.get(plan.id, {}).get("received_amount"),
        amount_to_receive=financial_totals.get(plan.id, {}).get("amount_to_receive"),
        season_metrics=_season_metrics_for_plan(plan, season_totals),
    )


def delete_purchase_plan(
    db: Session,
    company: Company,
    plan_id: str,
    actor_user: User,
) -> None:
    plan = db.scalar(
        select(PurchasePlan)
        .where(PurchasePlan.id == plan_id, PurchasePlan.company_id == company.id)
        .options(
            joinedload(PurchasePlan.supplier),
            joinedload(PurchasePlan.collection),
            joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Posicao de compra nao encontrada")

    linked_invoices = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == company.id,
            PurchaseInvoice.purchase_plan_id == plan.id,
        )
    ) or 0
    linked_deliveries = db.scalar(
        select(func.count(PurchaseDelivery.id)).where(
            PurchaseDelivery.company_id == company.id,
            PurchaseDelivery.purchase_plan_id == plan.id,
        )
    ) or 0
    if linked_invoices or linked_deliveries:
        raise HTTPException(
            status_code=409,
            detail="Compra planejada ja possui notas ou entregas vinculadas. Ajuste os vinculos antes de excluir.",
        )

    financial_totals, _ = _build_plan_financial_totals(db, company.id, [plan])
    before_state = _serialize_plan(
        plan,
        received_amount=financial_totals.get(plan.id, {}).get("received_amount"),
        amount_to_receive=financial_totals.get(plan.id, {}).get("amount_to_receive"),
    ).model_dump(mode="json")
    db.delete(plan)
    db.flush()
    write_audit_log(
        db,
        action="delete_purchase_plan",
        entity_name="purchase_plan",
        entity_id=plan.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"deleted": True},
    )


def _sync_installment_status(installment: PurchaseInstallment) -> str:
    linked_entry = installment.financial_entry
    if linked_entry is None or linked_entry.is_deleted:
        return OPEN_STATUS
    paid_amount = Decimal(linked_entry.paid_amount or 0)
    if paid_amount >= Decimal(installment.amount or 0) and linked_entry.status == "settled":
        return "paid"
    if paid_amount > 0 or linked_entry.status == "partial":
        return "partial"
    return "linked"


def _installment_remaining_amount(installment: PurchaseInstallment) -> Decimal:
    if installment.financial_entry is None or installment.financial_entry.is_deleted:
        return _money(installment.amount)
    paid_amount = Decimal(installment.financial_entry.paid_amount or 0)
    return max(_money(Decimal(installment.amount or 0) - paid_amount), Decimal("0.00"))


def _candidate_entries_for_installment(
    db: Session,
    company_id: str,
    installment: PurchaseInstallment,
) -> list[PurchaseInstallmentCandidate]:
    supplier_name = installment.invoice.supplier.name if installment.invoice and installment.invoice.supplier else None
    title_like = f"%{supplier_name}%" if supplier_name else None
    stmt = select(FinancialEntry).where(
        FinancialEntry.company_id == company_id,
        FinancialEntry.entry_type == "expense",
        FinancialEntry.is_deleted.is_(False),
    )
    if title_like:
        stmt = stmt.where(
            or_(
                FinancialEntry.counterparty_name.ilike(title_like),
                FinancialEntry.title.ilike(title_like),
                FinancialEntry.description.ilike(title_like),
            )
        )
    if installment.due_date:
        stmt = stmt.where(
            FinancialEntry.due_date.is_not(None),
            FinancialEntry.due_date >= installment.due_date - timedelta(days=20),
            FinancialEntry.due_date <= installment.due_date + timedelta(days=20),
        )
    entries = list(
        db.scalars(
            stmt.order_by(
                FinancialEntry.due_date.asc().nullslast(),
                FinancialEntry.created_at.desc(),
            ).limit(8)
        )
    )
    return [
        PurchaseInstallmentCandidate(
            entry_id=entry.id,
            title=entry.title,
            due_date=entry.due_date,
            total_amount=_money(entry.total_amount),
            paid_amount=_money(entry.paid_amount),
            status=entry.status,
            counterparty_name=entry.counterparty_name,
        )
        for entry in entries
    ]


def _serialize_installment(
    db: Session,
    installment: PurchaseInstallment,
    *,
    include_candidates: bool = True,
) -> PurchaseInstallmentRead:
    installment.status = _sync_installment_status(installment)
    return PurchaseInstallmentRead(
        id=installment.id,
        purchase_invoice_id=installment.purchase_invoice_id,
        installment_number=installment.installment_number,
        installment_label=installment.installment_label,
        due_date=installment.due_date,
        amount=_money(installment.amount),
        status=installment.status,
        financial_entry_id=installment.financial_entry_id,
        brand_name=installment.invoice.brand.name if installment.invoice and installment.invoice.brand else None,
        supplier_name=installment.invoice.supplier.name if installment.invoice and installment.invoice.supplier else None,
        collection_name=_collection_name(installment.invoice.collection) if installment.invoice else None,
        invoice_number=installment.invoice.invoice_number if installment.invoice else None,
        candidates=_candidate_entries_for_installment(db, installment.company_id, installment) if include_candidates else [],
    )


def _serialize_invoice(db: Session, invoice: PurchaseInvoice) -> PurchaseInvoiceRead:
    return PurchaseInvoiceRead(
        id=invoice.id,
        brand_id=invoice.brand_id,
        brand_name=invoice.brand.name if invoice.brand else None,
        supplier_id=invoice.supplier_id,
        supplier_name=invoice.supplier.name if invoice.supplier else None,
        collection_id=invoice.collection_id,
        collection_name=_collection_name(invoice.collection),
        season_phase=_normalize_season_phase(invoice.season_phase),
        season_phase_label=_season_phase_label(invoice.season_phase),
        purchase_plan_id=invoice.purchase_plan_id,
        invoice_number=invoice.invoice_number,
        series=invoice.series,
        nfe_key=invoice.nfe_key,
        issue_date=invoice.issue_date,
        entry_date=invoice.entry_date,
        total_amount=_money(invoice.total_amount),
        payment_description=invoice.payment_description,
        payment_term=invoice.payment_term,
        source_type=invoice.source_type,
        status=invoice.status,
        notes=invoice.notes,
        installments=[_serialize_installment(db, item, include_candidates=True) for item in invoice.installments],
    )


def _build_purchase_installment_entry_title(
    supplier_name: str,
    invoice_number: str | None,
    installment: PurchaseInstallment,
) -> str:
    invoice_label = f"NF {invoice_number}" if invoice_number else "NF compra"
    installment_label = installment.installment_label or str(installment.installment_number)
    return f"{supplier_name} - {invoice_label} - Parcela {installment_label}"


def _ensure_purchase_category(db: Session, company_id: str) -> Category:
    purchase_category = db.scalar(
        select(Category).where(
            Category.company_id == company_id,
            Category.entry_kind == "expense",
            or_(
                Category.name == "Compras",
                Category.report_group == "Compras",
                Category.report_subgroup == "Compras",
            ),
        )
    )
    if purchase_category is None:
        purchase_category = Category(
            company_id=company_id,
            code=None,
            name="Compras",
            entry_kind="expense",
            report_group="Compras",
            report_subgroup="Compras",
            is_active=True,
        )
        db.add(purchase_category)
        db.flush()
    elif not purchase_category.is_active:
        purchase_category.is_active = True
        db.flush()
    return purchase_category


def _create_financial_entry_for_installment(
    db: Session,
    *,
    company_id: str,
    supplier: Supplier,
    invoice: PurchaseInvoice,
    installment: PurchaseInstallment,
) -> FinancialEntry:
    reference_date = invoice.issue_date or invoice.entry_date or installment.due_date
    purchase_category = _ensure_purchase_category(db, company_id)
    financial_entry = FinancialEntry(
        company_id=company_id,
        category_id=purchase_category.id,
        supplier_id=invoice.supplier_id,
        collection_id=invoice.collection_id,
        season_phase=_normalize_season_phase(invoice.season_phase),
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status=OPEN_STATUS,
        title=_build_purchase_installment_entry_title(supplier.name, invoice.invoice_number, installment),
        description="Gerado automaticamente a partir da nota fiscal de compra.",
        notes=invoice.notes,
        counterparty_name=supplier.name,
        document_number=invoice.invoice_number,
        issue_date=reference_date,
        competence_date=reference_date,
        due_date=installment.due_date,
        principal_amount=_money(installment.amount),
        total_amount=_money(installment.amount),
        paid_amount=Decimal("0.00"),
        external_source="purchase_invoice",
        source_system="purchase_invoice",
        source_reference=invoice.nfe_key or f"{invoice.id}:{installment.installment_number}",
    )
    db.add(financial_entry)
    db.flush()
    installment.financial_entry_id = financial_entry.id
    return financial_entry


def _find_existing_import_batch(
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


def _create_import_batch(
    db: Session,
    company_id: str,
    source_type: str,
    filename: str,
    content: bytes,
) -> tuple[ImportBatch, bool]:
    fingerprint = fingerprint_bytes(content)
    existing = _find_existing_import_batch(db, company_id, source_type, fingerprint)
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


def _resolve_linx_purchase_payable_amount(row: ParsedPurchasePayableRow) -> Decimal:
    amount = _money(row.amount_with_charges or row.original_amount)
    if amount <= Decimal("0.00"):
        amount = _money(row.original_amount)
    return amount


def _build_linx_purchase_invoice_note(rows: list[ParsedPurchasePayableRow]) -> str:
    payable_codes = sorted({row.payable_code for row in rows if row.payable_code})
    if payable_codes:
        return (
            "Incluido via raspagem de dados do Linx. "
            f"Codigos da fatura Linx: {', '.join(payable_codes)}."
        )
    return "Incluido via raspagem de dados do Linx."


def _build_linx_purchase_entry_note(row: ParsedPurchasePayableRow) -> str:
    details = ["Incluido via raspagem de dados do Linx."]
    if row.payable_code:
        details.append(f"Codigo da fatura: {row.payable_code}.")
    if row.installment_label:
        details.append(f"Parcela: {row.installment_label}.")
    if row.document_number:
        details.append(f"Numero da nota: {row.document_number}.")
    return " ".join(details)


def _find_matching_purchase_invoice_for_linx(
    db: Session,
    company_id: str,
    supplier_id: str,
    row: ParsedPurchasePayableRow,
) -> PurchaseInvoice | None:
    if row.document_number:
        return db.scalar(
            select(PurchaseInvoice)
            .where(
                PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.supplier_id == supplier_id,
                PurchaseInvoice.invoice_number == row.document_number,
                PurchaseInvoice.series == row.document_series,
            )
            .options(joinedload(PurchaseInvoice.installments))
        )
    return None


def _find_matching_purchase_installment_for_linx(
    invoice: PurchaseInvoice,
    row: ParsedPurchasePayableRow,
) -> PurchaseInstallment | None:
    target_amount = _resolve_linx_purchase_payable_amount(row)
    for installment in invoice.installments:
        same_number = (
            row.installment_number is not None
            and installment.installment_number == row.installment_number
        )
        same_label = (
            row.installment_label is not None
            and installment.installment_label == row.installment_label
        )
        same_due_date = installment.due_date == row.due_date
        same_amount = _money(installment.amount) == target_amount
        if (same_number or same_label) and same_due_date and same_amount:
            return installment
    return None


def _create_linx_financial_entry_for_installment(
    db: Session,
    *,
    company_id: str,
    supplier: Supplier,
    invoice: PurchaseInvoice,
    installment: PurchaseInstallment,
    row: ParsedPurchasePayableRow,
    source_reference: str,
) -> FinancialEntry:
    purchase_category = _ensure_purchase_category(db, company_id)
    issue_date = invoice.issue_date or installment.due_date
    due_date = installment.due_date or invoice.issue_date
    financial_entry = FinancialEntry(
        company_id=company_id,
        category_id=purchase_category.id,
        supplier_id=invoice.supplier_id,
        collection_id=invoice.collection_id,
        season_phase=_normalize_season_phase(invoice.season_phase),
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status="open",
        title=_build_purchase_installment_entry_title(supplier.name, invoice.invoice_number, installment),
        description="Gerado automaticamente a partir da raspagem de faturas a pagar do Linx.",
        notes=_build_linx_purchase_entry_note(row),
        counterparty_name=supplier.name,
        document_number=invoice.invoice_number,
        issue_date=issue_date,
        competence_date=due_date,
        due_date=due_date,
        principal_amount=_money(installment.amount),
        total_amount=_money(installment.amount),
        paid_amount=Decimal("0.00"),
        external_source="linx_purchase_payables",
        source_system="linx_purchase_payables",
        source_reference=source_reference,
    )
    db.add(financial_entry)
    db.flush()
    installment.financial_entry_id = financial_entry.id
    installment.financial_entry = financial_entry
    installment.status = _sync_installment_status(installment)
    return financial_entry


def _get_or_create_supplier_for_linx_purchase(
    db: Session,
    company_id: str,
    supplier_name: str,
) -> tuple[Supplier, bool]:
    existing = _find_matching_supplier(
        db,
        company_id,
        supplier_name=supplier_name,
        supplier_document=None,
    )
    if existing is not None:
        return existing, False
    supplier = _find_or_create_supplier(
        db,
        company_id,
        supplier_id=None,
        supplier_name=supplier_name,
        supplier_document=None,
    )
    return supplier, True


def _sort_linx_purchase_rows(rows: list[ParsedPurchasePayableRow]) -> list[ParsedPurchasePayableRow]:
    return sorted(
        rows,
        key=lambda item: (
            item.installment_number if item.installment_number is not None else 999,
            item.due_date or date.max,
            item.payable_code or "",
        ),
    )


def _create_linx_purchase_invoice(
    db: Session,
    *,
    company: Company,
    actor_user: User,
    supplier: Supplier,
    rows: list[ParsedPurchasePayableRow],
) -> PurchaseInvoice:
    first_row = _sort_linx_purchase_rows(rows)[0]
    supplier.has_purchase_invoices = True
    brand = _brand_for_supplier(db, company.id, supplier.id)
    collection = _resolve_collection(db, company.id, None, first_row.issue_date)
    total_amount = sum((_resolve_linx_purchase_payable_amount(row) for row in rows), Decimal("0.00"))
    payment_term = f"{max((row.installments_total or 1) for row in rows)}x"

    invoice = PurchaseInvoice(
        company_id=company.id,
        brand_id=brand.id if brand else None,
        supplier_id=supplier.id,
        collection_id=collection.id if collection else None,
        purchase_plan_id=None,
        invoice_number=first_row.document_number,
        series=first_row.document_series,
        nfe_key=None,
        issue_date=first_row.issue_date,
        entry_date=first_row.issue_date,
        total_amount=_money(total_amount),
        payment_description="Linx - Faturas a pagar",
        payment_term=payment_term,
        payment_basis=supplier.payment_basis or "delivery",
        season_phase="main",
        raw_text=None,
        raw_xml=None,
        source_type="linx_payables",
        status="open",
        notes=_build_linx_purchase_invoice_note(rows),
    )
    db.add(invoice)
    db.flush()

    db.add(
        PurchaseDelivery(
            company_id=company.id,
            brand_id=brand.id if brand else None,
            supplier_id=supplier.id,
            collection_id=collection.id if collection else None,
            purchase_plan_id=None,
            purchase_invoice_id=invoice.id,
            delivery_date=first_row.issue_date,
            amount=_money(total_amount),
            season_phase="main",
            source_type="linx_payables",
            source_reference=first_row.document_number or first_row.payable_code,
            notes="Entrega inferida via raspagem de faturas a pagar do Linx",
        )
    )
    db.flush()

    write_audit_log(
        db,
        action="create_purchase_invoice",
        entity_name="purchase_invoice",
        entity_id=invoice.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "supplier_name": supplier.name,
            "invoice_number": invoice.invoice_number,
            "total_amount": f"{invoice.total_amount:.2f}",
            "source_type": invoice.source_type,
        },
    )
    return invoice


def _clean_linx_api_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _parse_linx_api_datetime(value: str | None) -> date | None:
    cleaned = _clean_linx_api_text(value)
    if not cleaned:
        return None
    for format_string in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, format_string).date()
        except ValueError:
            continue
    return None


def _parse_linx_api_int(value: str | None) -> int | None:
    cleaned = _clean_linx_api_text(value)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_linx_api_decimal(value: str | None) -> Decimal:
    cleaned = _clean_linx_api_text(value)
    if not cleaned:
        return Decimal("0.00")
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0.00")


def _split_linx_faturas_installment_pair(raw_value: str | None) -> tuple[str | None, int | None, int | None]:
    label = _clean_linx_api_text(raw_value)
    current = _parse_linx_api_int(raw_value)
    total = None
    return label, current, total


def _normalize_linx_api_purchase_status(
    *,
    canceled: bool,
    excluded: bool,
    settled_date: date | None,
) -> str:
    if canceled or excluded:
        return "Cancelado"
    if settled_date is not None:
        return "Baixado"
    return "Em aberto"


def _build_linx_api_purchase_title_source_reference(row: LinxApiPurchasePayableRow) -> str:
    return (
        f"{LINX_PURCHASE_PAYABLES_API_TAG}:{row.company_code or ''}:{row.payable_code or row.linx_code}"
    )


def _build_linx_api_purchase_invoice_note(rows: list[LinxApiPurchasePayableRow]) -> str:
    payable_codes = sorted({row.payable_code for row in rows if row.payable_code})
    suffix = f" Tag: {LINX_PURCHASE_PAYABLES_API_TAG}."
    if payable_codes:
        return (
            "Incluido via API do Linx. "
            f"Codigos da fatura Linx: {', '.join(payable_codes)}."
            f"{suffix}"
        )
    return f"Incluido via API do Linx.{suffix}"


def _build_linx_api_purchase_entry_note(row: LinxApiPurchasePayableRow) -> str:
    details = [f"Incluido via API do Linx. Tag: {LINX_PURCHASE_PAYABLES_API_TAG}."]
    if row.payable_code:
        details.append(f"Codigo da fatura: {row.payable_code}.")
    if row.installment_label:
        details.append(f"Parcela: {row.installment_label}.")
    if row.document_number:
        details.append(f"Numero da nota: {row.document_number}.")
    return " ".join(details)


def _build_linx_faturas_rows(response_bytes: bytes) -> list[dict[str, str]]:
    root = ElementTree.fromstring(response_bytes)
    header = [
        (node.text or "").strip()
        for node in root.findall("./ResponseData/C/D")
    ]
    rows: list[dict[str, str]] = []
    for row_node in root.findall("./ResponseData/R"):
        values = [(node.text or "").strip() for node in row_node.findall("./D")]
        rows.append(dict(zip(header, values)))
    return rows


def _fetch_linx_purchase_payable_rows_page(
    settings: LinxApiSettings,
    *,
    timestamp_value: int,
) -> tuple[bytes, list[dict[str, str]]]:
    request_root = ElementTree.Element("LinxMicrovix")
    ElementTree.SubElement(
        request_root,
        "Authentication",
        attrib={"user": LINX_WS_USERNAME, "password": LINX_WS_PASSWORD},
    )
    ElementTree.SubElement(request_root, "ResponseFormat").text = "xml"
    command = ElementTree.SubElement(request_root, "Command")
    ElementTree.SubElement(command, "Name").text = LINX_PURCHASE_PAYABLES_API_METHOD
    parameters = ElementTree.SubElement(command, "Parameters")
    for param_id, param_value in (
        ("chave", settings.api_key),
        ("cnpjEmp", settings.cnpj),
        ("data_inicial", LINX_PURCHASE_PAYABLES_API_FULL_LOAD_START),
        ("data_fim", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("timestamp", str(timestamp_value)),
    ):
        param = ElementTree.SubElement(parameters, "Parameter", attrib={"id": param_id})
        param.text = param_value

    payload = ElementTree.tostring(request_root, encoding="utf-8", xml_declaration=True)
    response = httpx.post(
        settings.base_url,
        content=payload,
        headers={"Content-Type": "application/xml; charset=utf-8"},
        timeout=LINX_PURCHASE_PAYABLES_API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content, _build_linx_faturas_rows(response.content)


def _collect_linx_purchase_payable_api_rows(
    settings: LinxApiSettings,
    *,
    start_timestamp: int,
) -> tuple[bytes, list[dict[str, str]]]:
    responses: list[bytes] = []
    rows: list[dict[str, str]] = []
    current_timestamp = start_timestamp
    while True:
        response_bytes, page_rows = _fetch_linx_purchase_payable_rows_page(
            settings,
            timestamp_value=current_timestamp,
        )
        responses.append(response_bytes)
        if not page_rows:
            break
        rows.extend(page_rows)
        max_timestamp = max((_parse_linx_api_int(row.get("timestamp")) or current_timestamp) for row in page_rows)
        if max_timestamp <= current_timestamp or len(page_rows) < LINX_PURCHASE_PAYABLES_API_PAGE_LIMIT:
            break
        current_timestamp = max_timestamp
    return b"\n".join(responses), rows


def _resolve_linx_api_purchase_amount(row: dict[str, str]) -> Decimal:
    amount = _parse_linx_api_decimal(row.get("valor_fatura"))
    amount += _parse_linx_api_decimal(row.get("valor_juros"))
    amount += _parse_linx_api_decimal(row.get("valor_multa"))
    amount += _parse_linx_api_decimal(row.get("taxa_financeira"))
    amount -= _parse_linx_api_decimal(row.get("valor_desconto"))
    amount -= _parse_linx_api_decimal(row.get("valor_abatimento"))
    if amount <= Decimal("0.00"):
        amount = _parse_linx_api_decimal(row.get("valor_fatura"))
    return _money(amount)


def _normalize_linx_api_purchase_row(row: dict[str, str]) -> LinxApiPurchasePayableRow | None:
    if (_clean_linx_api_text(row.get("receber_pagar")) or "").upper() != "P":
        return None
    issue_date = _parse_linx_api_datetime(row.get("data_emissao"))
    if issue_date is None or issue_date < LINX_PURCHASE_PAYABLES_API_MIN_ISSUE_DATE:
        return None
    linx_code = _parse_linx_api_int(row.get("codigo_fatura"))
    if linx_code is None:
        return None
    installment_label = _clean_linx_api_text(row.get("ordem_parcela"))
    return LinxApiPurchasePayableRow(
        linx_code=linx_code,
        issue_date=issue_date,
        payable_code=_clean_linx_api_text(row.get("codigo_fatura")),
        company_code=_clean_linx_api_text(row.get("empresa")),
        due_date=_parse_linx_api_datetime(row.get("data_vencimento")),
        installment_label=installment_label,
        installment_number=_parse_linx_api_int(row.get("ordem_parcela")),
        installments_total=_parse_linx_api_int(row.get("qtde_parcelas")),
        original_amount=_money(_parse_linx_api_decimal(row.get("valor_fatura"))),
        amount_with_charges=_resolve_linx_api_purchase_amount(row),
        supplier_name=_clean_linx_api_text(row.get("nome_cliente")) or f"Fornecedor {linx_code}",
        supplier_code=_clean_linx_api_text(row.get("cod_cliente")),
        document_number=_clean_linx_api_text(row.get("documento")),
        document_series=_clean_linx_api_text(row.get("serie")),
        status=_normalize_linx_api_purchase_status(
            canceled=(_clean_linx_api_text(row.get("cancelado")) or "N").upper() == "S",
            excluded=(_clean_linx_api_text(row.get("excluido")) or "N").upper() == "S",
            settled_date=_parse_linx_api_datetime(row.get("data_baixa")),
        ),
        paid_amount=_money(_parse_linx_api_decimal(row.get("valor_pago"))),
        settled_date=_parse_linx_api_datetime(row.get("data_baixa")),
        canceled=(_clean_linx_api_text(row.get("cancelado")) or "N").upper() == "S",
        excluded=(_clean_linx_api_text(row.get("excluido")) or "N").upper() == "S",
        row_timestamp=_parse_linx_api_int(row.get("timestamp")),
        observation=_clean_linx_api_text(row.get("observacao")),
    )


def _normalize_linx_lookup_part(value: str | int | None) -> str:
    cleaned = str(value or "").strip()
    return cleaned


def _build_purchase_movement_lookup(
    db: Session,
    *,
    company_id: str,
) -> tuple[set[tuple[str, str, str, str, date | None]], set[tuple[str, str, str, str]]]:
    exact_keys: set[tuple[str, str, str, str, date | None]] = set()
    loose_keys: set[tuple[str, str, str, str]] = set()
    rows = db.execute(
        select(
            LinxMovement.company_code,
            LinxMovement.customer_code,
            LinxMovement.document_number,
            LinxMovement.document_series,
            LinxMovement.issue_date,
            LinxMovement.launch_date,
        ).where(
            LinxMovement.company_id == company_id,
            LinxMovement.movement_type == "purchase",
            LinxMovement.issue_date >= datetime(2025, 3, 25),
        )
    ).all()
    for company_code, customer_code, document_number, document_series, issue_date, launch_date in rows:
        company_key = _normalize_linx_lookup_part(company_code)
        supplier_key = _normalize_linx_lookup_part(customer_code)
        document_key = _normalize_linx_lookup_part(document_number)
        series_key = _normalize_linx_lookup_part(document_series)
        if not supplier_key or not document_key:
            continue
        loose_keys.add((company_key, supplier_key, document_key, series_key))
        loose_keys.add((company_key, supplier_key, document_key, ""))
        for movement_date in (
            issue_date.date() if issue_date else None,
            launch_date.date() if launch_date else None,
        ):
            exact_keys.add((company_key, supplier_key, document_key, series_key, movement_date))
            exact_keys.add((company_key, supplier_key, document_key, "", movement_date))
    return exact_keys, loose_keys


def _row_matches_purchase_movement(
    row: LinxApiPurchasePayableRow,
    *,
    exact_lookup: set[tuple[str, str, str, str, date | None]],
    loose_lookup: set[tuple[str, str, str, str]],
) -> bool:
    company_key = _normalize_linx_lookup_part(row.company_code)
    supplier_key = _normalize_linx_lookup_part(row.supplier_code)
    document_key = _normalize_linx_lookup_part(row.document_number)
    series_key = _normalize_linx_lookup_part(row.document_series)
    if not supplier_key or not document_key:
        return False
    if (company_key, supplier_key, document_key, series_key, row.issue_date) in exact_lookup:
        return True
    if (company_key, supplier_key, document_key, "", row.issue_date) in exact_lookup:
        return True
    if (company_key, supplier_key, document_key, series_key) in loose_lookup:
        return True
    if (company_key, supplier_key, document_key, "") in loose_lookup:
        return True
    return False


def _create_linx_api_financial_entry_for_installment(
    db: Session,
    *,
    company_id: str,
    supplier: Supplier,
    invoice: PurchaseInvoice,
    installment: PurchaseInstallment,
    row: LinxApiPurchasePayableRow,
    source_reference: str,
) -> FinancialEntry:
    purchase_category = _ensure_purchase_category(db, company_id)
    issue_date = invoice.issue_date or installment.due_date
    due_date = installment.due_date or invoice.issue_date
    total_amount = _resolve_linx_purchase_payable_amount(row)
    paid_amount = min(_money(row.paid_amount), total_amount)
    if row.canceled or row.excluded:
        status = "cancelled"
        paid_amount = Decimal("0.00")
        settled_at = None
    elif row.settled_date is not None:
        status = "settled"
        if paid_amount <= Decimal("0.00"):
            paid_amount = total_amount
        settled_at = datetime.combine(row.settled_date, datetime.min.time(), tzinfo=timezone.utc)
    elif paid_amount > Decimal("0.00"):
        status = "partial"
        settled_at = None
    else:
        status = "open"
        settled_at = None

    financial_entry = FinancialEntry(
        company_id=company_id,
        category_id=purchase_category.id,
        supplier_id=invoice.supplier_id,
        collection_id=invoice.collection_id,
        season_phase=_normalize_season_phase(invoice.season_phase),
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status=status,
        title=_build_purchase_installment_entry_title(supplier.name, invoice.invoice_number, installment),
        description="Gerado automaticamente a partir da API de faturas a pagar do Linx.",
        notes=_build_linx_api_purchase_entry_note(row),
        counterparty_name=supplier.name,
        document_number=invoice.invoice_number,
        issue_date=issue_date,
        competence_date=due_date,
        due_date=due_date,
        settled_at=settled_at,
        principal_amount=total_amount,
        total_amount=total_amount,
        paid_amount=paid_amount,
        external_source=LINX_PURCHASE_PAYABLES_API_TAG,
        source_system=LINX_PURCHASE_PAYABLES_API_TAG,
        source_reference=source_reference,
    )
    db.add(financial_entry)
    db.flush()
    installment.financial_entry_id = financial_entry.id
    installment.financial_entry = financial_entry
    installment.status = _sync_installment_status(installment)
    return financial_entry


def _create_linx_api_purchase_invoice(
    db: Session,
    *,
    company: Company,
    actor_user: User,
    supplier: Supplier,
    rows: list[LinxApiPurchasePayableRow],
) -> PurchaseInvoice:
    first_row = _sort_linx_purchase_rows(rows)[0]
    supplier.has_purchase_invoices = True
    brand = _brand_for_supplier(db, company.id, supplier.id)
    collection = _resolve_collection(db, company.id, None, first_row.issue_date)
    total_amount = sum((_resolve_linx_purchase_payable_amount(row) for row in rows), Decimal("0.00"))
    payment_term = f"{max((row.installments_total or 1) for row in rows)}x"

    invoice = PurchaseInvoice(
        company_id=company.id,
        brand_id=brand.id if brand else None,
        supplier_id=supplier.id,
        collection_id=collection.id if collection else None,
        purchase_plan_id=None,
        invoice_number=first_row.document_number,
        series=first_row.document_series,
        nfe_key=None,
        issue_date=first_row.issue_date,
        entry_date=first_row.issue_date,
        total_amount=_money(total_amount),
        payment_description="Linx API - Faturas de compra",
        payment_term=payment_term,
        payment_basis=supplier.payment_basis or "delivery",
        season_phase="main",
        raw_text=None,
        raw_xml=None,
        source_type="linx_api_payables",
        status="open",
        notes=_build_linx_api_purchase_invoice_note(rows),
    )
    db.add(invoice)
    db.flush()

    db.add(
        PurchaseDelivery(
            company_id=company.id,
            brand_id=brand.id if brand else None,
            supplier_id=supplier.id,
            collection_id=collection.id if collection else None,
            purchase_plan_id=None,
            purchase_invoice_id=invoice.id,
            delivery_date=first_row.issue_date,
            amount=_money(total_amount),
            season_phase="main",
            source_type="linx_api_payables",
            source_reference=first_row.document_number or first_row.payable_code,
            notes=f"Entrega inferida via API de faturas de compra do Linx. Tag: {LINX_PURCHASE_PAYABLES_API_TAG}.",
        )
    )
    db.flush()

    write_audit_log(
        db,
        action="create_purchase_invoice",
        entity_name="purchase_invoice",
        entity_id=invoice.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "supplier_name": supplier.name,
            "invoice_number": invoice.invoice_number,
            "total_amount": f"{invoice.total_amount:.2f}",
            "source_type": invoice.source_type,
        },
    )
    return invoice


def import_linx_purchase_payables(
    db: Session,
    company: Company,
    filename: str,
    content: bytes,
    actor_user: User,
) -> ImportResult:
    batch, reused = _create_import_batch(db, company.id, "linx_purchase_payables", filename, content)
    if reused:
        return ImportResult(
            batch=batch,
            message="Arquivo de faturas de compra do Linx ja importado anteriormente.",
        )

    parsed_rows = parse_purchase_payable_rows(content)
    open_rows_by_reference: dict[str, ParsedPurchasePayableRow] = {}
    ignored_rows = 0
    for row in parsed_rows:
        if not _linx_purchase_payable_is_open(row):
            ignored_rows += 1
            continue
        source_reference = _linx_purchase_payable_source_reference(row)
        open_rows_by_reference.setdefault(source_reference, row)

    existing_titles = {
        title.source_reference: title
        for title in db.scalars(
            select(PurchasePayableTitle).where(
                PurchasePayableTitle.company_id == company.id,
                PurchasePayableTitle.source_reference.in_(list(open_rows_by_reference)),
            )
        )
    }

    new_rows_by_group: dict[tuple[str, str, str], list[tuple[str, ParsedPurchasePayableRow]]] = defaultdict(list)
    for source_reference, row in open_rows_by_reference.items():
        existing_title = existing_titles.get(source_reference)
        if existing_title is not None:
            existing_title.last_seen_batch_id = batch.id
            existing_title.issue_date = row.issue_date
            existing_title.due_date = row.due_date
            existing_title.status = _normalize_linx_purchase_status(row.status)
            existing_title.original_amount = row.original_amount
            existing_title.amount_with_charges = row.amount_with_charges
            continue
        new_rows_by_group[_linx_purchase_invoice_group_key(row)].append((source_reference, row))

    created_suppliers = 0
    created_invoices = 0
    created_installments = 0
    created_entries = 0

    for group_rows in new_rows_by_group.values():
        rows = [item[1] for item in group_rows]
        first_row = _sort_linx_purchase_rows(rows)[0]
        supplier, supplier_created = _get_or_create_supplier_for_linx_purchase(
            db,
            company.id,
            first_row.supplier_name,
        )
        if supplier_created:
            created_suppliers += 1
        supplier.has_purchase_invoices = True

        invoice = _find_matching_purchase_invoice_for_linx(db, company.id, supplier.id, first_row)
        if invoice is None:
            invoice = _create_linx_purchase_invoice(
                db,
                company=company,
                actor_user=actor_user,
                supplier=supplier,
                rows=rows,
            )
            created_invoices += 1

        for source_reference, row in sorted(
            group_rows,
            key=lambda item: (
                item[1].installment_number if item[1].installment_number is not None else 999,
                item[1].due_date or date.max,
            ),
        ):
            installment = _find_matching_purchase_installment_for_linx(invoice, row)
            if installment is None:
                installment = PurchaseInstallment(
                    company_id=company.id,
                    purchase_invoice_id=invoice.id,
                    installment_number=row.installment_number or (len(invoice.installments) + 1),
                    installment_label=row.installment_label,
                    due_date=row.due_date,
                    amount=_resolve_linx_purchase_payable_amount(row),
                    status=OPEN_STATUS,
                )
                db.add(installment)
                db.flush()
                invoice.installments.append(installment)
                created_installments += 1

            financial_entry = installment.financial_entry
            if financial_entry is None and installment.financial_entry_id:
                financial_entry = db.get(FinancialEntry, installment.financial_entry_id)
            if financial_entry is None:
                financial_entry = _create_linx_financial_entry_for_installment(
                    db,
                    company_id=company.id,
                    supplier=supplier,
                    invoice=invoice,
                    installment=installment,
                    row=row,
                    source_reference=source_reference,
                )
                created_entries += 1

            db.add(
                PurchasePayableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    last_seen_batch_id=batch.id,
                    source_reference=source_reference,
                    issue_date=row.issue_date,
                    due_date=row.due_date,
                    payable_code=row.payable_code,
                    company_code=row.company_code,
                    installment_label=row.installment_label,
                    installment_number=row.installment_number,
                    installments_total=row.installments_total,
                    original_amount=row.original_amount,
                    amount_with_charges=row.amount_with_charges,
                    supplier_name=row.supplier_name,
                    supplier_code=row.supplier_code,
                    document_number=row.document_number,
                    document_series=row.document_series,
                    status=_normalize_linx_purchase_status(row.status),
                    purchase_invoice_id=invoice.id,
                    purchase_installment_id=installment.id,
                    financial_entry_id=financial_entry.id,
                )
            )

    batch.records_total = len(parsed_rows)
    batch.records_valid = len(open_rows_by_reference)
    batch.records_invalid = ignored_rows
    batch.status = "processed"
    if ignored_rows:
        batch.error_summary = (
            f"{ignored_rows} linha(s) foram ignoradas por nao estarem em aberto."
        )

    db.commit()
    db.refresh(batch)

    message_parts = [
        "Faturas de compra do Linx sincronizadas.",
        f"{len(new_rows_by_group)} nota(s) nova(s) analisada(s).",
        f"{sum(len(items) for items in new_rows_by_group.values())} fatura(s) nova(s) incluida(s).",
    ]
    if not parsed_rows:
        message_parts.append("Nenhuma fatura encontrada na visao selecionada do Linx.")
    elif not open_rows_by_reference:
        message_parts.append("Nenhuma fatura em aberto encontrada no Linx.")
    if created_suppliers:
        message_parts.append(f"{created_suppliers} fornecedor(es) criado(s).")
    if created_entries:
        message_parts.append(f"{created_entries} lancamento(s) aberto(s) criado(s).")
    return ImportResult(batch=batch, message=" ".join(message_parts))


def sync_linx_purchase_payables_report(
    db: Session,
    company: Company,
    actor_user: User,
) -> ImportResult:
    filename, content = download_linx_purchase_payables_report(company)
    return import_linx_purchase_payables(db, company, filename, content, actor_user)


def sync_linx_purchase_payables(
    db: Session,
    company: Company,
    actor_user: User | None,
) -> ImportResult:
    settings = load_linx_api_settings(company)
    start_timestamp = int(
        db.scalar(
            select(func.max(PurchasePayableTitle.linx_row_timestamp)).where(
                PurchasePayableTitle.company_id == company.id,
                PurchasePayableTitle.linx_row_timestamp.is_not(None),
            )
        )
        or 0
    )

    response_bytes, raw_rows = _collect_linx_purchase_payable_api_rows(
        settings,
        start_timestamp=start_timestamp,
    )
    request_descriptor = json.dumps(
        {
            "method": LINX_PURCHASE_PAYABLES_API_METHOD,
            "source": LINX_PURCHASE_PAYABLES_API_SOURCE,
            "timestamp": start_timestamp,
            "start_date": LINX_PURCHASE_PAYABLES_API_FULL_LOAD_START,
        },
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    batch, reused = _create_import_batch(
        db,
        company.id,
        LINX_PURCHASE_PAYABLES_API_SOURCE,
        f"{LINX_PURCHASE_PAYABLES_API_SOURCE}.xml",
        request_descriptor + b"\n" + response_bytes,
    )
    if reused:
        return ImportResult(
            batch=batch,
            message="Sincronizacao de faturas de compra Linx ja processada anteriormente.",
        )

    exact_lookup, loose_lookup = _build_purchase_movement_lookup(db, company_id=company.id)
    normalized_by_code: dict[int, LinxApiPurchasePayableRow] = {}
    ignored_non_purchase = 0
    skipped_before_start = 0
    duplicate_rows = 0

    for raw_row in raw_rows:
        normalized = _normalize_linx_api_purchase_row(raw_row)
        if normalized is None:
            if (_clean_linx_api_text(raw_row.get("receber_pagar")) or "").upper() == "P":
                skipped_before_start += 1
            continue
        if not _row_matches_purchase_movement(
            normalized,
            exact_lookup=exact_lookup,
            loose_lookup=loose_lookup,
        ):
            ignored_non_purchase += 1
            continue
        previous = normalized_by_code.get(normalized.linx_code)
        if previous is not None:
            duplicate_rows += 1
            if int(normalized.row_timestamp or 0) <= int(previous.row_timestamp or 0):
                continue
        normalized_by_code[normalized.linx_code] = normalized

    existing_titles = {
        int(title.payable_code): title
        for title in db.scalars(
            select(PurchasePayableTitle).where(
                PurchasePayableTitle.company_id == company.id,
                PurchasePayableTitle.payable_code.in_([str(code) for code in normalized_by_code]),
            )
        )
        if title.payable_code and str(title.payable_code).isdigit()
    }

    created_suppliers = 0
    created_invoices = 0
    created_installments = 0
    created_entries = 0
    updated_titles = 0
    updated_entries = 0
    updated_installments = 0

    rows_by_group: dict[tuple[str, str, str], list[LinxApiPurchasePayableRow]] = defaultdict(list)
    existing_rows: list[tuple[PurchasePayableTitle, LinxApiPurchasePayableRow]] = []

    for row in normalized_by_code.values():
        existing_title = existing_titles.get(row.linx_code)
        if existing_title is not None:
            existing_rows.append((existing_title, row))
            continue
        rows_by_group[_linx_purchase_invoice_group_key(row)].append(row)

    for existing_title, row in existing_rows:
        existing_title.last_seen_batch_id = batch.id
        existing_title.issue_date = row.issue_date
        existing_title.due_date = row.due_date
        existing_title.company_code = row.company_code
        existing_title.installment_label = row.installment_label
        existing_title.installment_number = row.installment_number
        existing_title.installments_total = row.installments_total
        existing_title.original_amount = row.original_amount
        existing_title.amount_with_charges = row.amount_with_charges
        existing_title.supplier_name = row.supplier_name
        existing_title.supplier_code = row.supplier_code
        existing_title.document_number = row.document_number
        existing_title.document_series = row.document_series
        existing_title.status = row.status
        existing_title.linx_row_timestamp = row.row_timestamp
        updated_titles += 1

        installment = (
            db.get(PurchaseInstallment, existing_title.purchase_installment_id)
            if existing_title.purchase_installment_id
            else None
        )
        if installment is not None:
            installment.installment_number = row.installment_number or installment.installment_number
            installment.installment_label = row.installment_label
            installment.due_date = row.due_date
            installment.amount = _resolve_linx_purchase_payable_amount(row)
            updated_installments += 1

        entry = (
            db.get(FinancialEntry, existing_title.financial_entry_id)
            if existing_title.financial_entry_id
            else None
        )
        if entry is not None:
            total_amount = _resolve_linx_purchase_payable_amount(row)
            entry.notes = _build_linx_api_purchase_entry_note(row)
            entry.issue_date = row.issue_date
            entry.competence_date = row.due_date
            entry.due_date = row.due_date
            entry.total_amount = total_amount
            entry.principal_amount = total_amount
            entry.document_number = row.document_number
            if row.canceled or row.excluded:
                entry.status = "cancelled"
                entry.paid_amount = Decimal("0.00")
                entry.settled_at = None
            elif row.settled_date is not None:
                entry.status = "settled"
                entry.paid_amount = max(_money(row.paid_amount), total_amount)
                entry.settled_at = datetime.combine(row.settled_date, datetime.min.time(), tzinfo=timezone.utc)
            elif _money(row.paid_amount) > Decimal("0.00"):
                entry.status = "partial"
                entry.paid_amount = min(_money(row.paid_amount), total_amount)
                entry.settled_at = None
            else:
                entry.status = "open"
                entry.paid_amount = Decimal("0.00")
                entry.settled_at = None
            updated_entries += 1

    for grouped_rows in rows_by_group.values():
        rows = _sort_linx_purchase_rows(grouped_rows)
        first_row = rows[0]
        supplier, supplier_created = _get_or_create_supplier_for_linx_purchase(
            db,
            company.id,
            first_row.supplier_name,
        )
        if supplier_created:
            created_suppliers += 1
        supplier.has_purchase_invoices = True

        invoice = _find_matching_purchase_invoice_for_linx(db, company.id, supplier.id, first_row)
        if invoice is None:
            invoice = _create_linx_api_purchase_invoice(
                db,
                company=company,
                actor_user=actor_user,
                supplier=supplier,
                rows=rows,
            )
            created_invoices += 1

        for row in rows:
            installment = _find_matching_purchase_installment_for_linx(invoice, row)
            if installment is None:
                installment = PurchaseInstallment(
                    company_id=company.id,
                    purchase_invoice_id=invoice.id,
                    installment_number=row.installment_number or (len(invoice.installments) + 1),
                    installment_label=row.installment_label,
                    due_date=row.due_date,
                    amount=_resolve_linx_purchase_payable_amount(row),
                    status=OPEN_STATUS,
                )
                db.add(installment)
                db.flush()
                invoice.installments.append(installment)
                created_installments += 1

            financial_entry = installment.financial_entry
            if financial_entry is None and installment.financial_entry_id:
                financial_entry = db.get(FinancialEntry, installment.financial_entry_id)
            if financial_entry is None:
                financial_entry = _create_linx_api_financial_entry_for_installment(
                    db,
                    company_id=company.id,
                    supplier=supplier,
                    invoice=invoice,
                    installment=installment,
                    row=row,
                    source_reference=_build_linx_api_purchase_title_source_reference(row),
                )
                created_entries += 1

            db.add(
                PurchasePayableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    last_seen_batch_id=batch.id,
                    source_reference=_build_linx_api_purchase_title_source_reference(row),
                    issue_date=row.issue_date,
                    due_date=row.due_date,
                    payable_code=row.payable_code,
                    company_code=row.company_code,
                    installment_label=row.installment_label,
                    installment_number=row.installment_number,
                    installments_total=row.installments_total,
                    original_amount=row.original_amount,
                    amount_with_charges=row.amount_with_charges,
                    supplier_name=row.supplier_name,
                    supplier_code=row.supplier_code,
                    document_number=row.document_number,
                    document_series=row.document_series,
                    status=row.status,
                    linx_row_timestamp=row.row_timestamp,
                    purchase_invoice_id=invoice.id,
                    purchase_installment_id=installment.id,
                    financial_entry_id=financial_entry.id,
                )
            )

    batch.records_total = len(raw_rows)
    batch.records_valid = len(normalized_by_code)
    batch.records_invalid = ignored_non_purchase + skipped_before_start + duplicate_rows
    batch.status = "processed"
    errors: list[str] = []
    if ignored_non_purchase:
        errors.append(f"{ignored_non_purchase} titulo(s) a pagar nao eram nota de compra e foram ignorados.")
    if skipped_before_start:
        errors.append(
            f"{skipped_before_start} titulo(s) anteriores a "
            f"{LINX_PURCHASE_PAYABLES_API_MIN_ISSUE_DATE.strftime('%d/%m/%Y')} foram ignorados."
        )
    if duplicate_rows:
        errors.append(f"{duplicate_rows} linha(s) duplicadas foram consolidadas pelo maior timestamp.")
    batch.error_summary = " ".join(errors) or None

    db.commit()
    db.refresh(batch)

    message_parts = [
        "Faturas de compra via API Linx sincronizadas.",
        f"{created_invoices} nota(s) nova(s) analisada(s).",
        f"{created_installments} fatura(s) nova(s) incluida(s).",
    ]
    if updated_titles or updated_entries or updated_installments:
        message_parts.append(
            f"{updated_titles} titulo(s), {updated_installments} parcela(s) e {updated_entries} lancamento(s) atualizados."
        )
    if created_suppliers:
        message_parts.append(f"{created_suppliers} fornecedor(es) criado(s).")
    if created_entries:
        message_parts.append(f"{created_entries} lancamento(s) aberto(s) criado(s).")
    if not raw_rows:
        message_parts.append("Nenhuma fatura retornada pelo webservice da Linx.")
    elif not normalized_by_code:
        message_parts.append(
            "Nenhuma fatura de nota de compra encontrada a partir de "
            f"{LINX_PURCHASE_PAYABLES_API_MIN_ISSUE_DATE.strftime('%d/%m/%Y')}."
        )
    return ImportResult(batch=batch, message=" ".join(message_parts))


def cleanup_deleted_purchase_entry(
    db: Session,
    entry: FinancialEntry,
) -> None:
    installment = None
    if entry.purchase_installment_id:
        installment = db.get(PurchaseInstallment, entry.purchase_installment_id)
        if installment is not None and installment.company_id != entry.company_id:
            installment = None

    invoice = None
    if installment is not None:
        invoice = installment.invoice
    elif entry.purchase_invoice_id:
        invoice = db.get(PurchaseInvoice, entry.purchase_invoice_id)
        if invoice is not None and invoice.company_id != entry.company_id:
            invoice = None

    payable_title_matchers = [PurchasePayableTitle.financial_entry_id == entry.id]
    if entry.purchase_installment_id:
        payable_title_matchers.append(
            PurchasePayableTitle.purchase_installment_id == entry.purchase_installment_id
        )
    payable_title_filters = [
        PurchasePayableTitle.company_id == entry.company_id,
        or_(*payable_title_matchers),
    ]
    payable_titles = list(db.scalars(select(PurchasePayableTitle).where(*payable_title_filters)))
    for payable_title in payable_titles:
        if payable_title.financial_entry_id == entry.id:
            payable_title.financial_entry_id = None

    if installment is None:
        entry.purchase_invoice = None
        entry.purchase_installment = None
        entry.purchase_invoice_id = None
        entry.purchase_installment_id = None
        return

    if invoice is None or invoice.source_type != "linx_payables":
        if installment.financial_entry_id == entry.id:
            installment.financial_entry_id = None
        installment.financial_entry = None
        installment.status = OPEN_STATUS
        entry.purchase_invoice = None
        entry.purchase_installment = None
        entry.purchase_invoice_id = None
        entry.purchase_installment_id = None
        return

    for payable_title in payable_titles:
        if payable_title.purchase_installment_id == installment.id:
            payable_title.purchase_installment_id = None
            payable_title.purchase_invoice_id = None

    if installment.financial_entry_id == entry.id:
        installment.financial_entry_id = None
    installment.financial_entry = None
    entry.purchase_invoice = None
    entry.purchase_installment = None
    entry.purchase_installment_id = None
    entry.purchase_invoice_id = None
    db.delete(installment)
    db.flush()

    remaining_installments = list(
        db.scalars(
            select(PurchaseInstallment)
            .where(
                PurchaseInstallment.company_id == entry.company_id,
                PurchaseInstallment.purchase_invoice_id == invoice.id,
            )
            .order_by(PurchaseInstallment.installment_number.asc(), PurchaseInstallment.created_at.asc())
        )
    )
    remaining_total = _money(
        sum((Decimal(item.amount or 0) for item in remaining_installments), Decimal("0.00"))
    )
    linked_deliveries = list(
        db.scalars(
            select(PurchaseDelivery).where(
                PurchaseDelivery.company_id == entry.company_id,
                PurchaseDelivery.purchase_invoice_id == invoice.id,
                PurchaseDelivery.source_type == "linx_payables",
            )
        )
    )

    if remaining_installments:
        invoice.total_amount = remaining_total
        for delivery in linked_deliveries:
            delivery.amount = remaining_total
        return

    for payable_title in db.scalars(
        select(PurchasePayableTitle).where(
            PurchasePayableTitle.company_id == entry.company_id,
            PurchasePayableTitle.purchase_invoice_id == invoice.id,
        )
    ):
        payable_title.purchase_invoice_id = None
    for delivery in linked_deliveries:
        db.delete(delivery)
    purchase_plan = invoice.purchase_plan
    db.delete(invoice)
    _delete_orphan_imported_plan(db, purchase_plan)


def _delete_orphan_imported_plan(db: Session, plan: PurchasePlan | None) -> bool:
    if plan is None or plan.status != "imported":
        return False
    db.flush()
    invoice_count = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == plan.company_id,
            PurchaseInvoice.purchase_plan_id == plan.id,
        )
    )
    delivery_count = db.scalar(
        select(func.count(PurchaseDelivery.id)).where(
            PurchaseDelivery.company_id == plan.company_id,
            PurchaseDelivery.purchase_plan_id == plan.id,
        )
    )
    if invoice_count or delivery_count:
        return False
    for link in db.scalars(
        select(PurchasePlanSupplier).where(
            PurchasePlanSupplier.company_id == plan.company_id,
            PurchasePlanSupplier.plan_id == plan.id,
        )
    ):
        db.delete(link)
    db.delete(plan)
    return True


def reconcile_purchase_invoice_links(
    db: Session,
    *,
    company_id: str | None = None,
) -> int:
    stmt = select(PurchaseInvoice).options(
        joinedload(PurchaseInvoice.supplier),
        joinedload(PurchaseInvoice.collection),
        joinedload(PurchaseInvoice.purchase_plan).joinedload(PurchasePlan.collection),
        joinedload(PurchaseInvoice.purchase_plan).joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
        joinedload(PurchaseInvoice.purchase_plan).joinedload(PurchasePlan.supplier),
    )
    if company_id:
        stmt = stmt.where(PurchaseInvoice.company_id == company_id)

    repaired_count = 0
    invoices = list(db.execute(stmt).unique().scalars().all())
    for invoice in invoices:
        supplier = invoice.supplier
        if supplier is None:
            continue

        canonical_supplier = _find_matching_supplier(
            db,
            invoice.company_id,
            supplier_name=supplier.name,
            supplier_document=supplier.document_number,
            exclude_supplier_id=supplier.id,
        )
        if canonical_supplier and canonical_supplier.id != invoice.supplier_id:
            invoice.supplier_id = canonical_supplier.id
            supplier = canonical_supplier
            repaired_count += 1
            for delivery in db.scalars(
                select(PurchaseDelivery).where(
                    PurchaseDelivery.company_id == invoice.company_id,
                    PurchaseDelivery.purchase_invoice_id == invoice.id,
                )
            ):
                delivery.supplier_id = canonical_supplier.id
            for entry in db.scalars(
                select(FinancialEntry).where(
                    FinancialEntry.company_id == invoice.company_id,
                    FinancialEntry.purchase_invoice_id == invoice.id,
                    FinancialEntry.is_deleted.is_(False),
                )
            ):
                entry.supplier_id = canonical_supplier.id
                if not entry.counterparty_name or _strip_supplier_code_prefix(entry.counterparty_name) == _strip_supplier_code_prefix(invoice.supplier.name if invoice.supplier else ""):
                    entry.counterparty_name = canonical_supplier.name

        matched_plan = _find_matching_purchase_plan(
            db,
            invoice.company_id,
            supplier_id=supplier.id,
            collection_id=invoice.collection_id,
            season_phase=invoice.season_phase,
            issue_date=invoice.issue_date,
            exclude_plan_id=invoice.purchase_plan_id if invoice.purchase_plan and invoice.purchase_plan.status == "imported" else None,
        )
        if matched_plan and invoice.purchase_plan_id != matched_plan.id:
            previous_plan = invoice.purchase_plan
            invoice.purchase_plan_id = matched_plan.id
            repaired_count += 1
            for delivery in db.scalars(
                select(PurchaseDelivery).where(
                    PurchaseDelivery.company_id == invoice.company_id,
                    PurchaseDelivery.purchase_invoice_id == invoice.id,
                )
            ):
                delivery.purchase_plan_id = matched_plan.id
            if previous_plan is not None:
                _delete_orphan_imported_plan(db, previous_plan)

    if repaired_count:
        db.flush()
    return repaired_count


def ensure_purchase_installment_financial_entries(
    db: Session,
    *,
    company_id: str | None = None,
) -> int:
    stmt = select(PurchaseInstallment).where(PurchaseInstallment.financial_entry_id.is_(None)).options(
        joinedload(PurchaseInstallment.invoice).joinedload(PurchaseInvoice.supplier)
    )
    if company_id:
        stmt = stmt.where(PurchaseInstallment.company_id == company_id)

    repaired_count = 0
    installments = list(db.scalars(stmt))
    for installment in installments:
        invoice = installment.invoice
        supplier = invoice.supplier if invoice else None
        if invoice is None or supplier is None:
            continue

        existing_entry = db.scalar(
            select(FinancialEntry).where(
                FinancialEntry.company_id == installment.company_id,
                FinancialEntry.purchase_installment_id == installment.id,
                FinancialEntry.is_deleted.is_(False),
            )
        )
        if existing_entry is not None:
            purchase_category = _ensure_purchase_category(db, installment.company_id)
            existing_entry.supplier_id = invoice.supplier_id
            existing_entry.collection_id = invoice.collection_id
            existing_entry.season_phase = _normalize_season_phase(invoice.season_phase)
            existing_entry.purchase_invoice_id = invoice.id
            if not existing_entry.category_id:
                existing_entry.category_id = purchase_category.id
            if not existing_entry.counterparty_name:
                existing_entry.counterparty_name = supplier.name
            if not existing_entry.document_number and invoice.invoice_number:
                existing_entry.document_number = invoice.invoice_number
            installment.financial_entry_id = existing_entry.id
            repaired_count += 1
            continue

        _create_financial_entry_for_installment(
            db,
            company_id=installment.company_id,
            supplier=supplier,
            invoice=invoice,
            installment=installment,
        )
        repaired_count += 1

    if repaired_count:
        db.flush()
    category_repair_stmt = select(FinancialEntry).where(
        FinancialEntry.entry_type == "expense",
        FinancialEntry.source_system == "purchase_invoice",
        FinancialEntry.is_deleted.is_(False),
    )
    if company_id:
        category_repair_stmt = category_repair_stmt.where(FinancialEntry.company_id == company_id)

    for entry in db.scalars(category_repair_stmt):
        purchase_category = _ensure_purchase_category(db, entry.company_id)
        if entry.category_id != purchase_category.id:
            entry.category_id = purchase_category.id
            repaired_count += 1

    if repaired_count:
        db.flush()
    return repaired_count


def list_purchase_invoices(
    db: Session,
    company: Company,
    *,
    year: int | None = None,
    limit: int = 100,
) -> list[PurchaseInvoiceRead]:
    stmt = select(PurchaseInvoice).where(PurchaseInvoice.company_id == company.id)
    if year:
        stmt = stmt.where(
            or_(
                PurchaseInvoice.collection.has(CollectionSeason.season_year == year),
                and_(
                    PurchaseInvoice.collection_id.is_(None),
                    PurchaseInvoice.issue_date.is_not(None),
                    PurchaseInvoice.issue_date >= date(year, 1, 1),
                    PurchaseInvoice.issue_date <= date(year, 12, 31),
                ),
            )
        )
    invoices = (
        db.execute(
            stmt.order_by(PurchaseInvoice.issue_date.desc().nullslast(), PurchaseInvoice.created_at.desc())
            .limit(limit)
            .options(
                joinedload(PurchaseInvoice.brand),
                joinedload(PurchaseInvoice.supplier),
                joinedload(PurchaseInvoice.collection),
                joinedload(PurchaseInvoice.installments).joinedload(PurchaseInstallment.financial_entry),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [_serialize_invoice(db, item) for item in invoices]


def create_purchase_invoice(
    db: Session,
    company: Company,
    payload: PurchaseInvoiceCreate,
    actor_user: User,
    *,
    source_type: str = "text",
) -> PurchaseInvoiceRead:
    supplier = _find_or_create_supplier(
        db,
        company.id,
        supplier_id=payload.supplier_id,
        supplier_name=payload.supplier_name,
        supplier_document=None,
    )
    supplier.has_purchase_invoices = True
    brand = _validate_brand(db, company.id, payload.brand_id)
    if brand is None:
        brand = _brand_for_supplier(db, company.id, supplier.id)
    collection = _resolve_collection(db, company.id, payload.collection_id, payload.issue_date)

    if payload.nfe_key:
        existing = db.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.company_id == company.id,
                PurchaseInvoice.nfe_key == payload.nfe_key,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="Nota fiscal ja importada")
    elif payload.invoice_number:
        existing = db.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.company_id == company.id,
                PurchaseInvoice.supplier_id == supplier.id,
                PurchaseInvoice.invoice_number == payload.invoice_number,
                PurchaseInvoice.series == payload.series,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="Nota fiscal ja importada")

    payment_basis = supplier.payment_basis or "delivery"
    payment_term = payload.payment_term or supplier.default_payment_term
    season_phase = _normalize_season_phase(payload.season_phase)
    matched_plan = None
    if payload.purchase_plan_id is None:
        matched_plan = _find_matching_purchase_plan(
            db,
            company.id,
            supplier_id=supplier.id,
            collection_id=collection.id if collection else None,
            season_phase=payload.season_phase,
            issue_date=payload.issue_date,
        )
    plan_id = payload.purchase_plan_id or (matched_plan.id if matched_plan else None)
    invoice = PurchaseInvoice(
        company_id=company.id,
        brand_id=brand.id if brand else None,
        supplier_id=supplier.id,
        collection_id=collection.id if collection else None,
        purchase_plan_id=plan_id,
        invoice_number=payload.invoice_number,
        series=payload.series,
        nfe_key=_digits_only(payload.nfe_key),
        issue_date=payload.issue_date,
        entry_date=payload.entry_date,
        total_amount=_money(payload.total_amount),
        payment_description=payload.payment_description,
        payment_term=payment_term,
        payment_basis=payment_basis,
        season_phase=season_phase,
        raw_text=payload.raw_text,
        raw_xml=payload.raw_xml,
        source_type=source_type,
        status="open",
        notes=payload.notes,
    )
    db.add(invoice)
    db.flush()

    if not plan_id and payload.create_plan:
        plan = PurchasePlan(
            company_id=company.id,
            brand_id=brand.id if brand else None,
            supplier_id=supplier.id,
            collection_id=collection.id if collection else None,
            title=f"{supplier.name} - NF {payload.invoice_number or invoice.id[:8]}",
            order_date=payload.issue_date,
            expected_delivery_date=payload.entry_date,
            purchased_amount=_money(payload.total_amount),
            payment_term=payment_term,
            payment_basis=payment_basis,
            season_phase=season_phase,
            status="imported",
            notes=payload.notes,
        )
        db.add(plan)
        db.flush()
        invoice.purchase_plan_id = plan.id
        plan_id = plan.id

    db.add(
        PurchaseDelivery(
            company_id=company.id,
            brand_id=brand.id if brand else None,
            supplier_id=supplier.id,
            collection_id=collection.id if collection else None,
            purchase_plan_id=plan_id,
            purchase_invoice_id=invoice.id,
            delivery_date=payload.entry_date or payload.issue_date,
            amount=_money(payload.total_amount),
            season_phase=season_phase,
            source_type=source_type,
            source_reference=invoice.nfe_key or invoice.invoice_number,
            notes="Entrega inferida da nota fiscal",
        )
    )

    installments = payload.installments or _build_installments_from_term(
        payment_term,
        _money(payload.total_amount),
        payload.entry_date or payload.issue_date,
    )
    for item in installments:
        installment = PurchaseInstallment(
            company_id=company.id,
            purchase_invoice_id=invoice.id,
            installment_number=item.installment_number,
            installment_label=item.installment_label,
            due_date=item.due_date,
            amount=_money(item.amount),
            status=OPEN_STATUS,
        )
        db.add(installment)
        db.flush()
        _create_financial_entry_for_installment(
            db,
            company_id=company.id,
            supplier=supplier,
            invoice=invoice,
            installment=installment,
        )

    db.flush()
    invoice = (
        db.execute(
            select(PurchaseInvoice)
            .where(PurchaseInvoice.id == invoice.id)
            .options(
                joinedload(PurchaseInvoice.brand),
                joinedload(PurchaseInvoice.supplier),
                joinedload(PurchaseInvoice.collection),
                joinedload(PurchaseInvoice.installments).joinedload(PurchaseInstallment.financial_entry),
            )
        )
        .unique()
        .scalars()
        .first()
    )
    assert invoice is not None

    write_audit_log(
        db,
        action="create_purchase_invoice",
        entity_name="purchase_invoice",
        entity_id=invoice.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "supplier_name": supplier.name,
            "invoice_number": invoice.invoice_number,
            "total_amount": f"{invoice.total_amount:.2f}",
            "source_type": invoice.source_type,
        },
    )
    return _serialize_invoice(db, invoice)


def link_installment_to_entry(
    db: Session,
    company: Company,
    installment_id: str,
    financial_entry_id: str | None,
    actor_user: User,
) -> PurchaseInstallmentRead:
    installment = db.scalar(
        select(PurchaseInstallment)
        .where(PurchaseInstallment.id == installment_id, PurchaseInstallment.company_id == company.id)
        .options(
            joinedload(PurchaseInstallment.invoice).joinedload(PurchaseInvoice.supplier),
            joinedload(PurchaseInstallment.invoice).joinedload(PurchaseInvoice.brand),
            joinedload(PurchaseInstallment.invoice).joinedload(PurchaseInvoice.collection),
            joinedload(PurchaseInstallment.financial_entry),
        )
    )
    if installment is None:
        raise HTTPException(status_code=404, detail="Parcela nao encontrada")

    before_state = {"financial_entry_id": installment.financial_entry_id, "status": installment.status}
    installment.financial_entry_id = None
    if financial_entry_id:
        entry = db.get(FinancialEntry, financial_entry_id)
        if not entry or entry.company_id != company.id or entry.is_deleted:
            raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
        entry.supplier_id = installment.invoice.supplier_id
        entry.collection_id = installment.invoice.collection_id
        entry.season_phase = _normalize_season_phase(installment.invoice.season_phase)
        entry.purchase_invoice_id = installment.purchase_invoice_id
        entry.purchase_installment_id = installment.id
        if not entry.counterparty_name and installment.invoice.supplier:
            entry.counterparty_name = installment.invoice.supplier.name
        if not entry.document_number:
            entry.document_number = installment.invoice.invoice_number
        installment.financial_entry_id = entry.id
    db.flush()
    installment.status = _sync_installment_status(installment)
    db.flush()
    write_audit_log(
        db,
        action="link_purchase_installment",
        entity_name="purchase_installment",
        entity_id=installment.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"financial_entry_id": installment.financial_entry_id, "status": installment.status},
    )
    return _serialize_installment(db, installment)


def _apply_filters_to_invoice_stmt(stmt, filters: PurchasePlanningFilters):
    if filters.year:
        stmt = stmt.where(
            or_(
                PurchaseInvoice.collection.has(CollectionSeason.season_year == filters.year),
                and_(
                    PurchaseInvoice.collection_id.is_(None),
                    PurchaseInvoice.issue_date.is_not(None),
                    PurchaseInvoice.issue_date >= date(filters.year, 1, 1),
                    PurchaseInvoice.issue_date <= date(filters.year, 12, 31),
                ),
            )
        )
    if filters.brand_id:
        stmt = stmt.where(PurchaseInvoice.brand_id == filters.brand_id)
    if filters.supplier_id:
        stmt = stmt.where(PurchaseInvoice.supplier_id == filters.supplier_id)
    if filters.collection_id:
        stmt = stmt.where(PurchaseInvoice.collection_id == filters.collection_id)
    if filters.status:
        stmt = stmt.where(PurchaseInvoice.status == filters.status)
    return stmt


def _apply_filters_to_plan_stmt(stmt, filters: PurchasePlanningFilters):
    if filters.year:
        stmt = stmt.where(
            or_(
                PurchasePlan.collection.has(CollectionSeason.season_year == filters.year),
                and_(
                    PurchasePlan.collection_id.is_(None),
                    PurchasePlan.order_date.is_not(None),
                    PurchasePlan.order_date >= date(filters.year, 1, 1),
                    PurchasePlan.order_date <= date(filters.year, 12, 31),
                ),
            )
        )
    if filters.brand_id:
        stmt = stmt.where(PurchasePlan.brand_id == filters.brand_id)
    if filters.supplier_id:
        stmt = stmt.where(
            or_(
                PurchasePlan.supplier_id == filters.supplier_id,
                PurchasePlan.id.in_(
                    select(PurchasePlanSupplier.plan_id).where(
                        PurchasePlanSupplier.supplier_id == filters.supplier_id,
                    )
                ),
            )
        )
    if filters.collection_id:
        stmt = stmt.where(PurchasePlan.collection_id == filters.collection_id)
    if filters.status:
        normalized_status = normalize_open_alias(filters.status)
        if normalized_status == OPEN_STATUS:
            stmt = stmt.where(PurchasePlan.status.in_(OPEN_STATUS_QUERY_VALUES))
        else:
            stmt = stmt.where(PurchasePlan.status == normalized_status)
    return stmt


def _apply_filters_to_delivery_stmt(stmt, filters: PurchasePlanningFilters):
    if filters.year:
        stmt = stmt.where(
            or_(
                PurchaseDelivery.collection.has(CollectionSeason.season_year == filters.year),
                and_(
                    PurchaseDelivery.collection_id.is_(None),
                    PurchaseDelivery.delivery_date.is_not(None),
                    PurchaseDelivery.delivery_date >= date(filters.year, 1, 1),
                    PurchaseDelivery.delivery_date <= date(filters.year, 12, 31),
                ),
            )
        )
    if filters.brand_id:
        stmt = stmt.where(PurchaseDelivery.brand_id == filters.brand_id)
    if filters.supplier_id:
        stmt = stmt.where(PurchaseDelivery.supplier_id == filters.supplier_id)
    if filters.collection_id:
        stmt = stmt.where(PurchaseDelivery.collection_id == filters.collection_id)
    return stmt


def _apply_filters_to_entry_stmt(stmt, filters: PurchasePlanningFilters, db: Session, company: Company):
    if filters.year:
        stmt = stmt.where(
            or_(
                FinancialEntry.collection.has(CollectionSeason.season_year == filters.year),
                and_(
                    FinancialEntry.collection_id.is_(None),
                    FinancialEntry.competence_date.is_not(None),
                    FinancialEntry.competence_date >= date(filters.year, 1, 1),
                    FinancialEntry.competence_date <= date(filters.year, 12, 31),
                ),
            )
        )
    if filters.brand_id:
        brand_supplier_ids = _brand_supplier_ids(db, company.id, filters.brand_id)
        if not brand_supplier_ids:
            stmt = stmt.where(FinancialEntry.supplier_id == "__no_supplier__")
        else:
            stmt = stmt.where(FinancialEntry.supplier_id.in_(brand_supplier_ids))
    if filters.supplier_id:
        stmt = stmt.where(FinancialEntry.supplier_id == filters.supplier_id)
    if filters.collection_id:
        stmt = stmt.where(FinancialEntry.collection_id == filters.collection_id)
    if filters.status:
        normalized_status = normalize_open_alias(filters.status)
        if normalized_status == OPEN_STATUS:
            stmt = stmt.where(FinancialEntry.status.in_([OPEN_STATUS, "planned", "partial"]))
        else:
            stmt = stmt.where(FinancialEntry.status == normalized_status)
    return stmt


def _group_key(brand_name: str | None, collection_name: str | None) -> tuple[str, str]:
    return brand_name or "Sem marca", collection_name or "Sem colecao"


def _build_purchase_cost_totals(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
    company_collections: list[CollectionSeason],
) -> list[PurchasePlanningCostRow]:
    join_condition = and_(
        LinxProduct.company_id == LinxMovement.company_id,
        LinxProduct.linx_code == LinxMovement.product_code,
    )
    stmt = (
        select(
            LinxMovement.movement_type,
            LinxMovement.launch_date,
            LinxMovement.issue_date,
            LinxMovement.total_amount,
            LinxMovement.net_amount,
            LinxProduct.supplier_name,
        )
        .select_from(LinxMovement)
        .outerjoin(LinxProduct, join_condition)
        .where(
            LinxMovement.company_id == company.id,
            LinxMovement.movement_group == "purchase",
        )
    )

    if filters.year:
        period_start = datetime.combine(date(filters.year, 1, 1), datetime.min.time())
        period_end = datetime.combine(date(filters.year, 12, 31), datetime.max.time())
        stmt = stmt.where(
            func.coalesce(LinxMovement.launch_date, LinxMovement.issue_date) >= period_start,
            func.coalesce(LinxMovement.launch_date, LinxMovement.issue_date) <= period_end,
        )

    wanted_collection_id = None
    if filters.collection_id:
        collection = db.get(CollectionSeason, filters.collection_id)
        if collection and collection.company_id == company.id:
            wanted_collection_id = collection.id

    wanted_supplier_keys: set[str] | None = None
    if filters.supplier_id:
        supplier = db.get(Supplier, filters.supplier_id)
        if supplier and supplier.company_id == company.id:
            wanted_supplier_keys = _supplier_lookup_keys(supplier.name)

    totals_by_key: dict[tuple[str, str], dict[str, Decimal]] = {}

    for movement_type, launch_date, issue_date, total_amount, net_amount, supplier_name in db.execute(stmt).all():
        reference_date = launch_date or issue_date
        reporting_collection = _resolve_reporting_collection_by_date(company_collections, reference_date)
        if wanted_collection_id and (reporting_collection is None or reporting_collection.id != wanted_collection_id):
            continue

        collection_name = _collection_name(reporting_collection) or "Sem colecao"
        resolved_supplier_name = str(supplier_name or "Sem fornecedor")
        normalized_supplier_keys = _supplier_lookup_keys(resolved_supplier_name)
        if wanted_supplier_keys and not (normalized_supplier_keys & wanted_supplier_keys):
            continue

        amount = _money(Decimal(total_amount if total_amount is not None else (net_amount or 0)))
        if amount <= 0:
            continue

        group_key = (collection_name, resolved_supplier_name)
        bucket = totals_by_key.setdefault(
            group_key,
            {
                "purchase_cost_total": Decimal("0.00"),
                "purchase_return_cost_total": Decimal("0.00"),
            },
        )
        if movement_type == "purchase":
            bucket["purchase_cost_total"] += amount
        elif movement_type == "purchase_return":
            bucket["purchase_return_cost_total"] += amount

    rows: list[PurchasePlanningCostRow] = []
    for (collection_name, supplier_name), totals in sorted(
        totals_by_key.items(),
        key=lambda item: (
            item[0][0].lower(),
            item[0][1].lower(),
        ),
    ):
        purchase_amount = _money(totals["purchase_cost_total"])
        purchase_return_amount = _money(totals["purchase_return_cost_total"])
        if purchase_amount <= 0 and purchase_return_amount <= 0:
            continue
        rows.append(
            PurchasePlanningCostRow(
                collection_name=collection_name,
                supplier_name=supplier_name,
                purchase_cost_total=purchase_amount,
                purchase_return_cost_total=purchase_return_amount,
                net_cost_total=_money(purchase_amount - purchase_return_amount),
            )
        )
    return rows


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, month, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _remaining_billing_months(today: date, billing_deadline: date | None) -> list[date]:
    if billing_deadline is None or billing_deadline < today:
        return [_last_day_of_month(today.year, today.month)]

    month_ends: list[date] = []
    cursor = date(today.year, today.month, 1)
    end_cursor = date(billing_deadline.year, billing_deadline.month, 1)
    while cursor <= end_cursor:
        month_ends.append(_last_day_of_month(cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return month_ends


def _remaining_collection_month_ends(
    *,
    today: date,
    collection_start: date | None,
    collection_end: date | None,
) -> list[date]:
    if collection_start is None or collection_end is None or collection_end < today:
        return []

    effective_start = max(today, collection_start)
    cursor = date(effective_start.year, effective_start.month, 1)
    end_cursor = date(collection_end.year, collection_end.month, 1)
    month_ends: list[date] = []
    while cursor <= end_cursor:
        month_ends.append(_last_day_of_month(cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return month_ends


def _simulate_remaining_purchase_installments(
    *,
    amount_to_receive: Decimal,
    payment_term: str | None,
    collection_start: date | None,
    collection_end: date | None,
    today: date,
) -> list[PurchaseInstallmentDraft]:
    amount_to_receive = _money(amount_to_receive)
    if amount_to_receive <= 0:
        return []

    month_ends = _remaining_collection_month_ends(
        today=today,
        collection_start=collection_start,
        collection_end=collection_end,
    )
    if not month_ends:
        return []

    remaining = amount_to_receive
    simulated: list[PurchaseInstallmentDraft] = []
    month_count = len(month_ends)
    for index, month_end in enumerate(month_ends, start=1):
        batch_amount = (
            _money(amount_to_receive / Decimal(month_count))
            if index < month_count
            else remaining
        )
        remaining = _money(remaining - batch_amount)
        batch_installments = _build_installments_from_term(payment_term, batch_amount, month_end) or [
            PurchaseInstallmentDraft(
                installment_number=index,
                installment_label=f"{index}/{month_count}",
                due_date=month_end,
                amount=batch_amount,
            )
        ]
        simulated.extend(batch_installments)
    return simulated


def _build_plan_linx_received_totals(
    db: Session,
    company_id: str,
    plans: list[PurchasePlan],
    *,
    company_collections: list[CollectionSeason],
    today: date,
) -> dict[str, Decimal]:
    eligible_plans = [plan for plan in plans if plan.collection and not _is_past_collection(plan.collection, today=today)]
    if not eligible_plans:
        return {}

    min_period_start = min(plan.collection.start_date for plan in eligible_plans if plan.collection)
    max_period_end = max(plan.collection.end_date for plan in eligible_plans if plan.collection)
    join_condition = and_(
        LinxProduct.company_id == LinxMovement.company_id,
        LinxProduct.linx_code == LinxMovement.product_code,
    )
    rows = db.execute(
        select(
            LinxMovement.movement_type,
            LinxMovement.launch_date,
            LinxMovement.issue_date,
            LinxMovement.total_amount,
            LinxMovement.net_amount,
            LinxProduct.supplier_name,
        )
        .select_from(LinxMovement)
        .outerjoin(LinxProduct, join_condition)
        .where(
            LinxMovement.company_id == company_id,
            LinxMovement.movement_group == "purchase",
            LinxMovement.movement_type == "purchase",
            func.coalesce(LinxMovement.launch_date, LinxMovement.issue_date) >= datetime.combine(min_period_start, datetime.min.time()),
            func.coalesce(LinxMovement.launch_date, LinxMovement.issue_date) <= datetime.combine(max_period_end, datetime.max.time()),
        )
    ).all()

    movement_totals_by_group: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    for movement_type, launch_date, issue_date, total_amount, net_amount, supplier_name in rows:
        reference_date = launch_date or issue_date
        reporting_collection = _resolve_reporting_collection_by_date(company_collections, reference_date)
        if reporting_collection is None:
            continue
        resolved_supplier_name = str(supplier_name or "Sem fornecedor")
        amount = _money(Decimal(total_amount if total_amount is not None else (net_amount or 0)))
        if amount <= 0:
            continue
        if movement_type != "purchase":
            continue
        movement_totals_by_group[(reporting_collection.id, resolved_supplier_name)] += amount

    received_by_plan_id: dict[str, Decimal] = {}
    for plan in eligible_plans:
        assert plan.collection is not None
        supplier_keys = {
            lookup_key
            for supplier in _plan_suppliers(plan)
            for lookup_key in _supplier_lookup_keys(supplier.name)
        }
        if not supplier_keys:
            received_by_plan_id[plan.id] = Decimal("0.00")
            continue

        received_total = Decimal("0.00")
        for (collection_id, supplier_name), total in movement_totals_by_group.items():
            if collection_id != plan.collection.id:
                continue
            if _supplier_lookup_keys(supplier_name) & supplier_keys:
                received_total += total
        received_by_plan_id[plan.id] = _money(max(received_total, Decimal("0.00")))
    return received_by_plan_id


def _build_purchase_forecast_installments(
    plans: list[PurchasePlan],
    plan_received_totals: dict[str, Decimal],
    *,
    today: date,
) -> list[PurchaseInstallmentDraft]:
    simulated_installments: list[PurchaseInstallmentDraft] = []
    for plan in plans:
        if plan.collection is None or _is_past_collection(plan.collection, today=today):
            continue
        received_amount = _money(plan_received_totals.get(plan.id, Decimal("0.00")))
        amount_to_receive = _money(max(_money(plan.purchased_amount) - received_amount, Decimal("0.00")))
        payment_term = (plan.brand.default_payment_term if plan.brand and plan.brand.default_payment_term else None) or plan.payment_term
        simulated_installments.extend(
            _simulate_remaining_purchase_installments(
                amount_to_receive=amount_to_receive,
                payment_term=payment_term,
                collection_start=plan.collection.start_date,
                collection_end=plan.collection.end_date,
                today=today,
            )
        )
    return simulated_installments


def _add_monthly_projection_amount(
    monthly_projection: dict[str, dict[str, Decimal]],
    *,
    due_date: date | None,
    planned_amount: Decimal,
    linked_payment: Decimal = Decimal("0.00"),
) -> None:
    if due_date is None:
        return
    reference = _month_key(due_date)
    monthly_projection[reference]["planned_outflows"] += _money(planned_amount)
    monthly_projection[reference]["linked_payments"] += _money(max(linked_payment, Decimal("0.00")))


def _serialize_monthly_projection(
    monthly_projection: dict[str, dict[str, Decimal]],
) -> list[PurchasePlanningMonthlyProjection]:
    return [
        PurchasePlanningMonthlyProjection(
            reference=reference,
            planned_outflows=_money(values["planned_outflows"]),
            linked_payments=_money(values["linked_payments"]),
            open_balance=_money(max(values["planned_outflows"] - values["linked_payments"], Decimal("0.00"))),
        )
        for reference, values in sorted(monthly_projection.items())
    ]


def _query_sales_and_profit_by_brand_collection(
    db: Session,
    company_id: str,
    company_collections: list[CollectionSeason],
) -> dict[tuple[str, str], dict[str, Decimal]]:
    """
    Agrega vendas e custo total por marca e coleção do LinxMovement.
    Retorna {(brand_name, collection_name): {"sold_total": Decimal, "cost_total": Decimal}}
    """
    reference_date = func.coalesce(LinxMovement.launch_date, LinxMovement.issue_date)
    collection_match_cases = [
        (
            and_(
                reference_date >= datetime.combine(collection.start_date, datetime.min.time()),
                reference_date <= datetime.combine(collection.end_date, datetime.max.time()),
            ),
            _collection_name(collection) or collection.name,
        )
        for collection in company_collections
    ]
    collection_name_expr = (
        case(*collection_match_cases, else_=literal("Sem colecao"))
        if collection_match_cases
        else literal("Sem colecao")
    ).label("collection_name")
    supplier_brand_lookup = _build_supplier_brand_name_lookup(db, company_id)
    join_condition = and_(
        LinxProduct.company_id == LinxMovement.company_id,
        LinxProduct.linx_code == LinxMovement.product_code,
    )
    rows = db.execute(
        select(
            LinxProduct.supplier_name,
            collection_name_expr,
            func.sum(
                case(
                    (LinxMovement.movement_type == "sale", func.coalesce(LinxMovement.net_amount, 0)),
                    (LinxMovement.movement_type == "sale_return", -func.coalesce(LinxMovement.net_amount, 0)),
                    else_=0,
                )
            ).label("sold_total"),
            func.sum(
                case(
                    (LinxMovement.movement_type == "sale", func.coalesce(LinxMovement.cost_price, 0) * func.coalesce(LinxMovement.quantity, 0)),
                    (LinxMovement.movement_type == "sale_return", -(func.coalesce(LinxMovement.cost_price, 0) * func.coalesce(LinxMovement.quantity, 0))),
                    else_=0,
                )
            ).label("cost_total"),
        )
        .join(LinxProduct, join_condition)
        .where(
            LinxMovement.company_id == company_id,
            LinxMovement.movement_group == "sale",
            LinxMovement.canceled.is_(False),
            LinxMovement.excluded.is_(False),
        )
        .group_by(LinxProduct.supplier_name, collection_name_expr)
    ).all()
    result = {}
    for row in rows:
        resolved_brand = next(
            (
                supplier_brand_lookup[lookup_key]
                for lookup_key in _supplier_lookup_keys(row.supplier_name)
                if lookup_key in supplier_brand_lookup
            ),
            None,
        )
        if not resolved_brand:
            continue
        brand = resolved_brand.strip()
        collection = (row.collection_name or "Sem colecao").strip()
        
        # Normalization to handle Viviane/Tricot/Veste variants
        norm_brand = _normalize_reporting_brand_name(brand)
            
        key = (norm_brand, normalize_label(collection))
        if key not in result:
            result[key] = {
                "sold_total": Decimal("0.00"),
                "cost_total": Decimal("0.00"),
            }
        result[key]["sold_total"] += Decimal(row.sold_total or 0)
        result[key]["cost_total"] += Decimal(row.cost_total or 0)
    return result


def build_purchase_planning_overview(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
    *,
    mode: str = "summary",
) -> PurchasePlanningOverview:
    filters = _resolve_effective_purchase_planning_filters(db, company.id, filters)
    planning_mode = normalize_label(mode) == "planning"
    today = _today()
    company_collections = list(
        db.scalars(
            select(CollectionSeason)
            .where(CollectionSeason.company_id == company.id)
            .order_by(CollectionSeason.start_date.desc(), CollectionSeason.created_at.desc())
        )
    )
    supplier_brand_lookup: dict[str, tuple[str, str]] = {}
    for supplier_id, brand_id, brand_name in db.execute(
        select(PurchaseBrandSupplier.supplier_id, PurchaseBrand.id, PurchaseBrand.name)
        .join(PurchaseBrand, PurchaseBrand.id == PurchaseBrandSupplier.brand_id)
        .where(
            PurchaseBrandSupplier.company_id == company.id,
        )
        .order_by(PurchaseBrand.created_at.asc(), PurchaseBrandSupplier.created_at.asc())
    ):
        supplier_brand_lookup.setdefault(str(supplier_id), (str(brand_id), str(brand_name)))

    plan_stmt = _apply_filters_to_plan_stmt(
        select(PurchasePlan)
        .where(PurchasePlan.company_id == company.id)
        .options(
            joinedload(PurchasePlan.brand),
            joinedload(PurchasePlan.supplier),
            joinedload(PurchasePlan.collection),
            joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
        ),
        filters,
    )
    invoice_options = [
        joinedload(PurchaseInvoice.brand),
        joinedload(PurchaseInvoice.supplier),
        joinedload(PurchaseInvoice.collection),
    ]
    if not planning_mode:
        invoice_options.append(joinedload(PurchaseInvoice.installments).joinedload(PurchaseInstallment.financial_entry))
    invoice_stmt = _apply_filters_to_invoice_stmt(
        select(PurchaseInvoice)
        .where(PurchaseInvoice.company_id == company.id)
        .options(*invoice_options),
        filters,
    )
    delivery_stmt = _apply_filters_to_delivery_stmt(
        select(PurchaseDelivery)
        .where(PurchaseDelivery.company_id == company.id)
        .options(joinedload(PurchaseDelivery.brand), joinedload(PurchaseDelivery.supplier), joinedload(PurchaseDelivery.collection)),
        filters,
    )
    entry_stmt = _apply_filters_to_entry_stmt(
        select(FinancialEntry)
        .where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.entry_type == "expense",
            FinancialEntry.is_deleted.is_(False),
            or_(
                FinancialEntry.supplier_id.is_not(None),
                FinancialEntry.collection_id.is_not(None),
                FinancialEntry.purchase_invoice_id.is_not(None),
                FinancialEntry.purchase_installment_id.is_not(None),
            ),
        )
        .options(
            joinedload(FinancialEntry.supplier),
            joinedload(FinancialEntry.collection),
            joinedload(FinancialEntry.purchase_invoice),
        ),
        filters,
        db,
        company,
    )

    ordered_plan_stmt = plan_stmt.order_by(PurchasePlan.order_date.desc().nullslast(), PurchasePlan.created_at.desc())
    if not planning_mode:
        ordered_plan_stmt = ordered_plan_stmt.limit(50)
    plans = db.execute(ordered_plan_stmt).unique().scalars().all()
    ordered_invoice_stmt = invoice_stmt.order_by(PurchaseInvoice.issue_date.desc().nullslast(), PurchaseInvoice.created_at.desc())
    if not planning_mode:
        ordered_invoice_stmt = ordered_invoice_stmt.limit(50)
    invoices = db.execute(ordered_invoice_stmt).unique().scalars().all()
    deliveries = list(db.scalars(delivery_stmt))
    entries = list(db.scalars(entry_stmt))
    plan_financial_totals, ungrouped_suppliers = _build_plan_financial_totals(db, company.id, plans)
    cost_totals = _build_purchase_cost_totals(db, company, filters, company_collections)
    season_totals = _build_supplier_season_totals(db, company.id)
    cashflow_plans = _filter_cashflow_plans(db, company.id, plans)
    plan_linx_received_totals = _build_plan_linx_received_totals(
        db,
        company.id,
        cashflow_plans,
        company_collections=company_collections,
        today=today,
    )
    simulated_installments = _build_purchase_forecast_installments(
        cashflow_plans,
        plan_linx_received_totals,
        today=today,
    )
    supplier_lookup_by_key: dict[str, Supplier] = {}
    for supplier in db.scalars(select(Supplier).where(Supplier.company_id == company.id)):
        for lookup_key in _supplier_lookup_keys(supplier.name):
            supplier_lookup_by_key.setdefault(lookup_key, supplier)
    collection_lookup_by_key = {
        _normalize_collection_lookup_key(_collection_name(collection) or collection.name): collection
        for collection in company_collections
    }

    sales_data = _query_sales_and_profit_by_brand_collection(db, company.id, company_collections)
    aggregates: dict[tuple[str, str], dict[str, Decimal | str | list[str] | date | None]] = {}

    def ensure_row(
        brand_id: str | None,
        brand_name: str | None,
        collection_id: str | None,
        collection_name: str | None,
        season_year: int | None = None,
        season_type: str | None = None,
    ) -> dict[str, Decimal | str | list[str] | date | None]:
        key = _group_key(brand_name, collection_name)
        if key not in aggregates:
            aggregates[key] = {
                "plan_id": None,
                "brand_id": brand_id,
                "brand_name": key[0],
                "supplier_ids": [],
                "collection_id": collection_id,
                "collection_name": key[1],
                "season_year": season_year,
                "season_type": _normalize_season_type(season_type),
                "season_label": collection_name,
                "billing_deadline": None,
                "payment_term": None,
                "status": None,
                "order_date": None,
                "expected_delivery_date": None,
                "supplier_names": [],
                "purchased_total": Decimal("0.00"),
                "returns_total": Decimal("0.00"),
                "received_total": Decimal("0.00"),
                "delivered_total": Decimal("0.00"),
                "launched_financial_total": Decimal("0.00"),
                "paid_total": Decimal("0.00"),
                "outstanding_payable_total": Decimal("0.00"),
                "sold_total": Decimal("0.00"),
                "profit_margin": Decimal("0.00"),
            }
            # Inject sales data
            norm_brand = _normalize_reporting_brand_name(key[0])
            norm_coll = normalize_label(key[1])
            s_data = sales_data.get((norm_brand, norm_coll))
            if s_data:
                aggregates[key]["sold_total"] = s_data["sold_total"]
        return aggregates[key]

    def attach_supplier(
        row: dict[str, Decimal | str | list[str] | date | None],
        supplier_name: str | None,
        supplier_id: str | None = None,
    ) -> None:
        if supplier_id:
            supplier_ids = row["supplier_ids"]
            assert isinstance(supplier_ids, list)
            if supplier_id not in supplier_ids:
                supplier_ids.append(supplier_id)
        if not supplier_name:
            return
        supplier_names = row["supplier_names"]
        assert isinstance(supplier_names, list)
        if supplier_name not in supplier_names:
            supplier_names.append(supplier_name)

    def attach_plan_metadata(
        row: dict[str, Decimal | str | list[str] | date | None],
        *,
        plan_id: str | None = None,
        billing_deadline: date | None = None,
        payment_term: str | None = None,
        status: str | None = None,
        order_date: date | None = None,
        expected_delivery_date: date | None = None,
    ) -> None:
        if plan_id and not row["plan_id"]:
            row["plan_id"] = plan_id
        if billing_deadline and not row["billing_deadline"]:
            row["billing_deadline"] = billing_deadline
        if payment_term and not row["payment_term"]:
            row["payment_term"] = payment_term
        if status and not row["status"]:
            row["status"] = status
        if order_date and not row["order_date"]:
            row["order_date"] = order_date
        if expected_delivery_date and not row["expected_delivery_date"]:
            row["expected_delivery_date"] = expected_delivery_date

    def resolve_brand_id_from_supplier(supplier_id: str | None, fallback_id: str | None = None) -> str | None:
        if supplier_id and supplier_id in supplier_brand_lookup:
            return supplier_brand_lookup[supplier_id][0]
        return fallback_id

    def resolve_brand_name_from_supplier(supplier_id: str | None, fallback_name: str | None = None) -> str | None:
        if supplier_id and supplier_id in supplier_brand_lookup:
            return supplier_brand_lookup[supplier_id][1]
        return fallback_name

    def resolve_reporting_collection(
        explicit_collection: CollectionSeason | None,
        reference_date: date | None,
    ) -> CollectionSeason | None:
        if reference_date is not None:
            for collection in company_collections:
                if collection.start_date <= reference_date <= collection.end_date:
                    return collection
        return explicit_collection

    for plan in plans:
        linked_suppliers = _plan_suppliers(plan)
        primary_supplier = linked_suppliers[0] if linked_suppliers else None
        row = ensure_row(
            plan.brand_id if plan.brand else resolve_brand_id_from_supplier(primary_supplier.id if primary_supplier else plan.supplier_id),
            plan.brand.name if plan.brand else resolve_brand_name_from_supplier(primary_supplier.id if primary_supplier else plan.supplier_id),
            plan.collection_id,
            _collection_name(plan.collection),
            plan.collection.season_year if plan.collection else None,
            plan.collection.season_type if plan.collection else None,
        )
        for supplier in linked_suppliers:
            attach_supplier(row, supplier.name, supplier.id)
        attach_plan_metadata(
            row,
            plan_id=plan.id,
            billing_deadline=plan.collection.end_date if plan.collection else None,
            payment_term=(plan.brand.default_payment_term if plan.brand and plan.brand.default_payment_term else None) or plan.payment_term,
            status=plan.status,
            order_date=plan.order_date,
            expected_delivery_date=plan.expected_delivery_date,
        )
        row["purchased_total"] = Decimal(row["purchased_total"]) + _money(plan.purchased_amount)
        row["outstanding_payable_total"] = Decimal(row["outstanding_payable_total"]) + _money(
            plan_financial_totals.get(plan.id, {}).get("amount_to_receive")
        )

    for delivery in deliveries:
        reporting_collection = resolve_reporting_collection(delivery.collection, delivery.delivery_date)
        row = ensure_row(
            delivery.brand_id if delivery.brand else resolve_brand_id_from_supplier(delivery.supplier_id),
            delivery.brand.name if delivery.brand else resolve_brand_name_from_supplier(delivery.supplier_id),
            reporting_collection.id if reporting_collection else delivery.collection_id,
            _collection_name(reporting_collection) or _collection_name(delivery.collection),
            reporting_collection.season_year if reporting_collection else (delivery.collection.season_year if delivery.collection else None),
            reporting_collection.season_type if reporting_collection else (delivery.collection.season_type if delivery.collection else None),
        )
        attach_supplier(row, delivery.supplier.name if delivery.supplier else None, delivery.supplier_id)
        attach_plan_metadata(
            row,
            billing_deadline=reporting_collection.end_date if reporting_collection else (delivery.collection.end_date if delivery.collection else None),
        )
        row["delivered_total"] = Decimal(row["delivered_total"]) + _money(delivery.amount)

    for entry in entries:
        if not _is_purchase_entry(entry):
            continue
        entry_supplier_id = entry.supplier_id or (entry.purchase_invoice.supplier_id if entry.purchase_invoice else None)
        entry_supplier_name = entry.supplier.name if entry.supplier else None
        reporting_collection = resolve_reporting_collection(entry.collection, entry.issue_date or entry.competence_date or entry.due_date)
        row = ensure_row(
            resolve_brand_id_from_supplier(entry_supplier_id),
            resolve_brand_name_from_supplier(entry_supplier_id),
            reporting_collection.id if reporting_collection else entry.collection_id,
            _collection_name(reporting_collection) or _collection_name(entry.collection),
            reporting_collection.season_year if reporting_collection else (entry.collection.season_year if entry.collection else None),
            reporting_collection.season_type if reporting_collection else (entry.collection.season_type if entry.collection else None),
        )
        attach_supplier(row, entry_supplier_name, entry_supplier_id)
        row["launched_financial_total"] = Decimal(row["launched_financial_total"]) + _money(entry.total_amount)
        row["paid_total"] = Decimal(row["paid_total"]) + _money(entry.paid_amount)
        if entry.issue_date is not None:
            received_collection = resolve_reporting_collection(entry.collection, entry.issue_date)
            received_row = ensure_row(
                resolve_brand_id_from_supplier(entry_supplier_id),
                resolve_brand_name_from_supplier(entry_supplier_id),
                received_collection.id if received_collection else entry.collection_id,
                _collection_name(received_collection) or _collection_name(entry.collection),
                received_collection.season_year if received_collection else (received_collection.season_year if received_collection else None),
                received_collection.season_type if received_collection else (received_collection.season_type if received_collection else None),
            )
            attach_supplier(received_row, entry_supplier_name, entry_supplier_id)
            attach_plan_metadata(
                received_row,
                billing_deadline=received_collection.end_date if received_collection else (entry.collection.end_date if entry.collection else None),
            )
            received_row["received_total"] = Decimal(received_row["received_total"]) + _money(entry.total_amount)

    monthly_projection: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"planned_outflows": Decimal("0.00"), "linked_payments": Decimal("0.00")}
    )
    for simulated_installment in simulated_installments:
        _add_monthly_projection_amount(
            monthly_projection,
            due_date=simulated_installment.due_date,
            planned_amount=_money(simulated_installment.amount),
        )

    open_installments: list[PurchaseInstallmentRead] = []
    for invoice in invoices:
        reporting_collection = resolve_reporting_collection(invoice.collection, invoice.issue_date or invoice.entry_date)
        row = ensure_row(
            invoice.brand_id if invoice.brand else resolve_brand_id_from_supplier(invoice.supplier_id),
            invoice.brand.name if invoice.brand else resolve_brand_name_from_supplier(invoice.supplier_id),
            reporting_collection.id if reporting_collection else invoice.collection_id,
            _collection_name(reporting_collection) or _collection_name(invoice.collection),
            reporting_collection.season_year if reporting_collection else (invoice.collection.season_year if invoice.collection else None),
            reporting_collection.season_type if reporting_collection else (invoice.collection.season_type if invoice.collection else None),
        )
        attach_supplier(row, invoice.supplier.name if invoice.supplier else None, invoice.supplier_id)
        attach_plan_metadata(
            row,
            billing_deadline=reporting_collection.end_date if reporting_collection else (invoice.collection.end_date if invoice.collection else None),
        )
        if planning_mode:
            continue
        for installment in invoice.installments:
            installment.status = _sync_installment_status(installment)
            remaining_amount = _installment_remaining_amount(installment)
            if remaining_amount > 0:
                open_installments.append(_serialize_installment(db, installment))

    for cost_total in cost_totals:
        collection_key = _normalize_collection_lookup_key(cost_total.collection_name)
        collection = collection_lookup_by_key.get(collection_key)
        if filters.collection_id and (collection is None or collection.id != filters.collection_id):
            continue

        supplier = next(
            (
                supplier_lookup_by_key[lookup_key]
                for lookup_key in _supplier_lookup_keys(cost_total.supplier_name)
                if lookup_key in supplier_lookup_by_key
            ),
            None,
        )
        supplier_brand_id = resolve_brand_id_from_supplier(supplier.id if supplier else None)
        supplier_brand_name = resolve_brand_name_from_supplier(supplier.id if supplier else None)
        if filters.brand_id and supplier_brand_id != filters.brand_id:
            continue

        matched_row = False
        for row in aggregates.values():
            row_collection_key = _normalize_collection_lookup_key(str(row["collection_name"]))
            if row_collection_key != collection_key:
                continue
            supplier_names = row["supplier_names"] if isinstance(row["supplier_names"], list) else []
            if supplier_names and not any(_supplier_lookup_keys(name) & _supplier_lookup_keys(cost_total.supplier_name) for name in supplier_names):
                continue
            row["returns_total"] = Decimal(row["returns_total"]) + _money(cost_total.purchase_return_cost_total)
            matched_row = True

        if matched_row or collection is None:
            continue

        row = ensure_row(
            supplier_brand_id,
            supplier_brand_name,
            collection.id,
            _collection_name(collection),
            collection.season_year,
            collection.season_type,
        )
        attach_supplier(row, supplier.name if supplier else cost_total.supplier_name, supplier.id if supplier else None)
        attach_plan_metadata(row, billing_deadline=collection.end_date)
        row["returns_total"] = Decimal(row["returns_total"]) + _money(cost_total.purchase_return_cost_total)

    rows: list[PurchasePlanningRow] = []
    for item in aggregates.values():
        purchased_total = _money(Decimal(item["purchased_total"]))
        returns_total = _money(Decimal(item["returns_total"]))
        received_total = _money(Decimal(item["received_total"]))
        delivered_total = _money(Decimal(item["delivered_total"]))
        launched_total = _money(Decimal(item["launched_financial_total"]))
        paid_total = _money(Decimal(item["paid_total"]))
        outstanding_goods = _money(max(purchased_total - delivered_total, Decimal("0.00")))
        outstanding_payable = _money(Decimal(item["outstanding_payable_total"]))
        
        # Calculate new profit margin formula: ((sum sales / (received - returns)) - 1) * 100
        sold_total = Decimal(item.get("sold_total", 0))
        net_receipts = received_total - returns_total
        
        if net_receipts > 0:
            profit_margin = ((sold_total / net_receipts) - 1) * 100
        else:
            profit_margin = Decimal("0.00")
            
        rows.append(
            PurchasePlanningRow(
                plan_id=str(item["plan_id"]) if item["plan_id"] else None,
                brand_id=str(item["brand_id"]) if item["brand_id"] else None,
                brand_name=str(item["brand_name"]),
                supplier_ids=sorted(item["supplier_ids"]) if isinstance(item["supplier_ids"], list) else [],
                supplier_names=sorted(item["supplier_names"]) if isinstance(item["supplier_names"], list) else [],
                collection_id=str(item["collection_id"]) if item["collection_id"] else None,
                collection_name=str(item["collection_name"]),
                season_year=int(item["season_year"]) if item["season_year"] is not None else None,
                season_type=str(item["season_type"]) if item["season_type"] else None,
                season_label=str(item["season_label"]) if item["season_label"] else None,
                billing_deadline=item["billing_deadline"] if isinstance(item["billing_deadline"], date) else None,
                payment_term=str(item["payment_term"]) if item["payment_term"] else None,
                status=str(item["status"]) if item["status"] else None,
                order_date=item["order_date"] if isinstance(item["order_date"], date) else None,
                expected_delivery_date=item["expected_delivery_date"] if isinstance(item["expected_delivery_date"], date) else None,
                purchased_total=purchased_total,
                returns_total=returns_total,
                received_total=received_total,
                delivered_total=delivered_total,
                launched_financial_total=launched_total,
                paid_total=paid_total,
                outstanding_goods_total=outstanding_goods,
                delivered_not_recorded_total=_money(max(delivered_total - launched_total, Decimal("0.00"))),
                outstanding_payable_total=outstanding_payable,
                sold_total=_money(sold_total),
                profit_margin=_money(profit_margin),
            )
        )
    rows.sort(key=lambda item: (item.outstanding_payable_total, item.purchased_total), reverse=True)

    summary = PurchasePlanningSummary(
        purchased_total=_money(sum((row.purchased_total for row in rows), Decimal("0.00"))),
        delivered_total=_money(sum((row.delivered_total for row in rows), Decimal("0.00"))),
        launched_financial_total=_money(sum((row.launched_financial_total for row in rows), Decimal("0.00"))),
        paid_total=_money(sum((row.paid_total for row in rows), Decimal("0.00"))),
        outstanding_goods_total=_money(sum((row.outstanding_goods_total for row in rows), Decimal("0.00"))),
        delivered_not_recorded_total=_money(sum((row.delivered_not_recorded_total for row in rows), Decimal("0.00"))),
        outstanding_payable_total=_money(sum((row.outstanding_payable_total for row in rows), Decimal("0.00"))),
    )
    monthly_points = _serialize_monthly_projection(monthly_projection)

    return PurchasePlanningOverview(
        summary=summary,
        rows=rows,
        cost_totals=cost_totals,
        monthly_projection=monthly_points,
        invoices=[_serialize_invoice(db, item) for item in invoices] if not planning_mode else [],
        open_installments=sorted(
            open_installments,
            key=lambda item: ((item.due_date or date.max), item.installment_number),
        ) if not planning_mode else [],
        plans=[
            _serialize_plan(
                item,
                received_amount=plan_financial_totals.get(item.id, {}).get("received_amount"),
                amount_to_receive=plan_financial_totals.get(item.id, {}).get("amount_to_receive"),
                season_metrics=_season_metrics_for_plan(item, season_totals),
            )
            for item in plans
        ],
        ungrouped_suppliers=ungrouped_suppliers if not planning_mode else [],
    )


def get_cached_purchase_planning_overview(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
    *,
    mode: str = "summary",
) -> PurchasePlanningOverview:
    filters = _resolve_effective_purchase_planning_filters(db, company.id, filters)
    cache_key = _purchase_planning_cache_key(company.id, filters, mode)
    current_time = monotonic()

    with _purchase_planning_overview_cache_lock:
        cached_entry = _purchase_planning_overview_cache.get(cache_key)
        if cached_entry and cached_entry.expires_at > current_time:
            return cached_entry.payload.model_copy(deep=True)

    overview = build_purchase_planning_overview(db, company, filters, mode=mode)
    ttl_seconds = _purchase_planning_cache_ttl_seconds(filters)

    with _purchase_planning_overview_cache_lock:
        _prune_purchase_planning_overview_cache(current_time)
        _purchase_planning_overview_cache[cache_key] = PurchasePlanningOverviewCacheEntry(
            expires_at=current_time + ttl_seconds,
            payload=overview.model_copy(deep=True),
        )

    return overview


def build_purchase_planning_cashflow_events(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
) -> list[PurchaseInstallmentDraft]:

    filters = _resolve_effective_purchase_planning_filters(db, company.id, filters)
    today = _today()
    company_collections = list(
        db.scalars(
            select(CollectionSeason)
            .where(CollectionSeason.company_id == company.id)
            .order_by(CollectionSeason.start_date.desc(), CollectionSeason.created_at.desc())
        )
    )
    plans = (
        db.execute(
            _apply_filters_to_plan_stmt(
                select(PurchasePlan)
                .where(PurchasePlan.company_id == company.id)
                .options(
                    joinedload(PurchasePlan.brand),
                    joinedload(PurchasePlan.collection),
                    joinedload(PurchasePlan.supplier),
                    joinedload(PurchasePlan.plan_suppliers).joinedload(PurchasePlanSupplier.supplier),
                ),
                filters,
            ).order_by(PurchasePlan.order_date.desc().nullslast(), PurchasePlan.created_at.desc())
        )
        .unique()
        .scalars()
        .all()
    )
    cashflow_plans = _filter_cashflow_plans(db, company.id, plans)
    plan_linx_received_totals = _build_plan_linx_received_totals(
        db,
        company.id,
        cashflow_plans,
        company_collections=company_collections,
        today=today,
    )
    return _build_purchase_forecast_installments(cashflow_plans, plan_linx_received_totals, today=today)


def build_purchase_planning_cashflow(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
) -> list[PurchasePlanningMonthlyProjection]:
    simulated_installments = build_purchase_planning_cashflow_events(db, company, filters)
    monthly_projection: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"planned_outflows": Decimal("0.00"), "linked_payments": Decimal("0.00")}
    )
    for installment in simulated_installments:
        _add_monthly_projection_amount(
            monthly_projection,
            due_date=installment.due_date,
            planned_amount=_money(installment.amount),
        )
    return _serialize_monthly_projection(monthly_projection)

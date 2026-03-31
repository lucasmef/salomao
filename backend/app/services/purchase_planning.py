from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.finance import Category, FinancialEntry
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
    PurchasePlanRead,
    PurchasePlanUpdate,
    PurchaseReturnCreate,
    PurchaseReturnRead,
    PurchaseReturnUpdate,
    PurchasePlanningMonthlyProjection,
    PurchasePlanningOverview,
    PurchasePlanningRow,
    PurchasePlanningSummary,
    PurchasePlanningUngroupedSupplier,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from app.services.audit import write_audit_log
from app.services.import_parsers import normalize_label, parse_date_br, parse_decimal_pt_br

TWO_PLACES = Decimal("0.01")
HISTORICAL_COLLECTION_START_YEAR = 2020
SEASON_LABELS = {
    "summer": "Verao",
    "winter": "Inverno",
}
SEASON_PHASE_LABELS = {
    "main": "Principal",
    "high": "Alto",
}


@dataclass(slots=True)
class PurchasePlanningFilters:
    year: int | None = None
    brand_id: str | None = None
    supplier_id: str | None = None
    collection_id: str | None = None
    status: str | None = None


def _money(value: Decimal | int | float | None) -> Decimal:
    raw = Decimal(value or 0)
    return raw.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _today() -> date:
    return date.today()


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
        notes=purchase_return.notes,
    )


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

    purchase_return = PurchaseReturn(
        company_id=company.id,
        supplier_id=supplier.id,
        return_date=payload.return_date,
        amount=_money(payload.amount),
        notes=payload.notes,
    )
    db.add(purchase_return)
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
    purchase_return.supplier_id = supplier.id
    purchase_return.supplier = supplier
    purchase_return.return_date = payload.return_date
    purchase_return.amount = _money(payload.amount)
    purchase_return.notes = payload.notes
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
    purchase_return = db.scalar(
        select(PurchaseReturn)
        .where(PurchaseReturn.id == purchase_return_id, PurchaseReturn.company_id == company.id)
        .options(joinedload(PurchaseReturn.supplier))
    )
    if purchase_return is None:
        raise HTTPException(status_code=404, detail="Devolucao de compra nao encontrada")

    before_state = _serialize_purchase_return(purchase_return).model_dump(mode="json")
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


def _match_purchase_return_to_plan(
    purchase_return: PurchaseReturn,
    *,
    plan_supplier_ids: dict[str, set[str]],
    plan_periods: dict[str, tuple[date, date]],
) -> str | None:
    for plan_id, (period_start, period_end) in plan_periods.items():
        if purchase_return.return_date < period_start or purchase_return.return_date > period_end:
            continue
        if purchase_return.supplier_id in plan_supplier_ids.get(plan_id, set()):
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
    past_plan_ids: set[str] = set()
    min_period_start: date | None = None
    max_period_end: date | None = None
    today = _today()
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
        if _is_past_collection(plan.collection, today=today):
            past_plan_ids.add(plan.id)
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

    plan_supplier_id_set = {supplier_id for supplier_ids in plan_supplier_ids.values() for supplier_id in supplier_ids}
    if plan_supplier_id_set:
        purchase_returns = list(
            db.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.company_id == company_id,
                    PurchaseReturn.supplier_id.in_(plan_supplier_id_set),
                    PurchaseReturn.return_date >= min_period_start,
                    PurchaseReturn.return_date <= max_period_end,
                )
            )
        )
        for purchase_return in purchase_returns:
            matched_plan_id = _match_purchase_return_to_plan(
                purchase_return,
                plan_supplier_ids=plan_supplier_ids,
                plan_periods=plan_periods,
            )
            if matched_plan_id is None or matched_plan_id not in past_plan_ids:
                continue
            current_received = Decimal(
                totals_by_plan_id.setdefault(matched_plan_id, {"received_amount": Decimal("0.00")})["received_amount"]
            )
            totals_by_plan_id[matched_plan_id]["received_amount"] = max(
                current_received - _money(purchase_return.amount),
                Decimal("0.00"),
            )

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
                FinancialEntry.status.in_(["planned", "partial", "settled"]),
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
    if linked_entry is None:
        return "planned"
    paid_amount = Decimal(linked_entry.paid_amount or 0)
    if paid_amount >= Decimal(installment.amount or 0) and linked_entry.status == "settled":
        return "paid"
    if paid_amount > 0 or linked_entry.status == "partial":
        return "partial"
    return "linked"


def _installment_remaining_amount(installment: PurchaseInstallment) -> Decimal:
    if installment.financial_entry is None:
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
        status="planned",
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
            status="planned",
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
        stmt = stmt.where(PurchasePlan.status == filters.status)
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
        stmt = stmt.where(FinancialEntry.status == filters.status)
    return stmt


def _group_key(brand_name: str | None, collection_name: str | None) -> tuple[str, str]:
    return brand_name or "Sem marca", collection_name or "Sem colecao"


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


def _simulate_remaining_purchase_installments(
    *,
    amount_to_receive: Decimal,
    payment_term: str | None,
    billing_deadline: date | None,
    today: date,
) -> list[PurchaseInstallmentDraft]:
    amount_to_receive = _money(amount_to_receive)
    if amount_to_receive <= 0:
        return []

    month_ends = _remaining_billing_months(today, billing_deadline)
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
                installment_number=1,
                installment_label="1/1",
                due_date=month_end,
                amount=batch_amount,
            )
        ]
        simulated.extend(batch_installments)
    return simulated


def _build_purchase_forecast_installments(
    plans: list[PurchasePlan],
    plan_financial_totals: dict[str, dict[str, Decimal]],
    *,
    today: date,
) -> list[PurchaseInstallmentDraft]:
    simulated_installments: list[PurchaseInstallmentDraft] = []
    for plan in plans:
        financial_totals = plan_financial_totals.get(plan.id, {})
        amount_to_receive = _money(financial_totals.get("amount_to_receive", plan.purchased_amount))
        payment_term = (plan.brand.default_payment_term if plan.brand and plan.brand.default_payment_term else None) or plan.payment_term
        simulated_installments.extend(
            _simulate_remaining_purchase_installments(
                amount_to_receive=amount_to_receive,
                payment_term=payment_term,
                billing_deadline=plan.collection.end_date if plan.collection else None,
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


def build_purchase_planning_overview(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
    *,
    mode: str = "summary",
) -> PurchasePlanningOverview:
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
    season_totals = _build_supplier_season_totals(db, company.id)
    cashflow_plans = _filter_cashflow_plans(db, company.id, plans)
    simulated_installments = _build_purchase_forecast_installments(cashflow_plans, plan_financial_totals, today=_today())

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
                "received_total": Decimal("0.00"),
                "delivered_total": Decimal("0.00"),
                "launched_financial_total": Decimal("0.00"),
                "paid_total": Decimal("0.00"),
                "outstanding_payable_total": Decimal("0.00"),
            }
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
                received_collection.season_year if received_collection else (entry.collection.season_year if entry.collection else None),
                received_collection.season_type if received_collection else (entry.collection.season_type if entry.collection else None),
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

    purchase_return_stmt = select(PurchaseReturn).where(PurchaseReturn.company_id == company.id).options(joinedload(PurchaseReturn.supplier))
    if filters.year:
        purchase_return_stmt = purchase_return_stmt.where(
            PurchaseReturn.return_date >= date(filters.year, 1, 1),
            PurchaseReturn.return_date <= date(filters.year, 12, 31),
        )
    if filters.supplier_id:
        purchase_return_stmt = purchase_return_stmt.where(PurchaseReturn.supplier_id == filters.supplier_id)
    purchase_returns = list(db.scalars(purchase_return_stmt))
    for purchase_return in purchase_returns:
        reporting_collection = resolve_reporting_collection(None, purchase_return.return_date)
        if reporting_collection is None or not _is_past_collection(reporting_collection, today=today):
            continue
        supplier_brand_id = resolve_brand_id_from_supplier(purchase_return.supplier_id)
        supplier_brand_name = resolve_brand_name_from_supplier(purchase_return.supplier_id)
        if filters.brand_id and supplier_brand_id != filters.brand_id:
            continue
        if filters.collection_id and reporting_collection.id != filters.collection_id:
            continue
        row = ensure_row(
            supplier_brand_id,
            supplier_brand_name,
            reporting_collection.id,
            _collection_name(reporting_collection),
            reporting_collection.season_year,
            reporting_collection.season_type,
        )
        attach_supplier(row, purchase_return.supplier.name if purchase_return.supplier else None, purchase_return.supplier_id)
        attach_plan_metadata(row, billing_deadline=reporting_collection.end_date)
        row["received_total"] = max(
            Decimal(row["received_total"]) - _money(purchase_return.amount),
            Decimal("0.00"),
        )

    rows: list[PurchasePlanningRow] = []
    for item in aggregates.values():
        purchased_total = _money(Decimal(item["purchased_total"]))
        received_total = _money(Decimal(item["received_total"]))
        delivered_total = _money(Decimal(item["delivered_total"]))
        launched_total = _money(Decimal(item["launched_financial_total"]))
        paid_total = _money(Decimal(item["paid_total"]))
        outstanding_goods = _money(max(purchased_total - delivered_total, Decimal("0.00")))
        outstanding_payable = _money(Decimal(item["outstanding_payable_total"]))
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
                received_total=received_total,
                delivered_total=delivered_total,
                launched_financial_total=launched_total,
                paid_total=paid_total,
                outstanding_goods_total=outstanding_goods,
                delivered_not_recorded_total=_money(max(delivered_total - launched_total, Decimal("0.00"))),
                outstanding_payable_total=outstanding_payable,
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


def build_purchase_planning_cashflow_events(
    db: Session,
    company: Company,
    filters: PurchasePlanningFilters,
) -> list[PurchaseInstallmentDraft]:
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
    plan_financial_totals, _ = _build_plan_financial_totals(db, company.id, cashflow_plans)
    return _build_purchase_forecast_installments(cashflow_plans, plan_financial_totals, today=_today())


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

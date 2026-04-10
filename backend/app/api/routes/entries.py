from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.models.finance import FinancialEntry
from app.schemas.financial_entry import (
    FinancialEntryBulkDeleteRequest,
    FinancialEntryBulkDeleteResponse,
    FinancialEntryBulkCategoryUpdateRequest,
    FinancialEntryBulkCategoryUpdateResponse,
    EntrySettlementRequest,
    EntryStatusRequest,
    FinancialEntryCreate,
    FinancialEntryFilter,
    FinancialEntryListResponse,
    FinancialEntryRead,
    FinancialEntryUpdate,
)
from app.services.cache_invalidation import refresh_finance_analytics_caches
from app.services.company_context import get_current_company
from app.services.finance_ops import (
    bulk_delete_entries,
    bulk_update_entry_category,
    cancel_entry,
    create_entry,
    delete_entry,
    list_entries,
    reverse_entry,
    settle_entry,
    update_entry,
)

router = APIRouter()


def _split_csv_values(value: str | None) -> list[str] | None:
    if not value:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


def _transfer_direction(entry: FinancialEntry) -> str | None:
    if not entry.transfer_id or not entry.account_id:
        return None
    transfer = entry.transfer
    if not transfer:
        return None
    if transfer.source_account_id == entry.account_id:
        return "outflow"
    if transfer.destination_account_id == entry.account_id:
        return "inflow"
    return None


def _serialize_entry(entry: FinancialEntry) -> FinancialEntryRead:
    return FinancialEntryRead(
        id=entry.id,
        company_id=entry.company_id,
        account_id=entry.account_id,
        category_id=entry.category_id,
        interest_category_id=entry.interest_category_id,
        transfer_id=entry.transfer_id,
        loan_installment_id=entry.loan_installment_id,
        supplier_id=entry.supplier_id,
        collection_id=entry.collection_id,
        purchase_invoice_id=entry.purchase_invoice_id,
        purchase_installment_id=entry.purchase_installment_id,
        entry_type=entry.entry_type,
        status=entry.status,
        title=entry.title,
        description=entry.description,
        notes=entry.notes,
        counterparty_name=entry.counterparty_name,
        document_number=entry.document_number,
        issue_date=entry.issue_date,
        competence_date=entry.competence_date,
        due_date=entry.due_date,
        settled_at=entry.settled_at,
        principal_amount=entry.principal_amount,
        interest_amount=entry.interest_amount,
        discount_amount=entry.discount_amount,
        penalty_amount=entry.penalty_amount,
        total_amount=entry.total_amount,
        paid_amount=entry.paid_amount,
        expected_amount=entry.expected_amount,
        external_source=entry.external_source,
        source_system=entry.source_system,
        source_reference=entry.source_reference,
        is_recurring_generated=entry.is_recurring_generated,
        is_deleted=entry.is_deleted,
        transfer_direction=_transfer_direction(entry),
        account_name=entry.account.name if entry.account else None,
        category_name=entry.category.name if entry.category else None,
        category_group=entry.category.report_group if entry.category else None,
        category_subgroup=entry.category.report_subgroup if entry.category else None,
        interest_category_name=entry.interest_category.name if entry.interest_category else None,
        supplier_name=entry.supplier.name if entry.supplier else None,
        collection_name=entry.collection.name if entry.collection else None,
        is_legacy=entry.external_source == "historical_cashbook",
    )


@router.get("", response_model=FinancialEntryListResponse)
def get_entries(
    db: DbSession,
    status_value: str | None = Query(default=None, alias="status"),
    statuses: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    report_group: str | None = Query(default=None),
    report_subgroup: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    entry_types: str | None = Query(default=None),
    reconciled: bool | None = Query(default=None),
    source_system: str | None = Query(default=None),
    counterparty_name: str | None = Query(default=None),
    document_number: str | None = Query(default=None),
    search: str | None = Query(default=None),
    amount_min: Decimal | None = Query(default=None),
    amount_max: Decimal | None = Query(default=None),
    include_legacy: bool = Query(default=False),
    date_field: Literal["due_date", "issue_date"] = Query(default="due_date"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=50, ge=1, le=100000),
) -> FinancialEntryListResponse:
    company = get_current_company(db)
    filters = FinancialEntryFilter(
        status=status_value,
        statuses=_split_csv_values(statuses),
        account_id=account_id,
        category_id=category_id,
        report_group=report_group,
        report_subgroup=report_subgroup,
        entry_type=entry_type,
        entry_types=_split_csv_values(entry_types),
        reconciled=reconciled,
        source_system=source_system,
        counterparty_name=counterparty_name,
        document_number=document_number,
        search=search,
        amount_min=amount_min,
        amount_max=amount_max,
        include_legacy=include_legacy,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    items, total, total_amount, paid_amount = list_entries(db, company, filters)
    return FinancialEntryListResponse(
        items=[_serialize_entry(entry) for entry in items],
        total=total,
        page=page,
        page_size=page_size,
        total_amount=total_amount,
        paid_amount=paid_amount,
    )


@router.get("/payables", response_model=FinancialEntryListResponse)
def get_payables(
    db: DbSession,
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=25, ge=1, le=100000),
) -> FinancialEntryListResponse:
    company = get_current_company(db)
    filters = FinancialEntryFilter(entry_type="expense", status="open", page=page, page_size=page_size)
    items, total, total_amount, paid_amount = list_entries(db, company, filters)
    return FinancialEntryListResponse(
        items=[_serialize_entry(entry) for entry in items],
        total=total,
        page=page,
        page_size=page_size,
        total_amount=total_amount,
        paid_amount=paid_amount,
    )


@router.get("/receivables", response_model=FinancialEntryListResponse)
def get_receivables(
    db: DbSession,
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=25, ge=1, le=100000),
) -> FinancialEntryListResponse:
    company = get_current_company(db)
    filters = FinancialEntryFilter(entry_type="income", status="open", page=page, page_size=page_size)
    items, total, total_amount, paid_amount = list_entries(db, company, filters)
    return FinancialEntryListResponse(
        items=[_serialize_entry(entry) for entry in items],
        total=total,
        page=page,
        page_size=page_size,
        total_amount=total_amount,
        paid_amount=paid_amount,
    )


@router.post("", response_model=FinancialEntryRead, status_code=status.HTTP_201_CREATED)
def post_entry(payload: FinancialEntryCreate, db: DbSession, current_user: CurrentUser) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = create_entry(db, company, payload, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)


@router.post("/bulk/category", response_model=FinancialEntryBulkCategoryUpdateResponse)
def post_bulk_update_entry_category(
    payload: FinancialEntryBulkCategoryUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryBulkCategoryUpdateResponse:
    company = get_current_company(db)
    updated_count, category, entry_ids = bulk_update_entry_category(
        db,
        company,
        entry_ids=payload.entry_ids,
        category_id=payload.category_id,
        actor_user=current_user,
    )
    db.commit()
    refresh_finance_analytics_caches(db, company)
    return FinancialEntryBulkCategoryUpdateResponse(
        updated_count=updated_count,
        category_id=category.id,
        category_name=category.name,
        entry_ids=entry_ids,
    )


@router.post("/bulk/delete", response_model=FinancialEntryBulkDeleteResponse)
def post_bulk_delete_entries(
    payload: FinancialEntryBulkDeleteRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryBulkDeleteResponse:
    company = get_current_company(db)
    deleted_count, entry_ids = bulk_delete_entries(
        db,
        company,
        entry_ids=payload.entry_ids,
        actor_user=current_user,
    )
    db.commit()
    refresh_finance_analytics_caches(db, company)
    return FinancialEntryBulkDeleteResponse(
        deleted_count=deleted_count,
        entry_ids=entry_ids,
    )


@router.put("/{entry_id}", response_model=FinancialEntryRead)
def put_entry(
    entry_id: str,
    payload: FinancialEntryUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = update_entry(db, company, entry_id, payload, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)


@router.post("/{entry_id}/settle", response_model=FinancialEntryRead)
def settle_financial_entry(
    entry_id: str,
    payload: EntrySettlementRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = settle_entry(db, company, entry_id, payload, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)


@router.post("/{entry_id}/cancel", response_model=FinancialEntryRead)
def cancel_financial_entry(
    entry_id: str,
    payload: EntryStatusRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = cancel_entry(db, company, entry_id, payload, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)


@router.post("/{entry_id}/reverse", response_model=FinancialEntryRead)
def reverse_financial_entry(
    entry_id: str,
    payload: EntryStatusRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = reverse_entry(db, company, entry_id, payload, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)


@router.delete("/{entry_id}", response_model=FinancialEntryRead)
def delete_financial_entry(
    entry_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryRead:
    company = get_current_company(db)
    entry = delete_entry(db, company, entry_id, current_user)
    db.commit()
    refresh_finance_analytics_caches(db, company)
    db.refresh(entry)
    return _serialize_entry(entry)

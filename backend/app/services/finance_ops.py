from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.finance import (
    Account,
    Category,
    FinancialEntry,
    LoanContract,
    LoanInstallment,
    RecurrenceRule,
    Transfer,
)
from app.db.models.banking import Reconciliation, ReconciliationLine
from app.db.models.purchasing import CollectionSeason, PurchaseInvoice, PurchaseInstallment, Supplier
from app.db.models.security import Company, User
from app.schemas.financial_entry import (
    EntrySettlementRequest,
    EntryStatusRequest,
    FinancialEntryCreate,
    FinancialEntryFilter,
    FinancialEntryUpdate,
)
from app.schemas.loan import LoanContractCreate
from app.schemas.recurrence import (
    RecurrenceGenerationRequest,
    RecurrenceRuleCreate,
    RecurrenceRuleUpdate,
)
from app.schemas.transfer import TransferCreate
from app.services.audit import write_audit_log
from app.services.bootstrap import ensure_default_financial_category
from app.services.import_parsers import normalize_label


TWO_PLACES = Decimal("0.01")
SETTLEMENT_ADJUSTMENT_SOURCE = "settlement_adjustment"


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _validate_account(db: Session, company_id: str, account_id: str | None) -> Account | None:
    if not account_id:
        return None
    account = db.get(Account, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")
    return account


def _validate_category(
    db: Session,
    company_id: str,
    category_id: str | None,
    *,
    allow_transfer: bool = False,
) -> Category | None:
    if not category_id:
        return None
    category = db.get(Category, category_id)
    if not category or category.company_id != company_id:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    if not allow_transfer and category.entry_kind == "transfer":
        raise HTTPException(status_code=400, detail="Categoria de transferencia nao e valida aqui")
    return category


def _supplier_has_purchase_history(db: Session, company_id: str, supplier_id: str) -> bool:
    invoice_count = db.scalar(
        select(func.count(PurchaseInvoice.id)).where(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.supplier_id == supplier_id,
        )
    ) or 0
    if invoice_count:
        return True
    purchase_entry_count = db.scalar(
        select(func.count(FinancialEntry.id))
        .join(Category, Category.id == FinancialEntry.category_id)
        .where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.supplier_id == supplier_id,
            FinancialEntry.entry_type == "expense",
            FinancialEntry.is_deleted.is_(False),
            or_(
                Category.name == "Compras",
                Category.report_group == "Compras",
                Category.report_subgroup == "Compras",
            ),
        )
    ) or 0
    return bool(purchase_entry_count)


def _refresh_supplier_purchase_history_flags(db: Session, company_id: str, supplier_ids: set[str]) -> None:
    for supplier_id in {value for value in supplier_ids if value}:
        supplier = db.get(Supplier, supplier_id)
        if supplier is None or supplier.company_id != company_id:
            continue
        supplier.has_purchase_invoices = _supplier_has_purchase_history(db, company_id, supplier_id)


def _settled_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _entry_reference_date(entry: FinancialEntry) -> date:
    return entry.due_date or entry.competence_date or entry.issue_date or date.today()


def _synchronize_entry_financial_state(entry: FinancialEntry) -> None:
    total_amount = _money(entry.total_amount or Decimal("0.00"))
    paid_amount = _money(entry.paid_amount or Decimal("0.00"))

    if entry.status == "settled":
        entry.paid_amount = total_amount
        if entry.settled_at is None:
            entry.settled_at = _settled_datetime(_entry_reference_date(entry))
        return

    entry.paid_amount = paid_amount
    if paid_amount <= Decimal("0.00"):
        entry.settled_at = None


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


def _validate_purchase_invoice(db: Session, company_id: str, purchase_invoice_id: str | None) -> PurchaseInvoice | None:
    if not purchase_invoice_id:
        return None
    invoice = db.get(PurchaseInvoice, purchase_invoice_id)
    if not invoice or invoice.company_id != company_id:
        raise HTTPException(status_code=404, detail="Nota de compra nao encontrada")
    return invoice


def _validate_purchase_installment(
    db: Session,
    company_id: str,
    purchase_installment_id: str | None,
) -> PurchaseInstallment | None:
    if not purchase_installment_id:
        return None
    installment = db.get(PurchaseInstallment, purchase_installment_id)
    if not installment or installment.company_id != company_id:
        raise HTTPException(status_code=404, detail="Parcela de compra nao encontrada")
    return installment


def _category_requires_supplier(category: Category | None, entry_type: str) -> bool:
    if category is None or entry_type != "expense":
        return False
    group_label = normalize_label(category.report_group or "")
    name_label = normalize_label(category.name or "")
    return "compr" in group_label or "compra" in name_label


def _entry_dict(entry: FinancialEntry) -> dict[str, str | None]:
    return {
        "id": entry.id,
        "title": entry.title,
        "status": entry.status,
        "entry_type": entry.entry_type,
        "account_id": entry.account_id,
        "category_id": entry.category_id,
        "total_amount": f"{Decimal(entry.total_amount):.2f}",
        "paid_amount": f"{Decimal(entry.paid_amount):.2f}",
    }


def _settlement_adjustment_source_reference(entry_id: str, kind: str) -> str:
    return f"settlement-adjustment:{entry_id}:{kind}"


def _remove_existing_settlement_adjustments(db: Session, company_id: str, entry_id: str) -> None:
    adjustment_entries = db.scalars(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.source_system == SETTLEMENT_ADJUSTMENT_SOURCE,
            FinancialEntry.source_reference.like(f"settlement-adjustment:{entry_id}:%"),
            FinancialEntry.is_deleted.is_(False),
        )
    )
    for adjustment in adjustment_entries:
        adjustment.is_deleted = True
        adjustment.status = "cancelled"


def _require_due_date_for_paid_status(status_value: str | None, due_date: date | None) -> None:
    if status_value == "settled" and due_date is None:
        raise HTTPException(status_code=400, detail="Data de vencimento obrigatoria para lancamentos pagos")


def _expected_category_entry_kind(entry_type: str) -> str:
    if entry_type == "transfer":
        return "transfer"
    if entry_type in {"income", "historical_receipt", "historical_purchase_return"}:
        return "income"
    return "expense"


def apply_settlement_breakdown(
    db: Session,
    company: Company,
    entry: FinancialEntry,
    *,
    principal_amount: Decimal | None = None,
    interest_amount: Decimal | None = None,
    discount_amount: Decimal | None = None,
    penalty_amount: Decimal | None = None,
    settled_at: datetime | None = None,
) -> tuple[Decimal, list[tuple[FinancialEntry, Decimal]]]:
    principal = _money(
        principal_amount
        if principal_amount is not None
        else entry.principal_amount
        if Decimal(entry.principal_amount or 0) > Decimal("0.00")
        else entry.total_amount
    )
    interest = _money(interest_amount if interest_amount is not None else entry.interest_amount)
    discount = _money(discount_amount if discount_amount is not None else entry.discount_amount)
    penalty = _money(penalty_amount if penalty_amount is not None else entry.penalty_amount)
    cash_total = _money(principal + interest + penalty - discount)

    if principal <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="O principal deve ser maior que zero")
    if cash_total <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="O valor final da baixa deve ser maior que zero")
    if Decimal(entry.paid_amount or 0) > principal:
        raise HTTPException(status_code=400, detail="O valor ja pago nao pode ficar maior que o principal final")

    settled_at_value = settled_at or entry.settled_at or _settled_datetime(date.today())
    adjustment_category_id = entry.interest_category_id or ensure_default_financial_category(db, company.id).id
    effective_date = settled_at_value.date() if settled_at_value else date.today()
    adjustment_account_id = entry.account_id

    _remove_existing_settlement_adjustments(db, company.id, entry.id)

    entry.principal_amount = principal
    entry.interest_amount = Decimal("0.00")
    entry.discount_amount = Decimal("0.00")
    entry.penalty_amount = Decimal("0.00")
    entry.total_amount = principal

    generated_adjustments: list[tuple[FinancialEntry, Decimal]] = []

    def add_adjustment(kind: str, title_prefix: str, amount: Decimal, applied_amount: Decimal) -> None:
        adjustment_entry_type = "income" if kind == "discount" else "expense"
        adjustment_entry = FinancialEntry(
            company_id=company.id,
            account_id=adjustment_account_id,
            category_id=adjustment_category_id,
            entry_type=adjustment_entry_type,
            status="settled",
            title=f"{title_prefix} - {entry.title}",
            description=f"Gerado automaticamente na baixa de {entry.title}",
            notes=entry.notes,
            counterparty_name=entry.counterparty_name,
            document_number=entry.document_number,
            issue_date=effective_date,
            competence_date=effective_date,
            due_date=effective_date,
            settled_at=settled_at_value,
            principal_amount=amount,
            total_amount=amount,
            paid_amount=amount,
            source_system=SETTLEMENT_ADJUSTMENT_SOURCE,
            source_reference=_settlement_adjustment_source_reference(entry.id, kind),
        )
        db.add(adjustment_entry)
        db.flush()
        generated_adjustments.append((adjustment_entry, applied_amount))

    if interest > Decimal("0.00"):
        add_adjustment("interest", "Juros da baixa", interest, interest)
    if penalty > Decimal("0.00"):
        add_adjustment("penalty", "Multa da baixa", penalty, penalty)
    if discount > Decimal("0.00"):
        add_adjustment("discount", "Desconto da baixa", discount, -discount)

    return cash_total, generated_adjustments


def _upsert_entry_fields(
    db: Session,
    entry: FinancialEntry,
    payload: FinancialEntryCreate | FinancialEntryUpdate,
    company_id: str,
) -> None:
    _validate_account(db, company_id, payload.account_id)
    category = _validate_category(db, company_id, payload.category_id, allow_transfer=True)
    supplier = _validate_supplier(db, company_id, payload.supplier_id)
    _validate_collection(db, company_id, payload.collection_id)
    _validate_purchase_invoice(db, company_id, payload.purchase_invoice_id)
    _validate_purchase_installment(db, company_id, payload.purchase_installment_id)

    interest_category_id = payload.interest_category_id
    if payload.interest_amount > 0 and not interest_category_id:
        interest_category_id = ensure_default_financial_category(db, company_id).id
    _validate_category(db, company_id, interest_category_id, allow_transfer=True)

    if _category_requires_supplier(category, payload.entry_type) and supplier is None:
        raise HTTPException(status_code=400, detail="Compras de mercadoria exigem fornecedor")

    entry.account_id = payload.account_id
    entry.category_id = payload.category_id
    entry.interest_category_id = interest_category_id
    entry.transfer_id = payload.transfer_id
    entry.loan_installment_id = payload.loan_installment_id
    entry.supplier_id = payload.supplier_id
    entry.collection_id = payload.collection_id
    entry.purchase_invoice_id = payload.purchase_invoice_id
    entry.purchase_installment_id = payload.purchase_installment_id
    entry.entry_type = payload.entry_type
    entry.status = payload.status
    entry.title = payload.title
    entry.description = payload.description
    entry.notes = payload.notes
    entry.counterparty_name = payload.counterparty_name or (supplier.name if supplier is not None else None)
    entry.document_number = payload.document_number
    entry.issue_date = payload.issue_date
    entry.competence_date = payload.competence_date or payload.issue_date or payload.due_date
    entry.due_date = payload.due_date
    entry.settled_at = payload.settled_at
    _require_due_date_for_paid_status(payload.status, entry.due_date)
    entry.principal_amount = _money(payload.principal_amount)
    entry.interest_amount = _money(payload.interest_amount)
    entry.discount_amount = _money(payload.discount_amount)
    entry.penalty_amount = _money(payload.penalty_amount)
    entry.total_amount = _money(payload.total_amount or Decimal("0.00"))
    entry.paid_amount = _money(payload.paid_amount)
    entry.expected_amount = payload.expected_amount
    entry.external_source = payload.external_source
    entry.source_system = payload.source_system or payload.external_source or "manual"
    entry.source_reference = payload.source_reference
    _synchronize_entry_financial_state(entry)


def list_entries(
    db: Session,
    company: Company,
    filters: FinancialEntryFilter,
) -> tuple[list[FinancialEntry], int, Decimal, Decimal]:
    stmt: Select[tuple[FinancialEntry]] = select(FinancialEntry).join(
        Category,
        Category.id == FinancialEntry.category_id,
        isouter=True,
    ).where(
        FinancialEntry.company_id == company.id,
        FinancialEntry.is_deleted.is_(False),
    )

    reconciled_entries = (
        select(Reconciliation.financial_entry_id.label("financial_entry_id"))
        .union(select(ReconciliationLine.financial_entry_id.label("financial_entry_id")))
        .subquery()
    )

    if filters.statuses:
        normalized_statuses = {status for status in filters.statuses if status}
        effective_statuses: set[str] = set()
        if "open" in normalized_statuses:
            effective_statuses.update({"planned", "partial"})
        effective_statuses.update(status for status in normalized_statuses if status != "open")
        if effective_statuses:
            stmt = stmt.where(FinancialEntry.status.in_(list(effective_statuses)))
    elif filters.status:
        if filters.status == "open":
            stmt = stmt.where(FinancialEntry.status.in_(["planned", "partial"]))
        else:
            stmt = stmt.where(FinancialEntry.status == filters.status)
    if filters.account_id:
        stmt = stmt.where(FinancialEntry.account_id == filters.account_id)
    if filters.category_id:
        stmt = stmt.where(FinancialEntry.category_id == filters.category_id)
    if filters.report_group:
        stmt = stmt.where(Category.report_group == filters.report_group)
    if filters.report_subgroup:
        stmt = stmt.where(Category.report_subgroup == filters.report_subgroup)
    if filters.entry_types:
        normalized_entry_types = [entry_type for entry_type in filters.entry_types if entry_type]
        if normalized_entry_types:
            stmt = stmt.where(FinancialEntry.entry_type.in_(normalized_entry_types))
    elif filters.entry_type:
        stmt = stmt.where(FinancialEntry.entry_type == filters.entry_type)
    if filters.reconciled is True:
        stmt = stmt.where(
            FinancialEntry.id.in_(select(reconciled_entries.c.financial_entry_id)),
            FinancialEntry.status == "settled",
        )
    elif filters.reconciled is False:
        stmt = stmt.where(~FinancialEntry.id.in_(select(reconciled_entries.c.financial_entry_id)))
    if filters.source_system:
        stmt = stmt.where(FinancialEntry.source_system == filters.source_system)
    if filters.counterparty_name:
        stmt = stmt.where(FinancialEntry.counterparty_name.ilike(f"%{filters.counterparty_name}%"))
    if filters.document_number:
        stmt = stmt.where(FinancialEntry.document_number.ilike(f"%{filters.document_number}%"))
    if filters.search:
        like_value = f"%{filters.search}%"
        stmt = stmt.where(
            or_(
                FinancialEntry.title.ilike(like_value),
                FinancialEntry.description.ilike(like_value),
                FinancialEntry.notes.ilike(like_value),
                FinancialEntry.counterparty_name.ilike(like_value),
                FinancialEntry.document_number.ilike(like_value),
            )
        )
    if not filters.include_legacy:
        stmt = stmt.where(
            or_(
                FinancialEntry.external_source.is_(None),
                FinancialEntry.external_source != "historical_cashbook",
            )
        )
    date_column = FinancialEntry.issue_date if filters.date_field == "issue_date" else FinancialEntry.due_date
    if filters.date_from:
        stmt = stmt.where(date_column >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(date_column <= filters.date_to)

    subquery = stmt.order_by(None).subquery()
    total_stmt = select(func.count()).select_from(subquery)
    totals_stmt = select(
        func.coalesce(func.sum(subquery.c.total_amount), 0),
        func.coalesce(func.sum(subquery.c.paid_amount), 0),
    )
    total = db.scalar(total_stmt) or 0
    totals_row = db.execute(totals_stmt).one()
    total_amount = Decimal(totals_row[0] or 0)
    paid_amount = Decimal(totals_row[1] or 0)

    offset = (filters.page - 1) * filters.page_size
    paged_stmt = stmt.order_by(
        FinancialEntry.due_date.desc().nullslast(),
        FinancialEntry.created_at.desc(),
    ).offset(offset).limit(filters.page_size)
    items = list(
        db.scalars(
            paged_stmt.options(
                joinedload(FinancialEntry.account),
                joinedload(FinancialEntry.category),
                joinedload(FinancialEntry.interest_category),
                joinedload(FinancialEntry.transfer),
                joinedload(FinancialEntry.supplier),
                joinedload(FinancialEntry.collection),
            )
        )
    )
    return items, total, total_amount, paid_amount


def create_entry(db: Session, company: Company, payload: FinancialEntryCreate, actor_user: User) -> FinancialEntry:
    entry = FinancialEntry(company_id=company.id)
    _upsert_entry_fields(db, entry, payload, company.id)
    db.add(entry)
    db.flush()
    _refresh_supplier_purchase_history_flags(db, company.id, {entry.supplier_id} if entry.supplier_id else set())
    write_audit_log(
        db,
        action="create_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state=_entry_dict(entry),
    )
    return entry


def update_entry(
    db: Session,
    company: Company,
    entry_id: str,
    payload: FinancialEntryUpdate,
    actor_user: User,
) -> FinancialEntry:
    entry = db.get(FinancialEntry, entry_id)
    if not entry or entry.company_id != company.id or entry.is_deleted:
        raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
    supplier_ids_to_refresh = {entry.supplier_id} if entry.supplier_id else set()
    before_state = _entry_dict(entry)
    _upsert_entry_fields(db, entry, payload, company.id)
    db.flush()
    if entry.supplier_id:
        supplier_ids_to_refresh.add(entry.supplier_id)
    _refresh_supplier_purchase_history_flags(db, company.id, supplier_ids_to_refresh)
    write_audit_log(
        db,
        action="update_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_entry_dict(entry),
    )
    return entry


def bulk_update_entry_category(
    db: Session,
    company: Company,
    *,
    entry_ids: list[str],
    category_id: str,
    actor_user: User,
) -> tuple[int, Category, list[str]]:
    normalized_entry_ids = list(dict.fromkeys(entry_ids))
    if not normalized_entry_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lancamento")

    category = _validate_category(db, company.id, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")

    entries = list(
        db.scalars(
            select(FinancialEntry)
            .options(joinedload(FinancialEntry.category))
            .where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.id.in_(normalized_entry_ids),
            )
        )
    )

    if len(entries) != len(normalized_entry_ids):
        raise HTTPException(status_code=404, detail="Um ou mais lancamentos nao foram encontrados")

    entries_by_id = {entry.id: entry for entry in entries}
    ordered_entries = [entries_by_id[entry_id] for entry_id in normalized_entry_ids]

    expected_kinds = {_expected_category_entry_kind(entry.entry_type) for entry in ordered_entries}
    if len(expected_kinds) != 1:
        raise HTTPException(
            status_code=400,
            detail="Selecione lancamentos da mesma natureza para alterar a categoria em massa",
        )

    expected_kind = next(iter(expected_kinds))
    if expected_kind == "transfer":
        raise HTTPException(status_code=400, detail="Transferencias nao podem ter categoria alterada em massa")
    if category.entry_kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail="A categoria selecionada nao e compativel com os lancamentos escolhidos",
        )

    updated_count = 0
    supplier_ids_to_refresh = {entry.supplier_id for entry in ordered_entries if entry.supplier_id}
    for entry in ordered_entries:
        if entry.category_id == category.id:
            continue
        before_state = _entry_dict(entry) | {"category_name": entry.category.name if entry.category else None}
        entry.category_id = category.id
        updated_count += 1
        write_audit_log(
            db,
            action="bulk_update_entry_category",
            entity_name="financial_entry",
            entity_id=entry.id,
            company_id=company.id,
            actor_user=actor_user,
            before_state=before_state,
            after_state=_entry_dict(entry) | {"category_name": category.name},
        )

    db.flush()
    _refresh_supplier_purchase_history_flags(db, company.id, supplier_ids_to_refresh)
    return updated_count, category, normalized_entry_ids


def _ensure_entry_can_be_deleted(
    db: Session,
    entry: FinancialEntry,
    *,
    allow_reconciled_generated: bool = False,
) -> None:
    if not allow_reconciled_generated and entry.status not in {"planned", "cancelled", "open"}:
        raise HTTPException(status_code=400, detail="Apenas lancamentos em aberto podem ser excluidos")
    if not allow_reconciled_generated and (Decimal(entry.paid_amount or 0) > Decimal("0.00") or entry.settled_at is not None):
        raise HTTPException(status_code=400, detail="Lancamento com baixa nao pode ser excluido")
    if entry.transfer_id or entry.loan_installment_id or entry.is_recurring_generated:
        raise HTTPException(status_code=400, detail="Lancamento vinculado a outro processo nao pode ser excluido")
    has_reconciliation = db.scalar(
        select(func.count())
        .select_from(Reconciliation)
        .where(Reconciliation.financial_entry_id == entry.id)
    ) or 0
    has_group_reconciliation = db.scalar(
        select(func.count())
        .select_from(ReconciliationLine)
        .where(ReconciliationLine.financial_entry_id == entry.id)
    ) or 0
    if not allow_reconciled_generated and (has_reconciliation or has_group_reconciliation):
        raise HTTPException(status_code=400, detail="Lancamento conciliado nao pode ser excluido")


def _detach_purchase_links_for_deleted_entry(db: Session, entry: FinancialEntry) -> None:
    if not entry.purchase_invoice_id and not entry.purchase_installment_id:
        return
    from app.services.purchase_planning import cleanup_deleted_purchase_entry

    cleanup_deleted_purchase_entry(db, entry)


def bulk_delete_entries(
    db: Session,
    company: Company,
    *,
    entry_ids: list[str],
    actor_user: User,
    allow_reconciled_generated: bool = False,
) -> tuple[int, list[str]]:
    normalized_entry_ids = list(dict.fromkeys(entry_ids))
    if not normalized_entry_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lancamento")

    entries = list(
        db.scalars(
            select(FinancialEntry).where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.id.in_(normalized_entry_ids),
            )
        )
    )
    if len(entries) != len(normalized_entry_ids):
        raise HTTPException(status_code=404, detail="Um ou mais lancamentos nao foram encontrados")

    entries_by_id = {entry.id: entry for entry in entries}
    ordered_entries = [entries_by_id[entry_id] for entry_id in normalized_entry_ids]

    for entry in ordered_entries:
        _ensure_entry_can_be_deleted(db, entry, allow_reconciled_generated=allow_reconciled_generated)

    supplier_ids_to_refresh = {entry.supplier_id for entry in ordered_entries if entry.supplier_id}
    for entry in ordered_entries:
        before_state = _entry_dict(entry)
        _detach_purchase_links_for_deleted_entry(db, entry)
        entry.is_deleted = True
        entry.status = "cancelled"
        write_audit_log(
            db,
            action="bulk_delete_entry",
            entity_name="financial_entry",
            entity_id=entry.id,
            company_id=company.id,
            actor_user=actor_user,
            before_state=before_state,
            after_state=_entry_dict(entry),
        )

    db.flush()
    _refresh_supplier_purchase_history_flags(db, company.id, supplier_ids_to_refresh)
    return len(ordered_entries), normalized_entry_ids


def settle_entry(
    db: Session,
    company: Company,
    entry_id: str,
    payload: EntrySettlementRequest,
    actor_user: User,
) -> FinancialEntry:
    entry = db.get(FinancialEntry, entry_id)
    if not entry or entry.company_id != company.id or entry.is_deleted:
        raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
    selected_account = _validate_account(db, company.id, payload.account_id)
    if entry.account_id is None:
        if selected_account is None:
            raise HTTPException(status_code=400, detail="Selecione uma conta antes de baixar a fatura")
        entry.account_id = selected_account.id
    _require_due_date_for_paid_status("settled", entry.due_date)
    before_state = _entry_dict(entry)
    cash_total, _generated_adjustments = apply_settlement_breakdown(
        db,
        company,
        entry,
        principal_amount=payload.principal_amount,
        interest_amount=payload.interest_amount,
        penalty_amount=payload.penalty_amount,
        discount_amount=payload.discount_amount,
        settled_at=payload.settled_at,
    )
    paid_amount = _money(payload.paid_amount if payload.paid_amount is not None else cash_total)
    if paid_amount != cash_total:
        raise HTTPException(
            status_code=400,
            detail="A baixa exige valor exato. Ajuste principal, juros, multa ou desconto antes de confirmar.",
        )
    entry.paid_amount = Decimal(entry.total_amount)
    entry.notes = payload.notes or entry.notes
    entry.settled_at = payload.settled_at or _settled_datetime(date.today())
    entry.status = "settled"

    if entry.loan_installment_id:
        installment = db.get(LoanInstallment, entry.loan_installment_id)
        if installment:
            installment.status = entry.status

    db.flush()
    write_audit_log(
        db,
        action="settle_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_entry_dict(entry),
    )
    return entry


def cancel_entry(
    db: Session,
    company: Company,
    entry_id: str,
    payload: EntryStatusRequest,
    actor_user: User,
) -> FinancialEntry:
    entry = db.get(FinancialEntry, entry_id)
    if not entry or entry.company_id != company.id or entry.is_deleted:
        raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
    before_state = _entry_dict(entry)
    entry.status = "cancelled"
    entry.notes = payload.notes or entry.notes
    db.flush()
    write_audit_log(
        db,
        action="cancel_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_entry_dict(entry),
    )
    return entry


def reverse_entry(
    db: Session,
    company: Company,
    entry_id: str,
    payload: EntryStatusRequest,
    actor_user: User,
) -> FinancialEntry:
    entry = db.get(FinancialEntry, entry_id)
    if not entry or entry.company_id != company.id or entry.is_deleted:
        raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
    before_state = _entry_dict(entry)
    entry.status = "planned"
    entry.paid_amount = Decimal("0.00")
    entry.settled_at = None
    entry.notes = payload.notes or entry.notes
    db.flush()
    write_audit_log(
        db,
        action="reverse_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_entry_dict(entry),
    )
    return entry


def delete_entry(
    db: Session,
    company: Company,
    entry_id: str,
    actor_user: User,
    *,
    allow_reconciled_generated: bool = False,
) -> FinancialEntry:
    entry = db.get(FinancialEntry, entry_id)
    if not entry or entry.company_id != company.id or entry.is_deleted:
        raise HTTPException(status_code=404, detail="Lancamento nao encontrado")
    _ensure_entry_can_be_deleted(db, entry, allow_reconciled_generated=allow_reconciled_generated)
    before_state = _entry_dict(entry)
    supplier_ids_to_refresh = {entry.supplier_id} if entry.supplier_id else set()
    _detach_purchase_links_for_deleted_entry(db, entry)
    entry.is_deleted = True
    entry.status = "cancelled"
    db.flush()
    _refresh_supplier_purchase_history_flags(db, company.id, supplier_ids_to_refresh)
    write_audit_log(
        db,
        action="delete_entry",
        entity_name="financial_entry",
        entity_id=entry.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state=_entry_dict(entry),
    )
    return entry


def create_transfer(db: Session, company: Company, payload: TransferCreate, actor_user: User) -> Transfer:
    source_account = _validate_account(db, company.id, payload.source_account_id)
    destination_account = _validate_account(db, company.id, payload.destination_account_id)
    if source_account is None or destination_account is None:
        raise HTTPException(status_code=400, detail="Contas de transferencia invalidas")
    if source_account.id == destination_account.id:
        raise HTTPException(status_code=400, detail="Contas de origem e destino devem ser diferentes")

    transfer = Transfer(
        company_id=company.id,
        source_account_id=source_account.id,
        destination_account_id=destination_account.id,
        transfer_date=payload.transfer_date,
        amount=_money(payload.amount),
        status=payload.status,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(transfer)
    db.flush()

    source_entry = FinancialEntry(
        company_id=company.id,
        transfer_id=transfer.id,
        account_id=source_account.id,
        entry_type="transfer",
        status=payload.status,
        title=f"Transferencia para {destination_account.name}",
        description=payload.description,
        notes=payload.notes,
        counterparty_name=destination_account.name,
        issue_date=payload.transfer_date,
        competence_date=payload.transfer_date,
        due_date=payload.transfer_date,
        settled_at=_settled_datetime(payload.transfer_date) if payload.status == "settled" else None,
        principal_amount=_money(payload.amount),
        total_amount=_money(payload.amount),
        paid_amount=_money(payload.amount) if payload.status == "settled" else Decimal("0.00"),
        source_system="manual",
    )
    destination_entry = FinancialEntry(
        company_id=company.id,
        transfer_id=transfer.id,
        account_id=destination_account.id,
        entry_type="transfer",
        status=payload.status,
        title=f"Transferencia de {source_account.name}",
        description=payload.description,
        notes=payload.notes,
        counterparty_name=source_account.name,
        issue_date=payload.transfer_date,
        competence_date=payload.transfer_date,
        due_date=payload.transfer_date,
        settled_at=_settled_datetime(payload.transfer_date) if payload.status == "settled" else None,
        principal_amount=_money(payload.amount),
        total_amount=_money(payload.amount),
        paid_amount=_money(payload.amount) if payload.status == "settled" else Decimal("0.00"),
        source_system="manual",
    )
    db.add(source_entry)
    db.add(destination_entry)
    db.flush()
    transfer.source_entry_id = source_entry.id
    transfer.destination_entry_id = destination_entry.id
    db.flush()

    write_audit_log(
        db,
        action="create_transfer",
        entity_name="transfer",
        entity_id=transfer.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "source_account_id": transfer.source_account_id,
            "destination_account_id": transfer.destination_account_id,
            "amount": f"{transfer.amount:.2f}",
            "status": transfer.status,
        },
    )
    return transfer


def list_transfers(db: Session, company: Company, limit: int = 200) -> list[Transfer]:
    return list(
        db.scalars(
            select(Transfer)
            .where(Transfer.company_id == company.id)
            .order_by(Transfer.transfer_date.desc(), Transfer.created_at.desc())
            .limit(limit)
        )
    )


def list_recurrence_rules(db: Session, company: Company) -> list[RecurrenceRule]:
    return list(
        db.scalars(
            select(RecurrenceRule)
            .where(RecurrenceRule.company_id == company.id)
            .order_by(RecurrenceRule.is_active.desc(), RecurrenceRule.name.asc())
        )
    )


def create_recurrence_rule(
    db: Session,
    company: Company,
    payload: RecurrenceRuleCreate,
    actor_user: User,
) -> RecurrenceRule:
    _validate_account(db, company.id, payload.account_id)
    _validate_category(db, company.id, payload.category_id, allow_transfer=True)
    _validate_category(db, company.id, payload.interest_category_id, allow_transfer=True)
    rule = RecurrenceRule(company_id=company.id, **payload.model_dump())
    db.add(rule)
    db.flush()
    write_audit_log(
        db,
        action="create_recurrence",
        entity_name="recurrence_rule",
        entity_id=rule.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={"name": rule.name, "frequency": rule.frequency},
    )
    return rule


def update_recurrence_rule(
    db: Session,
    company: Company,
    rule_id: str,
    payload: RecurrenceRuleUpdate,
    actor_user: User,
) -> RecurrenceRule:
    rule = db.get(RecurrenceRule, rule_id)
    if not rule or rule.company_id != company.id:
        raise HTTPException(status_code=404, detail="Recorrencia nao encontrada")
    before_state = {"name": rule.name, "frequency": rule.frequency, "is_active": rule.is_active}
    for field_name, value in payload.model_dump().items():
        setattr(rule, field_name, value)
    db.flush()
    write_audit_log(
        db,
        action="update_recurrence",
        entity_name="recurrence_rule",
        entity_id=rule.id,
        company_id=company.id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"name": rule.name, "frequency": rule.frequency, "is_active": rule.is_active},
    )
    return rule


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = value.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def _next_occurrence(rule: RecurrenceRule, current: date) -> date:
    if rule.frequency == "weekly":
        from datetime import timedelta

        return current + timedelta(days=7 * rule.interval_value)
    if rule.frequency == "monthly":
        base = _add_months(current, rule.interval_value)
        if rule.day_of_month:
            day = min(rule.day_of_month, 28 if base.month == 2 else 31)
            try:
                return date(base.year, base.month, day)
            except ValueError:
                return _add_months(date(base.year, base.month, 1), 1)
        return base
    if rule.frequency == "yearly":
        return date(current.year + rule.interval_value, current.month, current.day)
    from datetime import timedelta

    return current + timedelta(days=rule.interval_value)


def generate_recurrence_entries(
    db: Session,
    company: Company,
    payload: RecurrenceGenerationRequest,
    actor_user: User | None = None,
) -> int:
    generated = 0
    for rule in db.scalars(
        select(RecurrenceRule).where(
            RecurrenceRule.company_id == company.id,
            RecurrenceRule.is_active.is_(True),
        )
    ):
        next_run = rule.next_run_date or rule.start_date
        while next_run and next_run <= payload.until_date:
            source_reference = f"recurrence:{rule.id}:{next_run.isoformat()}"
            exists = db.scalar(
                select(FinancialEntry).where(
                    FinancialEntry.company_id == company.id,
                    FinancialEntry.source_reference == source_reference,
                )
            )
            if not exists:
                entry = FinancialEntry(
                    company_id=company.id,
                    account_id=rule.account_id,
                    category_id=rule.category_id,
                    interest_category_id=rule.interest_category_id,
                    recurrence_rule_id=rule.id,
                    entry_type=rule.entry_type,
                    status="planned",
                    title=rule.title_template or rule.name,
                    description=rule.description,
                    notes=rule.notes,
                    counterparty_name=rule.counterparty_name,
                    document_number=rule.document_number,
                    issue_date=next_run,
                    competence_date=next_run,
                    due_date=next_run,
                    principal_amount=_money(rule.principal_amount or rule.amount),
                    interest_amount=_money(rule.interest_amount),
                    discount_amount=_money(rule.discount_amount),
                    penalty_amount=_money(rule.penalty_amount),
                    total_amount=_money(
                        Decimal(rule.principal_amount or rule.amount)
                        + Decimal(rule.interest_amount or 0)
                        + Decimal(rule.penalty_amount or 0)
                        - Decimal(rule.discount_amount or 0)
                    ),
                    source_system="recurrence",
                    source_reference=source_reference,
                    is_recurring_generated=True,
                )
                db.add(entry)
                db.flush()
                generated += 1
            next_run = _next_occurrence(rule, next_run)
            if rule.end_date and next_run > rule.end_date:
                next_run = None
        rule.next_run_date = next_run
    if generated and actor_user:
        write_audit_log(
            db,
            action="generate_recurrence_entries",
            entity_name="recurrence_rule",
            entity_id=company.id,
            company_id=company.id,
            actor_user=actor_user,
            after_state={"generated": generated, "until_date": payload.until_date.isoformat()},
        )
    return generated


def list_loans(db: Session, company: Company) -> list[LoanContract]:
    return list(
        db.scalars(
            select(LoanContract)
            .where(LoanContract.company_id == company.id)
            .order_by(LoanContract.start_date.desc(), LoanContract.created_at.desc())
        )
    )


def create_loan_contract(
    db: Session,
    company: Company,
    payload: LoanContractCreate,
    actor_user: User,
) -> LoanContract:
    _validate_account(db, company.id, payload.account_id)
    _validate_category(db, company.id, payload.category_id, allow_transfer=True)
    interest_category_id = payload.interest_category_id
    if payload.interest_total > 0 and not interest_category_id:
        interest_category_id = ensure_default_financial_category(db, company.id).id
    _validate_category(db, company.id, interest_category_id, allow_transfer=True)

    principal_installment = _money(payload.principal_total / payload.installments_count)
    interest_installment = _money(payload.interest_total / payload.installments_count) if payload.interest_total else Decimal("0.00")
    installment_amount = _money(principal_installment + interest_installment)

    contract = LoanContract(
        company_id=company.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        interest_category_id=interest_category_id,
        lender_name=payload.lender_name,
        contract_number=payload.contract_number,
        title=payload.title,
        start_date=payload.start_date,
        first_due_date=payload.first_due_date,
        installments_count=payload.installments_count,
        principal_total=_money(payload.principal_total),
        interest_total=_money(payload.interest_total),
        installment_amount=installment_amount,
        notes=payload.notes,
        is_active=True,
    )
    db.add(contract)
    db.flush()

    due_date = payload.first_due_date
    remaining_principal = _money(payload.principal_total)
    remaining_interest = _money(payload.interest_total)
    for installment_number in range(1, payload.installments_count + 1):
        principal = principal_installment if installment_number < payload.installments_count else remaining_principal
        interest = interest_installment if installment_number < payload.installments_count else remaining_interest
        total = _money(principal + interest)
        entry = FinancialEntry(
            company_id=company.id,
            account_id=payload.account_id,
            category_id=payload.category_id,
            interest_category_id=interest_category_id,
            entry_type="expense",
            status="planned",
            title=f"{payload.title} - Parcela {installment_number}/{payload.installments_count}",
            counterparty_name=payload.lender_name,
            document_number=payload.contract_number,
            issue_date=payload.start_date,
            competence_date=due_date,
            due_date=due_date,
            principal_amount=_money(principal),
            interest_amount=_money(interest),
            total_amount=total,
            source_system="loan",
            source_reference=f"loan:{contract.id}:{installment_number}",
        )
        db.add(entry)
        db.flush()

        installment = LoanInstallment(
            company_id=company.id,
            contract_id=contract.id,
            installment_number=installment_number,
            due_date=due_date,
            principal_amount=_money(principal),
            interest_amount=_money(interest),
            total_amount=total,
            status="planned",
            financial_entry_id=entry.id,
        )
        db.add(installment)
        db.flush()
        entry.loan_installment_id = installment.id

        remaining_principal = _money(remaining_principal - principal)
        remaining_interest = _money(remaining_interest - interest)
        due_date = _add_months(due_date, 1)

    write_audit_log(
        db,
        action="create_loan_contract",
        entity_name="loan_contract",
        entity_id=contract.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={"installments_count": payload.installments_count, "principal_total": f"{payload.principal_total:.2f}"},
    )
    return contract

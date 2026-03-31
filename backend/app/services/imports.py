import hashlib
import unicodedata
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models.banking import BankTransaction
from app.db.models.finance import Account, Category, FinancialEntry
from app.db.models.imports import ImportBatch
from app.db.models.linx import ReceivableTitle, SalesSnapshot
from app.db.models.purchasing import CollectionSeason, Supplier
from app.db.models.security import Company
from app.schemas.imports import ImportResult, ImportSummary
from app.services.category_catalog import (
    ensure_category_catalog,
    match_historical_category_name,
)
from app.services.import_parsers import (
    ParsedOfxTransaction,
    ParsedReceivableRow,
    ParsedSalesRow,
    _read_xlsx_workbook,
    fingerprint_bytes,
    normalize_label,
    parse_historical_cashbook_rows,
    parse_ofx_transactions,
    parse_receivable_rows,
    parse_sales_rows,
    prepare_linx_receivables_payload,
)

HISTORICAL_CASHBOOK_SOURCE = "historical_cashbook"
HISTORICAL_ACCOUNT_NAME = "Movimentacoes Antigas"
HISTORICAL_ACCOUNT_TYPE = "historical"
ELECTRONIC_RECEIVABLE_ACCOUNT_NAME = "Recebiveis Cartao, Debito e Pix"
ELECTRONIC_RECEIVABLE_ACCOUNT_TYPE = "receivables_control"
ELECTRONIC_RECEIVABLE_SOURCE = "linx_sales_control"
ELECTRONIC_RECEIVABLE_METHODS = {
    "card": "Cartao e Debito a Receber",
    "pix": "Pix a Receber",
}

TRANSFER_KEYWORDS = (
    "transfer",
    "transf",
    "sangria",
    "suprimento",
    "adiant",
    "aplicac",
    "resgate",
)
PURCHASE_KEYWORDS = ("compra", "fornecedor", "nf recepcao", "nf atacado")
PURCHASE_RETURN_KEYWORDS = ("devolucaodecompra", "estornodafatura")
FINANCIAL_EXPENSE_KEYWORDS = (
    "despesasbancarias",
    "juros",
    "iof",
    "tarifa",
    "multa",
    "encargo",
)
ADJUSTMENT_KEYWORDS = (
    "ajuste",
    "quebradecaixa",
    "divisaodelucros",
    "aportedecapital",
    "vendasnaolancadas",
)
HISTORICAL_STRUCTURED_ENTRY_TYPE_ALIASES = {
    "expense": "expense",
    "despesa": "expense",
    "income": "income",
    "receita": "income",
    "historicalpurchase": "historical_purchase",
    "comprahistorica": "historical_purchase",
    "historicalreceipt": "historical_receipt",
    "recebimentohistorico": "historical_receipt",
    "historicalpurchasereturn": "historical_purchase_return",
    "devolucaodecomprahistorica": "historical_purchase_return",
    "adjustment": "adjustment",
    "ajuste": "adjustment",
    "transfer": "transfer",
    "transferencia": "transfer",
}
HISTORICAL_STRUCTURED_STATUS_ALIASES = {
    "planned": "planned",
    "aberto": "planned",
    "previsto": "planned",
    "partial": "partial",
    "parcial": "partial",
    "settled": "settled",
    "baixado": "settled",
    "liquidado": "settled",
    "pago": "settled",
    "cancelled": "cancelled",
    "cancelado": "cancelled",
}
HISTORICAL_INCOME_ENTRY_TYPES = {"income", "historical_receipt", "historical_purchase_return"}
HISTORICAL_EXPENSE_ENTRY_TYPES = {"expense", "historical_purchase", "adjustment"}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[: max_length - 3].rstrip() + "..."


def _money(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _historical_settled_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _ensure_historical_account(db: Session, company_id: str) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.name == HISTORICAL_ACCOUNT_NAME,
        )
    )
    if account:
        if account.is_active:
            account.is_active = False
            db.flush()
        return account

    account = Account(
        company_id=company_id,
        name=HISTORICAL_ACCOUNT_NAME,
        account_type=HISTORICAL_ACCOUNT_TYPE,
        opening_balance=Decimal("0.00"),
        is_active=False,
    )
    db.add(account)
    db.flush()
    return account


def _ensure_electronic_receivables_account(db: Session, company_id: str) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.name == ELECTRONIC_RECEIVABLE_ACCOUNT_NAME,
        )
    )
    if account:
        if account.account_type != ELECTRONIC_RECEIVABLE_ACCOUNT_TYPE:
            account.account_type = ELECTRONIC_RECEIVABLE_ACCOUNT_TYPE
        if not account.is_active:
            account.is_active = True
        db.flush()
        return account

    account = Account(
        company_id=company_id,
        name=ELECTRONIC_RECEIVABLE_ACCOUNT_NAME,
        account_type=ELECTRONIC_RECEIVABLE_ACCOUNT_TYPE,
        opening_balance=Decimal("0.00"),
        is_active=True,
    )
    db.add(account)
    db.flush()
    return account


def deactivate_electronic_receivables_account(db: Session, company_id: str) -> bool:
    account = db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.name == ELECTRONIC_RECEIVABLE_ACCOUNT_NAME,
        )
    )
    if not account or not account.is_active:
        return False
    account.is_active = False
    db.flush()
    return True


def cleanup_open_linx_sales_entries(db: Session, company_id: str) -> int:
    entries = list(
        db.scalars(
            select(FinancialEntry).where(
                FinancialEntry.company_id == company_id,
                FinancialEntry.entry_type == "income",
                FinancialEntry.source_system == ELECTRONIC_RECEIVABLE_SOURCE,
                FinancialEntry.status.in_(["planned", "partial"]),
                FinancialEntry.is_deleted.is_(False),
            )
        )
    )
    for entry in entries:
        entry.is_deleted = True
        entry.status = "cancelled"
    if entries:
        db.flush()
    return len(entries)


def _electronic_receivable_source_reference(snapshot_date: date, method: str) -> str:
    return f"{ELECTRONIC_RECEIVABLE_SOURCE}:{snapshot_date.isoformat()}:{method}"


def _sync_sales_control_entries(
    db: Session,
    company: Company,
    rows: list[ParsedSalesRow],
) -> None:
    control_account = _ensure_electronic_receivables_account(db, company.id)
    target_dates = {row.snapshot_date for row in rows}
    if not target_dates:
        return

    existing_entries = {
        entry.source_reference or "": entry
        for entry in db.scalars(
            select(FinancialEntry).where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.source_system == ELECTRONIC_RECEIVABLE_SOURCE,
                FinancialEntry.issue_date.in_(target_dates),
                FinancialEntry.is_deleted.is_(False),
            )
        )
    }

    desired_refs: set[str] = set()
    for row in rows:
        method_amounts = {
            "card": Decimal(row.card_revenue or 0),
            "pix": Decimal(row.pix_revenue or 0),
        }
        for method, label in ELECTRONIC_RECEIVABLE_METHODS.items():
            amount = Decimal(method_amounts.get(method, Decimal("0.00")))
            source_reference = _electronic_receivable_source_reference(row.snapshot_date, method)
            desired_refs.add(source_reference)
            existing = existing_entries.get(source_reference)

            if amount <= Decimal("0.00"):
                if existing and Decimal(existing.paid_amount or 0) <= Decimal("0.00"):
                    existing.is_deleted = True
                    existing.status = "cancelled"
                continue

            if not existing:
                existing = FinancialEntry(
                    company_id=company.id,
                    account_id=control_account.id,
                    entry_type="income",
                    status="planned",
                    title=f"{label} {row.snapshot_date.isoformat()}",
                    issue_date=row.snapshot_date,
                    competence_date=row.snapshot_date,
                    due_date=row.snapshot_date,
                    principal_amount=amount,
                    total_amount=amount,
                    paid_amount=Decimal("0.00"),
                    external_source=ELECTRONIC_RECEIVABLE_SOURCE,
                    source_system=ELECTRONIC_RECEIVABLE_SOURCE,
                    source_reference=source_reference,
                    counterparty_name=label,
                )
                db.add(existing)
                db.flush()

            existing.account_id = control_account.id
            existing.entry_type = "income"
            existing.title = f"{label} {row.snapshot_date.isoformat()}"
            existing.issue_date = row.snapshot_date
            existing.competence_date = row.snapshot_date
            existing.due_date = row.snapshot_date
            existing.principal_amount = amount
            existing.total_amount = amount
            existing.external_source = ELECTRONIC_RECEIVABLE_SOURCE
            existing.source_system = ELECTRONIC_RECEIVABLE_SOURCE
            existing.counterparty_name = label
            existing.is_deleted = False

            paid_amount = min(Decimal(existing.paid_amount or 0), amount)
            existing.paid_amount = paid_amount
            if paid_amount <= Decimal("0.00"):
                existing.status = "planned"
                existing.settled_at = None
            elif paid_amount < amount:
                existing.status = "partial"
            else:
                existing.status = "settled"

    for source_reference, entry in existing_entries.items():
        if source_reference in desired_refs:
            continue
        if Decimal(entry.paid_amount or 0) <= Decimal("0.00"):
            entry.is_deleted = True
            entry.status = "cancelled"

    db.flush()


def _classify_historical_cashbook_row(history: str, inflow: bool) -> tuple[str, str]:
    normalized_history = "".join(
        char
        for char in unicodedata.normalize("NFKD", history.lower())
        if not unicodedata.combining(char)
    )
    normalized_history = "".join(char for char in normalized_history if char.isalnum())

    if any(keyword in normalized_history for keyword in PURCHASE_RETURN_KEYWORDS):
        return ("historical_purchase_return", "purchase_return")
    if any(keyword in normalized_history for keyword in PURCHASE_KEYWORDS):
        return ("historical_purchase", "purchase")
    if any(keyword in normalized_history for keyword in TRANSFER_KEYWORDS):
        return ("transfer", "transfer")
    if any(keyword in normalized_history for keyword in ADJUSTMENT_KEYWORDS):
        return ("adjustment", "adjustment")
    if inflow:
        return ("historical_receipt", "receipt")
    if any(keyword in normalized_history for keyword in FINANCIAL_EXPENSE_KEYWORDS):
        return ("expense", "financial_expense")
    return ("expense", "expense")


def _historical_source_reference(
    row_date: str,
    source_account: str,
    launch_number: str | None,
    document_number: str | None,
    reference: str | None,
    history: str,
    debit_amount: Decimal,
    credit_amount: Decimal,
) -> str:
    payload = "|".join(
        [
            row_date,
            _normalize_text(source_account),
            launch_number or "",
            document_number or "",
            reference or "",
            _normalize_text(history),
            f"{debit_amount:.2f}",
            f"{credit_amount:.2f}",
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:32]


def _structured_historical_source_reference(
    *,
    due_date: date | None,
    issue_date: date | None,
    title: str,
    document_number: str | None,
    category_code: str | None,
    category_name: str | None,
    supplier_name: str | None,
    collection_name: str | None,
    principal_amount: Decimal,
    interest_amount: Decimal,
    discount_amount: Decimal,
    penalty_amount: Decimal,
    total_amount: Decimal,
) -> str:
    payload = "|".join(
        [
            due_date.isoformat() if due_date else "",
            issue_date.isoformat() if issue_date else "",
            _normalize_text(title),
            document_number or "",
            _normalize_text(category_code or ""),
            _normalize_text(category_name or ""),
            _normalize_text(supplier_name or ""),
            _normalize_text(collection_name or ""),
            f"{principal_amount:.2f}",
            f"{interest_amount:.2f}",
            f"{discount_amount:.2f}",
            f"{penalty_amount:.2f}",
            f"{total_amount:.2f}",
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:32]


def _pick_single_lookup_match(
    matches: list,
    *,
    entity_label: str,
    lookup_value: str,
    row_label: str,
):
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    active_matches = [item for item in matches if getattr(item, "is_active", True)]
    if len(active_matches) == 1:
        return active_matches[0]
    raise ValueError(f"{row_label}: {entity_label} '{lookup_value}' retornou mais de um cadastro.")


def _resolve_structured_category(
    row,
    *,
    categories_by_code: dict[str, list[Category]],
    categories_by_name: dict[str, list[Category]],
) -> Category:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    if row.category_code:
        category = _pick_single_lookup_match(
            categories_by_code.get(normalize_label(row.category_code), []),
            entity_label="Categoria",
            lookup_value=row.category_code,
            row_label=row_label,
        )
        if category is not None:
            return category
    if row.category_name:
        category = _pick_single_lookup_match(
            categories_by_name.get(normalize_label(row.category_name), []),
            entity_label="Categoria",
            lookup_value=row.category_name,
            row_label=row_label,
        )
        if category is not None:
            return category
    raise ValueError(
        f"{row_label}: categoria nao encontrada (preencha category_code ou category_name com valor existente)."
    )


def _resolve_or_create_structured_category(
    db: Session,
    company_id: str,
    row,
    *,
    categories_by_code: dict[str, list[Category]],
    categories_by_name: dict[str, list[Category]],
) -> Category:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    if row.category_code:
        category = _pick_single_lookup_match(
            categories_by_code.get(normalize_label(row.category_code), []),
            entity_label="Categoria",
            lookup_value=row.category_code,
            row_label=row_label,
        )
        if category is not None:
            return category
    if row.category_name:
        name_lookup = normalize_label(row.category_name)
        category = _pick_single_lookup_match(
            categories_by_name.get(name_lookup, []),
            entity_label="Categoria",
            lookup_value=row.category_name,
            row_label=row_label,
        )
        if category is not None:
            return category

        category = Category(
            company_id=company_id,
            code=None,
            name=row.category_name.strip(),
            entry_kind=_entry_kind_from_support_value(row.entry_type),
            report_group=None,
            report_subgroup=None,
            is_financial_expense=False,
            is_active=True,
        )
        db.add(category)
        db.flush()
        categories_by_name.setdefault(name_lookup, []).append(category)
        return category
    raise ValueError(
        f"{row_label}: categoria nao encontrada (preencha category_code ou category_name com valor existente)."
    )


def _resolve_structured_interest_category(
    row,
    *,
    categories_by_code: dict[str, list[Category]],
    categories_by_name: dict[str, list[Category]],
) -> Category | None:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    if row.interest_category_code:
        category = _pick_single_lookup_match(
            categories_by_code.get(normalize_label(row.interest_category_code), []),
            entity_label="Categoria de juros",
            lookup_value=row.interest_category_code,
            row_label=row_label,
        )
        if category is not None:
            return category
    if row.interest_category_name:
        category = _pick_single_lookup_match(
            categories_by_name.get(normalize_label(row.interest_category_name), []),
            entity_label="Categoria de juros",
            lookup_value=row.interest_category_name,
            row_label=row_label,
        )
        if category is not None:
            return category
    if row.interest_category_code or row.interest_category_name:
        raise ValueError(f"{row_label}: categoria de juros nao encontrada.")
    return None


def _resolve_structured_supplier(
    row,
    *,
    suppliers_by_name: dict[str, list[Supplier]],
    suppliers_by_document: dict[str, list[Supplier]],
) -> Supplier | None:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    document_lookup = normalize_label(row.supplier_document_number or "")
    name_lookup = normalize_label(row.supplier_name or "")

    if document_lookup:
        document_matches = suppliers_by_document.get(document_lookup, [])
        if name_lookup:
            document_matches = [
                supplier
                for supplier in document_matches
                if normalize_label(supplier.name or "") == name_lookup
            ]
        supplier = _pick_single_lookup_match(
            document_matches,
            entity_label="Fornecedor",
            lookup_value=row.supplier_document_number or "",
            row_label=row_label,
        )
        if supplier is not None:
            return supplier
    if name_lookup:
        supplier = _pick_single_lookup_match(
            suppliers_by_name.get(name_lookup, []),
            entity_label="Fornecedor",
            lookup_value=row.supplier_name or "",
            row_label=row_label,
        )
        if supplier is not None:
            return supplier
    if row.supplier_name or row.supplier_document_number:
        raise ValueError(f"{row_label}: fornecedor nao encontrado.")
    return None


def _resolve_or_create_structured_supplier(
    db: Session,
    company_id: str,
    row,
    *,
    suppliers_by_name: dict[str, list[Supplier]],
    suppliers_by_document: dict[str, list[Supplier]],
) -> Supplier | None:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    document_lookup = normalize_label(row.supplier_document_number or "")
    name_lookup = normalize_label(row.supplier_name or "")

    if document_lookup:
        document_matches = suppliers_by_document.get(document_lookup, [])
        if name_lookup:
            document_matches = [
                supplier
                for supplier in document_matches
                if normalize_label(supplier.name or "") == name_lookup
            ]
        supplier = _pick_single_lookup_match(
            document_matches,
            entity_label="Fornecedor",
            lookup_value=row.supplier_document_number or "",
            row_label=row_label,
        )
        if supplier is not None:
            return supplier
    if name_lookup:
        supplier = _pick_single_lookup_match(
            suppliers_by_name.get(name_lookup, []),
            entity_label="Fornecedor",
            lookup_value=row.supplier_name or "",
            row_label=row_label,
        )
        if supplier is not None:
            return supplier

    if row.supplier_name or row.supplier_document_number:
        supplier_name = (
            (row.supplier_name or "").strip()
            or (row.counterparty_name or "").strip()
            or (row.title or "").strip()
            or "Fornecedor historico"
        )[:180]
        document_number = (row.supplier_document_number or "").strip() or None
        supplier = Supplier(
            company_id=company_id,
            name=supplier_name,
            document_number=document_number,
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        suppliers_by_name.setdefault(normalize_label(supplier.name), []).append(supplier)
        if supplier.document_number:
            suppliers_by_document.setdefault(normalize_label(supplier.document_number), []).append(
                supplier
            )
        return supplier
    return None


def _resolve_structured_collection(
    row,
    *,
    collections_by_name: dict[str, list[CollectionSeason]],
) -> CollectionSeason | None:
    if not row.collection_name:
        return None
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    collection = _pick_single_lookup_match(
        collections_by_name.get(normalize_label(row.collection_name), []),
        entity_label="Colecao",
        lookup_value=row.collection_name,
        row_label=row_label,
    )
    if collection is None:
        raise ValueError(f"{row_label}: colecao nao encontrada.")
    return collection


def _resolve_structured_entry_type(row, category: Category) -> str:
    raw_entry_type = normalize_label(row.entry_type or "")
    if raw_entry_type:
        entry_type = HISTORICAL_STRUCTURED_ENTRY_TYPE_ALIASES.get(raw_entry_type)
        if entry_type is None:
            raise ValueError(
                f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: entry_type invalido."
            )
    elif category.entry_kind == "income":
        entry_type = "historical_receipt"
    elif category.entry_kind == "transfer":
        entry_type = "transfer"
    else:
        entry_type = "expense"

    if category.entry_kind == "transfer" and entry_type != "transfer":
        raise ValueError(
            f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: categoria de transferencia exige entry_type transfer."
        )
    if category.entry_kind == "income" and entry_type not in HISTORICAL_INCOME_ENTRY_TYPES:
        raise ValueError(
            f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: categoria de receita exige entry_type de entrada."
        )
    if category.entry_kind == "expense" and entry_type not in HISTORICAL_EXPENSE_ENTRY_TYPES:
        raise ValueError(
            f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: categoria de despesa exige entry_type de saida."
        )
    return entry_type


def _resolve_structured_status(row, *, total_amount: Decimal, paid_amount: Decimal | None) -> str:
    raw_status = normalize_label(row.status or "")
    if raw_status:
        status = HISTORICAL_STRUCTURED_STATUS_ALIASES.get(raw_status)
        if status is None:
            raise ValueError(
                f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: status invalido."
            )
        return status
    if paid_amount is None:
        return "settled"
    if paid_amount <= Decimal("0.00"):
        return "planned"
    if paid_amount >= total_amount:
        return "settled"
    return "partial"


def _resolve_structured_amounts(row) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal | None]:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    principal_amount = _money(row.principal_amount or 0)
    interest_amount = _money(row.interest_amount or 0)
    discount_amount = _money(row.discount_amount or 0)
    penalty_amount = _money(row.penalty_amount or 0)
    calculated_total = _money(principal_amount + interest_amount + penalty_amount - discount_amount)
    total_amount = _money(row.total_amount if row.total_amount is not None else calculated_total)
    if total_amount != calculated_total:
        raise ValueError(
            f"{row_label}: total_amount deve ser igual a principal_amount + interest_amount + penalty_amount - discount_amount."
        )
    if total_amount <= Decimal("0.00"):
        raise ValueError(f"{row_label}: total_amount deve ser maior que zero.")
    paid_amount = _money(row.paid_amount) if row.paid_amount is not None else None
    expected_amount = _money(row.expected_amount) if row.expected_amount is not None else None
    return (
        principal_amount,
        interest_amount,
        discount_amount,
        penalty_amount,
        total_amount,
        paid_amount if paid_amount is not None else Decimal("0.00"),
        expected_amount,
    )


def _resolve_structured_dates(row) -> tuple[date, date, date]:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    due_date = row.due_date
    if due_date is None:
        raise ValueError(f"{row_label}: due_date e obrigatoria.")
    issue_date = row.issue_date or due_date
    competence_date = row.competence_date or issue_date or due_date
    return issue_date, competence_date, due_date


def _validate_structured_status_amounts(
    row,
    *,
    status: str,
    total_amount: Decimal,
    paid_amount: Decimal,
) -> None:
    row_label = f"Aba '{row.sheet_name}', linha {row.sheet_row_number}"
    if paid_amount < Decimal("0.00"):
        raise ValueError(f"{row_label}: paid_amount nao pode ser negativo.")
    if paid_amount > total_amount:
        raise ValueError(f"{row_label}: paid_amount nao pode ser maior que total_amount.")
    if status == "planned" and paid_amount != Decimal("0.00"):
        raise ValueError(f"{row_label}: status planned exige paid_amount zerado.")
    if status == "cancelled" and paid_amount != Decimal("0.00"):
        raise ValueError(f"{row_label}: status cancelled exige paid_amount zerado.")
    if status in {"planned", "cancelled"} and row.settled_at is not None:
        raise ValueError(f"{row_label}: settled_at so pode ser informado para linhas baixadas/parciais.")
    if status == "partial" and (paid_amount <= Decimal("0.00") or paid_amount >= total_amount):
        raise ValueError(f"{row_label}: status partial exige paid_amount maior que zero e menor que total_amount.")


def _build_historical_structured_lookups(
    db: Session,
    company_id: str,
) -> tuple[
    dict[str, list[Category]],
    dict[str, list[Category]],
    dict[str, list[Supplier]],
    dict[str, list[Supplier]],
    dict[str, list[CollectionSeason]],
]:
    categories = list(
        db.scalars(select(Category).where(Category.company_id == company_id))
    )
    suppliers = list(
        db.scalars(select(Supplier).where(Supplier.company_id == company_id))
    )
    collections = list(
        db.scalars(select(CollectionSeason).where(CollectionSeason.company_id == company_id))
    )

    categories_by_code: dict[str, list[Category]] = {}
    categories_by_name: dict[str, list[Category]] = {}
    for category in categories:
        if category.code:
            categories_by_code.setdefault(normalize_label(category.code), []).append(category)
        categories_by_name.setdefault(normalize_label(category.name), []).append(category)

    suppliers_by_name: dict[str, list[Supplier]] = {}
    suppliers_by_document: dict[str, list[Supplier]] = {}
    for supplier in suppliers:
        suppliers_by_name.setdefault(normalize_label(supplier.name), []).append(supplier)
        if supplier.document_number:
            suppliers_by_document.setdefault(normalize_label(supplier.document_number), []).append(
                supplier
            )

    collections_by_name: dict[str, list[CollectionSeason]] = {}
    for collection in collections:
        collections_by_name.setdefault(normalize_label(collection.name), []).append(collection)

    return (
        categories_by_code,
        categories_by_name,
        suppliers_by_name,
        suppliers_by_document,
        collections_by_name,
    )


def _read_historical_support_sheet(content: bytes, *, sheet_name: str) -> list[dict[str, str]]:
    target_sheet = normalize_label(sheet_name)
    for current_sheet_name, parsed_rows in _read_xlsx_workbook(content):
        if normalize_label(current_sheet_name) != target_sheet or not parsed_rows:
            continue

        header_row = parsed_rows[0]
        header_map = {
            column: normalize_label(raw_value or "")
            for column, raw_value in header_row.items()
            if normalize_label(raw_value or "")
        }
        structured_rows: list[dict[str, str]] = []
        for parsed_row in parsed_rows[1:]:
            row = {
                field_name: (parsed_row.get(column) or "").strip()
                for column, field_name in header_map.items()
            }
            if any(value for value in row.values()):
                structured_rows.append(row)
        return structured_rows
    return []


def _entry_kind_from_support_value(value: str | None) -> str:
    entry_type = HISTORICAL_STRUCTURED_ENTRY_TYPE_ALIASES.get(normalize_label(value or ""), "")
    if entry_type in HISTORICAL_INCOME_ENTRY_TYPES:
        return "income"
    if entry_type == "transfer":
        return "transfer"
    return "expense"


def _ensure_historical_support_categories(db: Session, company_id: str, content: bytes) -> int:
    rows = _read_historical_support_sheet(content, sheet_name="CategoriasCriar")
    if not rows:
        return 0

    existing_by_name = {
        normalize_label(category.name): category
        for category in db.scalars(select(Category).where(Category.company_id == company_id))
    }
    created = 0

    for row in rows:
        action = normalize_label(row.get("acaocategoria", "") or "criar categoria")
        if action and action != "criarcategoria":
            continue

        category_name = (row.get("categoriaimportacao") or row.get("categoryname") or "").strip()
        if not category_name:
            continue

        normalized_name = normalize_label(category_name)
        if normalized_name in existing_by_name:
            continue

        report_group = (row.get("gruposugerido") or row.get("reportgroup") or "").strip() or None
        report_subgroup = (row.get("subgruposugerido") or row.get("reportsubgroup") or "").strip() or None
        entry_kind = _entry_kind_from_support_value(
            row.get("entrytypeimportacao") or row.get("entrytype")
        )

        category = Category(
            company_id=company_id,
            code=None,
            name=category_name,
            entry_kind=entry_kind,
            report_group=report_group,
            report_subgroup=report_subgroup,
            is_financial_expense=normalize_label(report_group or "") == "despesasfinanceiras",
            is_active=True,
        )
        db.add(category)
        db.flush()
        existing_by_name[normalized_name] = category
        created += 1

    return created


def _ensure_historical_support_suppliers(db: Session, company_id: str, content: bytes) -> int:
    rows = _read_historical_support_sheet(content, sheet_name="FornecedoresCriar")
    if not rows:
        return 0

    existing_by_name = {
        normalize_label(supplier.name): supplier
        for supplier in db.scalars(select(Supplier).where(Supplier.company_id == company_id))
    }
    created = 0

    for row in rows:
        action = normalize_label(row.get("acaofornecedor", "") or "criar fornecedor")
        if action and action != "criarfornecedor":
            continue

        supplier_name = (row.get("suppliername") or row.get("name") or "").strip()
        if not supplier_name:
            continue

        normalized_name = normalize_label(supplier_name)
        if normalized_name in existing_by_name:
            continue

        document_number = (row.get("supplierdocumentnumber") or row.get("documentnumber") or "").strip() or None
        supplier = Supplier(
            company_id=company_id,
            name=supplier_name,
            document_number=document_number,
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        existing_by_name[normalized_name] = supplier
        created += 1

    return created


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
    if existing:
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


def import_linx_sales(db: Session, company: Company, filename: str, content: bytes) -> ImportResult:
    batch, reused = _create_batch(db, company.id, "linx_sales", filename, content)
    if reused:
        return ImportResult(batch=batch, message="Arquivo de faturamento ja importado anteriormente.")

    rows: list[ParsedSalesRow] = parse_sales_rows(content)
    snapshot_dates = sorted({row.snapshot_date for row in rows})
    overwritten_days = 0
    if snapshot_dates:
        existing_for_days = db.scalar(
            select(func.count())
            .select_from(SalesSnapshot)
            .where(
                SalesSnapshot.company_id == company.id,
                SalesSnapshot.snapshot_date.in_(snapshot_dates),
            )
        ) or 0
        if existing_for_days:
            overwritten_days = len(
                {
                    item
                    for item in db.scalars(
                        select(SalesSnapshot.snapshot_date).where(
                            SalesSnapshot.company_id == company.id,
                            SalesSnapshot.snapshot_date.in_(snapshot_dates),
                        )
                    )
                }
            )
            db.execute(
                delete(SalesSnapshot).where(
                    SalesSnapshot.company_id == company.id,
                    SalesSnapshot.snapshot_date.in_(snapshot_dates),
                )
            )

    for row in rows:
        db.add(
            SalesSnapshot(
                company_id=company.id,
                source_batch_id=batch.id,
                snapshot_date=row.snapshot_date,
                gross_revenue=row.gross_revenue,
                cash_revenue=row.cash_revenue,
                check_sight_revenue=row.check_sight_revenue,
                check_term_revenue=row.check_term_revenue,
                inhouse_credit_revenue=row.inhouse_credit_revenue,
                card_revenue=row.card_revenue,
                convenio_revenue=row.convenio_revenue,
                pix_revenue=row.pix_revenue,
                financing_revenue=row.financing_revenue,
                markup=row.markup,
                discount_or_surcharge=row.discount_or_surcharge,
            )
        )
    cleanup_open_linx_sales_entries(db, company.id)
    deactivate_electronic_receivables_account(db, company.id)
    batch.records_total = len(rows)
    batch.records_valid = len(rows)
    batch.records_invalid = 0
    batch.status = "processed"
    if overwritten_days:
        batch.error_summary = (
            f"{overwritten_days} dia(s) do faturamento foram substituidos pelos dados do arquivo novo."
        )
    db.commit()
    db.refresh(batch)
    if overwritten_days:
        message = (
            "Faturamento Linx importado com sucesso. "
            f"{overwritten_days} dia(s) existentes foram sobrescritos."
        )
    else:
        message = "Faturamento Linx importado com sucesso."
    return ImportResult(batch=batch, message=message)


def import_linx_receivables(
    db: Session,
    company: Company,
    filename: str,
    content: bytes,
) -> ImportResult:
    extracted_filename, extracted_content = prepare_linx_receivables_payload(filename, content)
    batch, reused = _create_batch(db, company.id, "linx_receivables", extracted_filename, extracted_content)
    if reused:
        return ImportResult(batch=batch, message="Arquivo de faturas a receber ja importado anteriormente.")

    rows: list[ParsedReceivableRow] = parse_receivable_rows(extracted_content)
    existing_count = db.scalar(
        select(func.count()).select_from(ReceivableTitle).where(ReceivableTitle.company_id == company.id)
    ) or 0
    db.execute(delete(ReceivableTitle).where(ReceivableTitle.company_id == company.id))

    for row in rows:
        db.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=batch.id,
                issue_date=row.issue_date,
                due_date=row.due_date,
                invoice_number=row.invoice_number,
                company_code=row.company_code,
                installment_label=row.installment_label,
                original_amount=row.original_amount,
                amount_with_interest=row.amount_with_interest,
                customer_name=row.customer_name,
                document_reference=row.document_reference,
                status=row.status,
                seller_name=row.seller_name,
            )
        )
    batch.records_total = len(rows)
    batch.records_valid = len(rows)
    batch.records_invalid = 0
    batch.status = "processed"
    if existing_count:
        batch.error_summary = (
            f"{existing_count} fatura(s) antigas da cobranca foram substituidas pela carga nova."
        )
    db.commit()
    db.refresh(batch)
    if existing_count:
        return ImportResult(
            batch=batch,
            message=(
                "Faturas a receber importadas com sucesso. "
                f"{existing_count} registro(s) antigos de cobranca foram sobrescritos."
            ),
        )
    return ImportResult(batch=batch, message="Faturas a receber importadas com sucesso.")


def import_ofx(
    db: Session,
    company: Company,
    account_id: str,
    filename: str,
    content: bytes,
) -> ImportResult:
    account = db.get(Account, account_id)
    if not account or account.company_id != company.id:
        raise ValueError("Conta financeira nao encontrada para a importacao OFX")
    if not account.import_ofx_enabled:
        raise ValueError("A importacao OFX nao esta habilitada para esta conta")

    batch, reused = _create_batch(db, company.id, f"ofx:{account_id}", filename, content)
    if reused:
        return ImportResult(batch=batch, message="Arquivo OFX ja importado anteriormente para esta conta.")

    rows: list[ParsedOfxTransaction] = parse_ofx_transactions(content)
    duplicates = 0
    inserted = 0
    for row in rows:
        exists = db.scalar(
            select(BankTransaction).where(
                BankTransaction.account_id == account_id,
                BankTransaction.fit_id == row.fit_id,
            )
        )
        if exists:
            duplicates += 1
            continue
        db.add(
            BankTransaction(
                company_id=company.id,
                source_batch_id=batch.id,
                account_id=account_id,
                bank_name=row.bank_name,
                bank_code=row.bank_code,
                posted_at=row.posted_at,
                trn_type=row.trn_type,
                amount=row.amount,
                fit_id=row.fit_id,
                check_number=row.check_number,
                reference_number=row.reference_number,
                memo=row.memo,
                name=row.name,
                raw_payload=row.raw_payload,
            )
        )
        inserted += 1
    batch.records_total = len(rows)
    batch.records_valid = inserted
    batch.records_invalid = duplicates
    batch.status = "processed"
    if duplicates:
        batch.error_summary = f"{duplicates} lancamentos ja existiam para esta conta."
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message="OFX importado com sucesso.")


def import_historical_cashbook(
    db: Session,
    company: Company,
    filename: str,
    content: bytes,
) -> ImportResult:
    batch, reused = _create_batch(db, company.id, HISTORICAL_CASHBOOK_SOURCE, filename, content)
    if reused:
        return ImportResult(batch=batch, message="Arquivo do livro caixa ja importado anteriormente.")

    rows = parse_historical_cashbook_rows(content)
    historical_account = _ensure_historical_account(db, company.id)
    ensure_category_catalog(db, company.id)
    _ensure_historical_support_categories(db, company.id, content)
    _ensure_historical_support_suppliers(db, company.id, content)
    (
        categories_by_code,
        categories_by_name,
        suppliers_by_name,
        suppliers_by_document,
        collections_by_name,
    ) = _build_historical_structured_lookups(db, company.id)

    existing_refs = {
        row[0]
        for row in db.execute(
            select(FinancialEntry.source_reference).where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.external_source == HISTORICAL_CASHBOOK_SOURCE,
                FinancialEntry.source_reference.is_not(None),
            )
        )
    }

    inserted = 0
    skipped_duplicates = 0

    for index, row in enumerate(rows, start=1):
        if row.format_version == "structured":
            category = _resolve_or_create_structured_category(
                db,
                company.id,
                row,
                categories_by_code=categories_by_code,
                categories_by_name=categories_by_name,
            )
            interest_category = _resolve_structured_interest_category(
                row,
                categories_by_code=categories_by_code,
                categories_by_name=categories_by_name,
            )
            supplier = _resolve_or_create_structured_supplier(
                db,
                company.id,
                row,
                suppliers_by_name=suppliers_by_name,
                suppliers_by_document=suppliers_by_document,
            )
            collection = _resolve_structured_collection(
                row,
                collections_by_name=collections_by_name,
            )
            (
                principal_amount,
                interest_amount,
                discount_amount,
                penalty_amount,
                total_amount,
                paid_amount,
                expected_amount,
            ) = _resolve_structured_amounts(row)
            issue_date, competence_date, due_date = _resolve_structured_dates(row)
            status = _resolve_structured_status(
                row,
                total_amount=total_amount,
                paid_amount=row.paid_amount,
            )
            if status == "settled" and row.paid_amount is None:
                paid_amount = total_amount
            _validate_structured_status_amounts(
                row,
                status=status,
                total_amount=total_amount,
                paid_amount=paid_amount,
            )
            entry_type = _resolve_structured_entry_type(row, category)
            title = _truncate((row.title or "").strip(), 160)
            if not title:
                raise ValueError(
                    f"Aba '{row.sheet_name}', linha {row.sheet_row_number}: title e obrigatorio."
                )
            source_reference = row.source_reference or _structured_historical_source_reference(
                due_date=due_date,
                issue_date=issue_date,
                title=title,
                document_number=row.document_number,
                category_code=row.category_code,
                category_name=row.category_name,
                supplier_name=row.supplier_name,
                collection_name=row.collection_name,
                principal_amount=principal_amount,
                interest_amount=interest_amount,
                discount_amount=discount_amount,
                penalty_amount=penalty_amount,
                total_amount=total_amount,
            )
            if source_reference in existing_refs:
                skipped_duplicates += 1
                continue

            db.add(
                FinancialEntry(
                    company_id=company.id,
                    account_id=historical_account.id,
                    category_id=category.id,
                    interest_category_id=interest_category.id if interest_category else None,
                    supplier_id=supplier.id if supplier else None,
                    collection_id=collection.id if collection else None,
                    entry_type=entry_type,
                    status=status,
                    title=title,
                    description=_truncate((row.description or "").strip(), 2000) or None,
                    notes=_truncate((row.notes or "").strip(), 2000) or None,
                    counterparty_name=_truncate((row.counterparty_name or "").strip(), 180) or None,
                    document_number=_truncate((row.document_number or "").strip(), 80) or None,
                    issue_date=issue_date,
                    competence_date=competence_date,
                    due_date=due_date,
                    settled_at=_historical_settled_datetime(
                        row.settled_at if status != "settled" else row.settled_at or due_date
                    ),
                    principal_amount=principal_amount,
                    interest_amount=interest_amount,
                    discount_amount=discount_amount,
                    penalty_amount=penalty_amount,
                    total_amount=total_amount,
                    paid_amount=paid_amount,
                    expected_amount=expected_amount,
                    external_source=HISTORICAL_CASHBOOK_SOURCE,
                    source_system=HISTORICAL_CASHBOOK_SOURCE,
                    source_reference=source_reference,
                )
            )
        else:
            source_reference = _historical_source_reference(
                row_date=row.due_date.isoformat() if row.due_date else "",
                source_account=row.source_account or "",
                launch_number=row.launch_number,
                document_number=row.document_number,
                reference=row.reference,
                history=row.history or "",
                debit_amount=row.debit_amount or Decimal("0.00"),
                credit_amount=row.credit_amount or Decimal("0.00"),
            )
            if source_reference in existing_refs:
                skipped_duplicates += 1
                continue

            inflow = (row.debit_amount or Decimal("0.00")) > 0 and (row.credit_amount or Decimal("0.00")) <= 0
            outflow = (row.credit_amount or Decimal("0.00")) > 0 and (row.debit_amount or Decimal("0.00")) <= 0
            if not inflow and not outflow:
                if (row.debit_amount or Decimal("0.00")) >= (row.credit_amount or Decimal("0.00")) and (row.debit_amount or Decimal("0.00")) > 0:
                    inflow = True
                elif (row.credit_amount or Decimal("0.00")) > 0:
                    outflow = True
                else:
                    skipped_duplicates += 1
                    continue

            entry_type, _ = _classify_historical_cashbook_row(row.history or "", inflow)
            amount = row.debit_amount if inflow else row.credit_amount
            category_name = match_historical_category_name(
                history=row.history or "",
                entry_type=entry_type,
                inflow=inflow,
            )
            category = catalog[category_name]
            title = _truncate(row.history or "", 160)
            description = _truncate(
                (
                    f"Livro caixa {row.sheet_name} | Conta origem: {row.source_account or '-'} | "
                    f"Lanc: {row.launch_number or '-'} | Doc: {row.document_number or '-'} | "
                    f"Ref: {row.reference or '-'} | Historico original: {row.history or '-'}"
                ),
                2000,
            )

            db.add(
                FinancialEntry(
                    company_id=company.id,
                    account_id=historical_account.id,
                    category_id=category.id,
                    interest_category_id=None,
                    entry_type=entry_type,
                    status="settled",
                    title=title,
                    description=description,
                    counterparty_name=None,
                    issue_date=row.issue_date,
                    competence_date=row.competence_date,
                    due_date=row.due_date,
                    settled_at=_historical_settled_datetime(row.settled_at),
                    principal_amount=amount,
                    interest_amount=Decimal("0.00"),
                    total_amount=amount,
                    paid_amount=amount,
                    external_source=HISTORICAL_CASHBOOK_SOURCE,
                    source_system=HISTORICAL_CASHBOOK_SOURCE,
                    source_reference=source_reference,
                )
            )
        existing_refs.add(source_reference)
        inserted += 1

        if index % 1000 == 0:
            db.flush()

    batch.records_total = len(rows)
    batch.records_valid = inserted
    batch.records_invalid = skipped_duplicates
    batch.status = "processed"
    if skipped_duplicates:
        batch.error_summary = (
            f"{skipped_duplicates} lancamentos historicos duplicados foram ignorados."
        )
    db.commit()
    db.refresh(batch)
    return ImportResult(
        batch=batch,
        message=(
            "Livro caixa historico importado com sucesso. "
            f"{inserted} movimentacoes adicionadas."
        ),
    )


def build_import_summary(db: Session, company: Company) -> ImportSummary:
    batches = list(
        db.scalars(
            select(ImportBatch)
            .where(ImportBatch.company_id == company.id)
            .order_by(ImportBatch.created_at.desc())
            .limit(12)
        )
    )
    sales_count = db.scalar(
        select(func.count()).select_from(SalesSnapshot).where(SalesSnapshot.company_id == company.id)
    )
    receivable_count = db.scalar(
        select(func.count()).select_from(ReceivableTitle).where(ReceivableTitle.company_id == company.id)
    )
    bank_count = db.scalar(
        select(func.count()).select_from(BankTransaction).where(BankTransaction.company_id == company.id)
    )
    historical_cashbook_count = db.scalar(
        select(func.count()).select_from(FinancialEntry).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.external_source == HISTORICAL_CASHBOOK_SOURCE,
        )
    )
    latest_ofx_transaction_date = db.scalar(
        select(func.max(BankTransaction.posted_at))
        .select_from(BankTransaction)
        .join(ImportBatch, ImportBatch.id == BankTransaction.source_batch_id)
        .where(
            BankTransaction.company_id == company.id,
            ImportBatch.company_id == company.id,
            ImportBatch.source_type.like("ofx:%"),
        )
    )
    return ImportSummary(
        import_batches=batches,
        sales_snapshot_count=sales_count or 0,
        receivable_title_count=receivable_count or 0,
        bank_transaction_count=bank_count or 0,
        historical_cashbook_count=historical_cashbook_count or 0,
        latest_ofx_transaction_date=latest_ofx_transaction_date.isoformat() if latest_ofx_transaction_date else None,
    )


def backfill_historical_cashbook_settlements(db: Session, company_id: str) -> int:
    updated = 0
    for entry in db.scalars(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.external_source == HISTORICAL_CASHBOOK_SOURCE,
        )
    ):
        settled_date = entry.competence_date or entry.issue_date or entry.due_date
        settled_at = (
            datetime.combine(settled_date, time.min, tzinfo=timezone.utc)
            if settled_date
            else datetime.now(timezone.utc)
        )
        changed = False
        if entry.status != "settled":
            entry.status = "settled"
            changed = True
        if Decimal(entry.paid_amount or 0) != Decimal(entry.total_amount or 0):
            entry.paid_amount = Decimal(entry.total_amount or 0)
            changed = True
        if entry.settled_at is None:
            entry.settled_at = settled_at
            changed = True
        if not entry.source_system:
            entry.source_system = HISTORICAL_CASHBOOK_SOURCE
            changed = True
        if changed:
            updated += 1
    if updated:
        db.flush()
    return updated

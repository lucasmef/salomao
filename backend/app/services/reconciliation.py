import hashlib
import re
import unicodedata
from datetime import datetime, time, timezone, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.banking import (
    BankTransaction,
    Reconciliation,
    ReconciliationGroup,
    ReconciliationLine,
)
from app.db.models.finance import Account, FinancialEntry
from app.db.models.security import Company, User
from app.schemas.dashboard import DashboardAccountBalance
from app.schemas.financial_entry import FinancialEntryCreate
from app.schemas.reconciliation import (
    ReconciliationAppliedEntry,
    BankTransactionActionCreate,
    BankTransactionWorkItem,
    ReconciliationCreate,
    ReconciliationUndoResponse,
    ReconciliationWorklist,
)
from app.services.audit import write_audit_log
from app.services.cashflow import RECEIVABLES_CONTROL_ACCOUNT_TYPE, _current_balance_for_account
from app.services.finance_ops import apply_settlement_breakdown, create_entry, create_transfer, delete_entry
from app.schemas.transfer import TransferCreate
from app.services.bootstrap import ensure_default_financial_category


TWO_PLACES = Decimal("0.01")


def _money(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES)


def _is_settlement_adjustment_entry(entry: FinancialEntry) -> bool:
    return entry.source_system == "settlement_adjustment" and (entry.source_reference or "").startswith(
        "settlement-adjustment:"
    )


def _has_manual_amount_adjustments(payload: ReconciliationCreate) -> bool:
    return any(
        value is not None
        for value in (
            payload.principal_amount,
            payload.interest_amount,
            payload.discount_amount,
            payload.penalty_amount,
        )
    )


def _apply_manual_reconciliation_adjustments(
    db: Session,
    company: Company,
    entry: FinancialEntry,
    payload: ReconciliationCreate,
) -> None:
    if payload.principal_amount is not None:
        entry.principal_amount = _money(payload.principal_amount)
    if payload.interest_amount is not None:
        entry.interest_amount = _money(payload.interest_amount)
        if entry.interest_amount > Decimal("0.00") and not entry.interest_category_id:
            entry.interest_category_id = ensure_default_financial_category(db, company.id).id
    if payload.discount_amount is not None:
        entry.discount_amount = _money(payload.discount_amount)
    if payload.penalty_amount is not None:
        entry.penalty_amount = _money(payload.penalty_amount)

    recalculated_total = _money(
        Decimal(entry.principal_amount)
        + Decimal(entry.interest_amount)
        + Decimal(entry.penalty_amount)
        - Decimal(entry.discount_amount)
    )
    if recalculated_total <= Decimal("0.00"):
        raise ValueError("O valor total do lancamento deve ser maior que zero")
    if Decimal(entry.paid_amount or 0) > recalculated_total:
        raise ValueError("O valor ja pago do lancamento nao pode ficar maior que o novo total")
    entry.total_amount = recalculated_total


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _build_bank_source_reference(transactions: list[BankTransaction]) -> str:
    payload = "|".join(
        f"{transaction.id}:{transaction.fit_id}:{transaction.posted_at.isoformat()}:{Decimal(transaction.amount):.2f}"
        for transaction in transactions
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]
    return f"bank-batch:{len(transactions)}:{digest}"


def _build_grouped_transaction_title(transactions: list[BankTransaction]) -> str:
    if not transactions:
        return "Lancamento agrupado"

    if len(transactions) == 1:
        transaction = transactions[0]
        return transaction.memo or transaction.name or transaction.fit_id or "Lancamento bancario"

    net_amount = sum(Decimal(transaction.amount) for transaction in transactions)
    is_income = net_amount > 0
    base_title = "Recebimento agrupado" if is_income else "Pagamento agrupado"
    return f"{base_title} ({len(transactions)} movimentos)"


def _build_grouped_transaction_notes(transactions: list[BankTransaction], existing_notes: str | None = None) -> str | None:
    details = []
    for transaction in transactions:
        amount = abs(Decimal(transaction.amount))
        signed_amount = f"- {amount:.2f}" if Decimal(transaction.amount) < 0 else f"{amount:.2f}"
        details.append(
            " | ".join(
                filter(
                    None,
                    [
                        transaction.posted_at.strftime("%d/%m/%Y"),
                        signed_amount,
                        transaction.name or transaction.memo or transaction.fit_id,
                        transaction.memo or transaction.fit_id,
                    ],
                )
            )
        )

    notes_parts = []
    if existing_notes:
        notes_parts.append(existing_notes.strip())
    if details:
        notes_parts.append("Movimentos do extrato:\n" + "\n".join(details))

    joined = "\n\n".join(part for part in notes_parts if part).strip()
    return joined[:4000] if joined else None


def _is_reconciliation_generated_entry(entry: FinancialEntry, match_type: str | None = None) -> bool:
    if _is_settlement_adjustment_entry(entry):
        return True
    if entry.transfer_id or entry.loan_installment_id:
        return False
    if match_type and match_type not in {"action_create_entry", "action_mark_bank_fee"}:
        return False
    return bool(entry.source_system == "ofx" and (entry.source_reference or "").startswith("bank-batch:"))


def _undo_mode_from_entries(applied_entries: list[ReconciliationAppliedEntry]) -> str | None:
    if not applied_entries:
        return None
    deletable = [entry for entry in applied_entries if entry.can_delete_on_unreconcile]
    if not deletable:
        return "reopen"
    if len(deletable) == len(applied_entries):
        return "delete_entry"
    return "mixed"


def _apply_unreconciled_status(entry: FinancialEntry, amount_to_remove: Decimal) -> None:
    new_paid = max(Decimal(entry.paid_amount or 0) - amount_to_remove, Decimal("0.00"))
    entry.paid_amount = new_paid
    if new_paid <= Decimal("0.00"):
        entry.status = "planned"
        entry.settled_at = None
    elif new_paid < Decimal(entry.total_amount):
        entry.status = "partial"
        entry.settled_at = None
    else:
        entry.status = "settled"


def _score_candidate(
    transaction: BankTransaction,
    entry: FinancialEntry,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    tx_amount = abs(Decimal(transaction.amount))
    entry_remaining = max(Decimal(entry.total_amount) - Decimal(entry.paid_amount or 0), Decimal("0.00"))
    amount_diff = abs(tx_amount - entry_remaining)
    if amount_diff == Decimal("0.00"):
        score += 55
        reasons.append("valor exato")
    elif amount_diff <= Decimal("1.00"):
        score += 40
        reasons.append("valor muito proximo")
    elif tx_amount and amount_diff / tx_amount <= Decimal("0.03"):
        score += 20
        reasons.append("valor compativel")
    else:
        score -= 25

    if entry.due_date:
        day_diff = abs((transaction.posted_at - entry.due_date).days)
        if day_diff == 0:
            score += 25
            reasons.append("mesma data")
        elif day_diff <= 2:
            score += 16
            reasons.append("data proxima")
        elif day_diff <= 7:
            score += 8
            reasons.append("janela compativel")
    else:
        score += 1

    if entry.account_id == transaction.account_id:
        score += 12
        reasons.append("mesma conta")
    elif entry.account_id is None:
        score += 4
        reasons.append("sem conta definida")
    else:
        score -= 20

    tx_type = "income" if Decimal(transaction.amount) > 0 else "expense"
    if entry.entry_type == tx_type:
        score += 10
        reasons.append("mesma natureza")
    elif entry.entry_type == "transfer":
        score += 6
        reasons.append("possivel transferencia")
    else:
        score -= 25

    tx_text = _normalize_text(" ".join(filter(None, [transaction.memo, transaction.name])))
    entry_text = _normalize_text(
        " ".join(filter(None, [entry.title, entry.counterparty_name, entry.document_number]))
    )
    if tx_text and entry_text:
        tx_words = set(tx_text.split())
        entry_words = set(entry_text.split())
        common = tx_words & entry_words
        if common:
            score += min(len(common) * 5, 18)
            reasons.append("historico parecido")

    for rule in entry.account and [] or []:
        _ = rule
    return score, reasons


def _transaction_already_reconciled(db: Session, transaction_id: str) -> bool:
    old_count = db.scalar(
        select(func.count()).select_from(Reconciliation).where(Reconciliation.bank_transaction_id == transaction_id)
    ) or 0
    new_count = db.scalar(
        select(func.count()).select_from(ReconciliationLine).where(ReconciliationLine.bank_transaction_id == transaction_id)
    ) or 0
    return old_count > 0 or new_count > 0


def build_reconciliation_worklist(
    db: Session,
    company: Company,
    page: int = 1,
    limit: int = 25,
    account_id: str | None = None,
    search: str | None = None,
    date_from=None,
    date_to=None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
) -> ReconciliationWorklist:
    base_conditions = [BankTransaction.company_id == company.id]
    if account_id:
        base_conditions.append(BankTransaction.account_id == account_id)
    if date_from:
        base_conditions.append(BankTransaction.posted_at >= date_from)
    if date_to:
        base_conditions.append(BankTransaction.posted_at <= date_to)
    if min_amount is not None:
        base_conditions.append(func.abs(BankTransaction.amount) >= min_amount)
    if max_amount is not None:
        base_conditions.append(func.abs(BankTransaction.amount) <= max_amount)
    if search:
        like_value = f"%{search}%"
        base_conditions.append(
            or_(
                BankTransaction.memo.ilike(like_value),
                BankTransaction.name.ilike(like_value),
                BankTransaction.fit_id.ilike(like_value),
                BankTransaction.reference_number.ilike(like_value),
                BankTransaction.check_number.ilike(like_value),
            )
        )

    unreconciled_conditions = [
        *base_conditions,
        ~BankTransaction.id.in_(select(ReconciliationLine.bank_transaction_id)),
        ~BankTransaction.id.in_(select(Reconciliation.bank_transaction_id)),
    ]

    unreconciled_count = db.scalar(
        select(func.count())
        .select_from(BankTransaction)
        .where(*unreconciled_conditions)
    ) or 0
    overall_unreconciled_count = db.scalar(
        select(func.count())
        .select_from(BankTransaction)
        .where(
            BankTransaction.company_id == company.id,
            ~BankTransaction.id.in_(select(ReconciliationLine.bank_transaction_id)),
            ~BankTransaction.id.in_(select(Reconciliation.bank_transaction_id)),
        )
    ) or 0

    total_count = db.scalar(select(func.count()).select_from(BankTransaction).where(*base_conditions)) or 0
    matched_count = max(total_count - unreconciled_count, 0)

    offset = (page - 1) * limit

    transactions = list(
        db.scalars(
            select(BankTransaction)
            .where(*base_conditions)
            .order_by(BankTransaction.posted_at.desc(), BankTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )

    transaction_ids = [transaction.id for transaction in transactions]
    reconciliation_lines = list(
        db.scalars(
            select(ReconciliationLine).where(ReconciliationLine.bank_transaction_id.in_(transaction_ids))
        )
    ) if transaction_ids else []
    legacy_reconciliations = list(
        db.scalars(
            select(Reconciliation).where(Reconciliation.bank_transaction_id.in_(transaction_ids))
        )
    ) if transaction_ids else []

    applied_entry_ids = {
        line.financial_entry_id for line in reconciliation_lines
    } | {
        item.financial_entry_id for item in legacy_reconciliations
    }
    applied_entry_map = {
        entry.id: entry
        for entry in db.scalars(
            select(FinancialEntry)
            .options(joinedload(FinancialEntry.account))
            .where(FinancialEntry.id.in_(applied_entry_ids))
        )
    } if applied_entry_ids else {}

    line_map: dict[str, list[ReconciliationLine]] = {}
    for line in reconciliation_lines:
        line_map.setdefault(line.bank_transaction_id, []).append(line)

    legacy_map: dict[str, list[Reconciliation]] = {}
    for reconciliation in legacy_reconciliations:
        legacy_map.setdefault(reconciliation.bank_transaction_id, []).append(reconciliation)

    items: list[BankTransactionWorkItem] = []
    for transaction in transactions:
        applied_entries: list[ReconciliationAppliedEntry] = []
        transaction_lines = line_map.get(transaction.id, [])
        transaction_legacy = legacy_map.get(transaction.id, [])
        if transaction_lines:
            for line in transaction_lines:
                entry = applied_entry_map.get(line.financial_entry_id)
                if not entry:
                    continue
                applied_entries.append(
                    ReconciliationAppliedEntry(
                        financial_entry_id=entry.id,
                        title=entry.title,
                        amount_applied=line.amount_applied,
                        status=entry.status,
                        can_delete_on_unreconcile=_is_reconciliation_generated_entry(entry, line.reconciliation_group.match_type if line.reconciliation_group else None),
                    )
                )
        elif transaction_legacy:
            for reconciliation in transaction_legacy:
                entry = applied_entry_map.get(reconciliation.financial_entry_id)
                if not entry:
                    continue
                applied_entries.append(
                    ReconciliationAppliedEntry(
                        financial_entry_id=entry.id,
                        title=entry.title,
                        amount_applied=abs(Decimal(transaction.amount)),
                        status=entry.status,
                        can_delete_on_unreconcile=False,
                    )
                )

        is_reconciled = bool(applied_entries)
        items.append(
            BankTransactionWorkItem(
                bank_transaction_id=transaction.id,
                account_id=transaction.account_id,
                posted_at=transaction.posted_at,
                amount=transaction.amount,
                trn_type=transaction.trn_type,
                fit_id=transaction.fit_id,
                memo=transaction.memo,
                name=transaction.name,
                account_name=transaction.account.name if transaction.account else None,
                reconciliation_status="matched" if is_reconciled else "pending",
                undo_mode=_undo_mode_from_entries(applied_entries) if is_reconciled else None,
                applied_entries=applied_entries,
                candidates=[],
            )
        )

    balance_accounts = sorted(
        [
            account
            for account in db.scalars(
                select(Account).where(
                    Account.company_id == company.id,
                    Account.is_active.is_(True),
                )
            )
            if account.account_type != RECEIVABLES_CONTROL_ACCOUNT_TYPE and not account.exclude_from_balance
        ],
        key=lambda item: (item.name or "").lower(),
    )
    total_account_balance = Decimal("0.00")
    account_balances: list[DashboardAccountBalance] = []
    for account in balance_accounts:
        balance = _current_balance_for_account(db, company.id, account)
        total_account_balance += balance
        account_balances.append(
            DashboardAccountBalance(
                account_id=account.id,
                account_name=account.name,
                account_type=account.account_type,
                current_balance=balance,
            )
        )

    return ReconciliationWorklist(
        unreconciled_count=unreconciled_count,
        overall_unreconciled_count=overall_unreconciled_count,
        matched_count=matched_count,
        total=total_count,
        page=page,
        page_size=limit,
        total_account_balance=total_account_balance,
        account_balances=account_balances,
        items=items,
    )


def create_reconciliation(
    db: Session,
    company: Company,
    payload: ReconciliationCreate,
    actor_user: User | None = None,
) -> ReconciliationGroup:
    transactions = [db.get(BankTransaction, item_id) for item_id in payload.bank_transaction_ids]
    entries = [db.get(FinancialEntry, item_id) for item_id in payload.financial_entry_ids]

    if any(item is None or item.company_id != company.id for item in transactions):
        raise ValueError("Movimento bancario nao encontrado")
    if any(item is None or item.company_id != company.id for item in entries):
        raise ValueError("Lancamento financeiro nao encontrado")
    if any(item is not None and item.due_date is None for item in entries):
        raise ValueError("Data de vencimento obrigatoria para conciliar e baixar o lancamento")
    if any(_transaction_already_reconciled(db, transaction.id) for transaction in transactions if transaction):
        raise ValueError("Um dos movimentos bancarios ja foi conciliado")
    transaction_signs = {Decimal(item.amount) > 0 for item in transactions if item and Decimal(item.amount) != Decimal("0.00")}
    is_mixed_action_create_entry = (
        payload.match_type == "action_create_entry"
        and len(entries) == 1
        and len(transactions) > 1
        and len(transaction_signs) > 1
    )
    total_transactions = sum(abs(Decimal(item.amount)) for item in transactions if item)
    if total_transactions <= Decimal("0.00"):
        raise ValueError("Os movimentos selecionados nao possuem valor valido para conciliacao")

    single_entry_adjustment_lines: list[tuple[FinancialEntry, Decimal]] = []
    single_entry_posted_at: date | None = None
    total_remaining = sum(
        max(Decimal(item.total_amount) - Decimal(item.paid_amount or 0), Decimal("0.00"))
        for item in entries
        if item
    )

    if len(transactions) == 1 and len(entries) == 1:
        transaction = transactions[0]
        entry = entries[0]
        single_entry_posted_at = transaction.posted_at
        settlement_datetime = datetime.combine(transaction.posted_at, time.min, tzinfo=timezone.utc)
        cash_total, generated_adjustments = apply_settlement_breakdown(
            db,
            company,
            entry,
            principal_amount=payload.principal_amount,
            interest_amount=payload.interest_amount,
            discount_amount=payload.discount_amount,
            penalty_amount=payload.penalty_amount,
            settled_at=settlement_datetime,
        )
        amount_difference = abs(total_transactions - cash_total)
        if amount_difference > TWO_PLACES:
            raise ValueError("Os valores nao conferem. Ajuste principal, juros, multa ou desconto antes de conciliar.")
        total_remaining = cash_total
        single_entry_adjustment_lines = [(entry, Decimal(entry.total_amount))] + generated_adjustments
    else:
        if _has_manual_amount_adjustments(payload):
            raise ValueError("Ajustes de principal, juros, multa ou desconto exigem 1 movimento e 1 lancamento")
        if total_remaining <= 0:
            raise ValueError("Os lancamentos selecionados nao possuem saldo aberto")
        comparison_total = total_transactions
        if is_mixed_action_create_entry:
            comparison_total = abs(sum(Decimal(item.amount) for item in transactions if item))
        amount_difference = abs(comparison_total - total_remaining)
        if amount_difference > TWO_PLACES:
            raise ValueError("Conciliacao multipla exige que a soma do extrato seja igual a soma dos lancamentos.")

    confidence_base = total_transactions
    if is_mixed_action_create_entry:
        confidence_base = abs(sum(Decimal(item.amount) for item in transactions if item))
    confidence_score = min(float((min(confidence_base, total_remaining) / max(confidence_base, Decimal("0.01"))) * 100), 100.0)

    group = ReconciliationGroup(
        company_id=company.id,
        match_type=payload.match_type,
        confidence_score=round(confidence_score, 2),
        notes=payload.notes,
    )
    db.add(group)
    db.flush()

    transaction_remaining: dict[str, Decimal] = {
        transaction.id: abs(Decimal(transaction.amount))
        for transaction in transactions
        if transaction is not None
    }
    entry_posted_dates: dict[str, list] = {entry.id: [] for entry in entries if entry is not None}

    if single_entry_adjustment_lines:
        transaction = transactions[0]
        transaction_remaining[transaction.id] = Decimal("0.00")
        for line_entry, applied_amount in single_entry_adjustment_lines:
            if applied_amount == Decimal("0.00"):
                continue
            db.add(
                ReconciliationLine(
                    company_id=company.id,
                    reconciliation_group_id=group.id,
                    bank_transaction_id=transaction.id,
                    financial_entry_id=line_entry.id,
                    amount_applied=applied_amount,
                )
            )
            if not line_entry.account_id and transaction.account_id:
                line_entry.account_id = transaction.account_id
            if _is_settlement_adjustment_entry(line_entry):
                continue
            line_entry.paid_amount = Decimal(line_entry.total_amount)
            line_entry.status = "settled"
            line_entry.settled_at = datetime.combine(transaction.posted_at, time.min, tzinfo=timezone.utc)
    elif is_mixed_action_create_entry:
        entry = entries[0]
        settled_dates: list[date] = []
        for transaction in transactions:
            signed_amount = Decimal(transaction.amount)
            if signed_amount == Decimal("0.00"):
                transaction_remaining[transaction.id] = Decimal("0.00")
                continue

            db.add(
                ReconciliationLine(
                    company_id=company.id,
                    reconciliation_group_id=group.id,
                    bank_transaction_id=transaction.id,
                    financial_entry_id=entry.id,
                    amount_applied=signed_amount,
                )
            )
            transaction_remaining[transaction.id] = Decimal("0.00")
            settled_dates.append(transaction.posted_at)

        entry.paid_amount = Decimal(entry.total_amount)
        entry.status = "settled"
        if settled_dates:
            entry.settled_at = datetime.combine(max(settled_dates), time.min, tzinfo=timezone.utc)
        if not entry.account_id:
            matched_account_ids = [transaction.account_id for transaction in transactions if transaction.account_id]
            if matched_account_ids:
                entry.account_id = matched_account_ids[0]
    else:
        for entry in entries:
            open_amount = max(Decimal(entry.total_amount) - Decimal(entry.paid_amount or 0), Decimal("0.00"))
            if open_amount <= 0:
                continue

            for transaction in transactions:
                if open_amount <= 0:
                    break
                remaining_tx = transaction_remaining.get(transaction.id, Decimal("0.00"))
                if remaining_tx <= 0:
                    continue

                amount_applied = min(open_amount, remaining_tx)
                if amount_applied <= 0:
                    continue

                db.add(
                    ReconciliationLine(
                        company_id=company.id,
                        reconciliation_group_id=group.id,
                        bank_transaction_id=transaction.id,
                        financial_entry_id=entry.id,
                        amount_applied=amount_applied,
                    )
                )
                transaction_remaining[transaction.id] = remaining_tx - amount_applied
                open_amount -= amount_applied
                entry_posted_dates[entry.id].append(transaction.posted_at)

            if open_amount > TWO_PLACES:
                raise ValueError("Cada lancamento precisa ser quitado integralmente na conciliacao.")

            applied_total = max(Decimal(entry.total_amount) - Decimal(entry.paid_amount or 0), Decimal("0.00"))
            if applied_total <= 0:
                continue

            entry.paid_amount = Decimal(entry.total_amount)
            entry.status = "settled"
            if entry_posted_dates[entry.id]:
                entry.settled_at = datetime.combine(max(entry_posted_dates[entry.id]), time.min, tzinfo=timezone.utc)
            if not entry.account_id:
                matched_account_ids = [transaction.account_id for transaction in transactions if transaction.account_id]
                if matched_account_ids:
                    entry.account_id = matched_account_ids[0]

    if any(abs(remaining) > TWO_PLACES for remaining in transaction_remaining.values()):
        raise ValueError("A conciliacao so pode ser concluida quando o valor do extrato fechar exatamente com os lancamentos.")

    if actor_user:
        write_audit_log(
            db,
            action="create_reconciliation_group",
            entity_name="reconciliation_group",
            entity_id=group.id,
            company_id=company.id,
            actor_user=actor_user,
            after_state={
                "bank_transaction_ids": payload.bank_transaction_ids,
                "financial_entry_ids": payload.financial_entry_ids,
            },
        )
    db.flush()
    return group


def _create_transfer_reconciliation(
    db: Session,
    company: Company,
    bank_transactions: list[BankTransaction],
    financial_entry_id: str,
    notes: str | None,
    actor_user: User | None = None,
) -> ReconciliationGroup:
    if not bank_transactions:
        raise ValueError("Nenhum movimento bancario informado para a transferencia")

    group = ReconciliationGroup(
        company_id=company.id,
        match_type="action_transfer",
        confidence_score=100.0,
        notes=notes,
    )
    db.add(group)
    db.flush()

    for bank_transaction in bank_transactions:
        db.add(
            ReconciliationLine(
                company_id=company.id,
                reconciliation_group_id=group.id,
                bank_transaction_id=bank_transaction.id,
                financial_entry_id=financial_entry_id,
                amount_applied=abs(Decimal(bank_transaction.amount)),
            )
        )

    if actor_user:
        write_audit_log(
            db,
            action="create_reconciliation_group",
            entity_name="reconciliation_group",
            entity_id=group.id,
            company_id=company.id,
            actor_user=actor_user,
            after_state={
                "bank_transaction_ids": [bank_transaction.id for bank_transaction in bank_transactions],
                "financial_entry_ids": [financial_entry_id],
                "match_type": "action_transfer",
            },
        )

    db.flush()
    return group


def create_entry_from_bank_transaction(
    db: Session,
    company: Company,
    payload: BankTransactionActionCreate,
    actor_user: User,
):
    transactions = [db.get(BankTransaction, item_id) for item_id in payload.bank_transaction_ids]
    if any(not transaction or transaction.company_id != company.id for transaction in transactions):
        raise ValueError("Movimento bancario nao encontrado")
    valid_transactions = [transaction for transaction in transactions if transaction is not None]
    if any(_transaction_already_reconciled(db, transaction.id) for transaction in valid_transactions):
        raise ValueError("Um dos movimentos bancarios selecionados ja foi conciliado")

    transactions = sorted(valid_transactions, key=lambda item: (item.posted_at, item.created_at))
    first_transaction = transactions[0]
    net_amount = sum(Decimal(transaction.amount) for transaction in transactions)
    total_amount = abs(net_amount)

    if payload.action_type == "mark_transfer":
        if not payload.destination_account_id:
            raise ValueError("Conta de destino obrigatoria para transferencias")
        if total_amount == 0:
            raise ValueError("Os movimentos selecionados resultam em valor liquido zero e nao podem gerar transferencia")
        account_ids = {transaction.account_id for transaction in transactions}
        if len(account_ids) != 1:
            raise ValueError("Selecione apenas movimentos da mesma conta para lancar uma transferencia")
        amount_signs = {Decimal(transaction.amount) > 0 for transaction in transactions}
        if len(amount_signs) != 1:
            raise ValueError("Selecione movimentos apenas de entrada ou apenas de saida para criar a transferencia")

        source_account_id = first_transaction.account_id
        destination_account_id = payload.destination_account_id
        if net_amount > 0:
            source_account_id, destination_account_id = destination_account_id, source_account_id
        transfer = create_transfer(
            db,
            company,
            TransferCreate(
                source_account_id=source_account_id,
                destination_account_id=destination_account_id,
                transfer_date=transactions[-1].posted_at,
                amount=total_amount,
                status="settled",
                description=(payload.title or _build_grouped_transaction_title(transactions))[:160],
                notes=_build_grouped_transaction_notes(transactions, payload.notes),
            ),
            actor_user,
        )
        transfer_entry_id = transfer.source_entry_id
        if net_amount > 0:
            transfer_entry_id = transfer.destination_entry_id
        transfer_notes = _build_grouped_transaction_notes(transactions, payload.notes)
        reconciliation = _create_transfer_reconciliation(
            db,
            company,
            transactions,
            transfer_entry_id,
            transfer_notes,
            actor_user,
        )
        return {"transfer_id": transfer.id, "reconciliation_id": reconciliation.id}

    if total_amount == 0:
        raise ValueError("Os movimentos selecionados resultam em valor liquido zero e nao podem ser consolidados")

    account_ids = {transaction.account_id for transaction in transactions}
    if len(account_ids) != 1:
        raise ValueError("Selecione apenas movimentos da mesma conta para criar um lancamento consolidado")

    entry_type = "income" if net_amount > 0 else "expense"
    title = payload.title or _build_grouped_transaction_title(transactions)
    descriptions = [value for value in [transaction.memo or transaction.name for transaction in transactions] if value]
    notes = _build_grouped_transaction_notes(transactions, payload.notes)
    entry = create_entry(
        db,
        company,
        FinancialEntryCreate(
            account_id=payload.account_id or first_transaction.account_id,
            category_id=payload.category_id,
            supplier_id=payload.supplier_id,
            entry_type=entry_type,
            status="planned",
            title=title[:160],
            description=" | ".join(descriptions)[:1000] if descriptions else None,
            notes=notes,
            counterparty_name=payload.counterparty_name or first_transaction.name,
            issue_date=transactions[0].posted_at,
            competence_date=transactions[-1].posted_at,
            due_date=transactions[-1].posted_at,
            principal_amount=total_amount,
            total_amount=total_amount,
            source_system="ofx",
            source_reference=_build_bank_source_reference(transactions),
        ),
        actor_user,
    )
    reconciliation = create_reconciliation(
        db,
        company,
            ReconciliationCreate(
                bank_transaction_ids=[transaction.id for transaction in transactions],
                financial_entry_ids=[entry.id],
                match_type=f"action_{payload.action_type}",
                notes=notes,
            ),
            actor_user,
        )
    db.flush()
    return {"financial_entry_id": entry.id, "reconciliation_id": reconciliation.id}


def undo_reconciliation_by_bank_transaction(
    db: Session,
    company: Company,
    bank_transaction_id: str,
    delete_generated_entries: bool,
    actor_user: User,
) -> ReconciliationUndoResponse:
    lines = list(
        db.scalars(
            select(ReconciliationLine)
            .options(joinedload(ReconciliationLine.reconciliation_group))
            .where(
                ReconciliationLine.company_id == company.id,
                ReconciliationLine.bank_transaction_id == bank_transaction_id,
            )
        )
    )

    reopened_entry_ids: list[str] = []
    deleted_entry_ids: list[str] = []
    affected_bank_transaction_ids: list[str] = []

    if lines:
        group_id = lines[0].reconciliation_group_id
        group = db.get(ReconciliationGroup, group_id)
        if not group or group.company_id != company.id:
            raise ValueError("Grupo de conciliacao nao encontrado")

        group_lines = list(
            db.scalars(
                select(ReconciliationLine)
                .options(joinedload(ReconciliationLine.reconciliation_group))
                .where(
                    ReconciliationLine.company_id == company.id,
                    ReconciliationLine.reconciliation_group_id == group_id,
                )
            )
        )
        entry_totals: dict[str, Decimal] = {}
        entry_ids = set()
        affected_bank_transaction_ids = sorted({line.bank_transaction_id for line in group_lines})
        for line in group_lines:
            entry_ids.add(line.financial_entry_id)
            entry_totals[line.financial_entry_id] = entry_totals.get(line.financial_entry_id, Decimal("0.00")) + Decimal(line.amount_applied)

        entries = {
            entry.id: entry
            for entry in db.scalars(
                select(FinancialEntry).where(
                    FinancialEntry.company_id == company.id,
                    FinancialEntry.id.in_(entry_ids),
                )
            )
        }
        generated_entries = [
            entry
            for entry in entries.values()
            if _is_reconciliation_generated_entry(entry, group.match_type)
        ]
        if generated_entries and not delete_generated_entries:
            raise ValueError("Esta desconciliacao vai excluir lancamento(s) criado(s) na conciliacao. Confirme para continuar.")

        for entry_id, amount_to_remove in entry_totals.items():
            entry = entries.get(entry_id)
            if not entry:
                continue
            if _is_reconciliation_generated_entry(entry, group.match_type):
                delete_entry(db, company, entry.id, actor_user, allow_reconciled_generated=True)
                deleted_entry_ids.append(entry.id)
            else:
                _apply_unreconciled_status(entry, amount_to_remove)
                reopened_entry_ids.append(entry.id)

        for line in group_lines:
            db.delete(line)
        if group:
            db.delete(group)

        write_audit_log(
            db,
            action="undo_reconciliation_group",
            entity_name="reconciliation_group",
            entity_id=group_id,
            company_id=company.id,
            actor_user=actor_user,
            after_state={
                "bank_transaction_ids": affected_bank_transaction_ids,
                "reopened_entry_ids": reopened_entry_ids,
                "deleted_entry_ids": deleted_entry_ids,
            },
        )
        db.flush()
        return ReconciliationUndoResponse(
            bank_transaction_ids=affected_bank_transaction_ids,
            reopened_entry_ids=reopened_entry_ids,
            deleted_entry_ids=deleted_entry_ids,
        )

    legacy = db.scalar(
        select(Reconciliation).where(
            Reconciliation.company_id == company.id,
            Reconciliation.bank_transaction_id == bank_transaction_id,
        )
    )
    if not legacy:
        raise ValueError("Conciliacao nao encontrada para este movimento")

    entry = db.get(FinancialEntry, legacy.financial_entry_id)
    transaction = db.get(BankTransaction, legacy.bank_transaction_id)
    if not entry or not transaction:
        raise ValueError("Dados da conciliacao nao encontrados")

    _apply_unreconciled_status(entry, abs(Decimal(transaction.amount)))
    reopened_entry_ids.append(entry.id)
    affected_bank_transaction_ids = [transaction.id]
    db.delete(legacy)
    write_audit_log(
        db,
        action="undo_reconciliation_legacy",
        entity_name="reconciliation",
        entity_id=legacy.id,
        company_id=company.id,
        actor_user=actor_user,
        after_state={
            "bank_transaction_ids": affected_bank_transaction_ids,
            "reopened_entry_ids": reopened_entry_ids,
            "deleted_entry_ids": [],
        },
    )
    db.flush()
    return ReconciliationUndoResponse(
        bank_transaction_ids=affected_bank_transaction_ids,
        reopened_entry_ids=reopened_entry_ids,
        deleted_entry_ids=[],
    )

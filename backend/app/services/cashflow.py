from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from threading import Lock
from time import monotonic

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.db.models.finance import Account, FinancialEntry, Transfer
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxOpenReceivable, ReceivableTitle
from app.db.models.security import Company
from app.schemas.cashflow import AccountBalance, CashflowOverview, CashflowPoint
from app.services.analytics_hybrid import (
    ANALYTICS_CASHFLOW_OVERVIEW,
    clear_live_cache,
    is_full_month_period,
    is_historical_period,
    iter_month_segments,
    read_live_cache,
    read_snapshot_or_rebuild,
    snapshot_params_for_cashflow,
    upsert_monthly_snapshot,
    write_live_cache,
)
from app.services.purchase_planning import PurchasePlanningFilters, build_purchase_planning_cashflow_events

RECEIVABLES_CONTROL_ACCOUNT_TYPE = "receivables_control"
RECEIVABLES_CONTROL_SOURCE = "linx_sales_control"
OPEN_RECEIVABLE_STATUS_KEYWORDS = ("aberto", "a receber", "vencido", "em aberto", "pendente")
PAID_RECEIVABLE_STATUS_KEYWORDS = ("recebido", "pago", "paid", "quitado", "baixado")
CANCELLED_RECEIVABLE_STATUS_KEYWORDS = ("cancelado",)
CURRENT_MONTH_CASHFLOW_CACHE_TTL_SECONDS = 86400
HISTORICAL_MONTH_CASHFLOW_CACHE_TTL_SECONDS = 604800
MAX_CASHFLOW_CACHE_ITEMS = 48


def _should_ignore_account_in_consolidated_balance(account: Account) -> bool:
    return account.account_type == RECEIVABLES_CONTROL_ACCOUNT_TYPE or bool(account.exclude_from_balance)


@dataclass(slots=True)
class CashflowOverviewCacheEntry:
    expires_at: float
    payload: CashflowOverview


_cashflow_overview_cache: dict[tuple[str, str, str, str, bool, bool], CashflowOverviewCacheEntry] = {}
_cashflow_overview_cache_lock = Lock()


@dataclass(slots=True)
class CashflowEvent:
    due_date: date
    crediario_inflow: Decimal = Decimal("0.00")
    card_inflow: Decimal = Decimal("0.00")
    launched_outflow: Decimal = Decimal("0.00")
    planned_purchase_outflow: Decimal = Decimal("0.00")

    @property
    def inflow(self) -> Decimal:
        return self.crediario_inflow + self.card_inflow

    @property
    def outflow(self) -> Decimal:
        return self.launched_outflow + self.planned_purchase_outflow


@dataclass(slots=True)
class CashflowBucket:
    crediario_inflow: Decimal = Decimal("0.00")
    card_inflow: Decimal = Decimal("0.00")
    launched_outflow: Decimal = Decimal("0.00")
    planned_purchase_outflow: Decimal = Decimal("0.00")

    @property
    def inflow(self) -> Decimal:
        return self.crediario_inflow + self.card_inflow

    @property
    def outflow(self) -> Decimal:
        return self.launched_outflow + self.planned_purchase_outflow


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _month_end(value: date) -> date:
    return _add_months(_month_start(value), 1) - timedelta(days=1)


def _receivable_is_open(status: str | None) -> bool:
    normalized = (status or "").strip().lower()
    if any(keyword in normalized for keyword in CANCELLED_RECEIVABLE_STATUS_KEYWORDS):
        return False
    if any(keyword in normalized for keyword in PAID_RECEIVABLE_STATUS_KEYWORDS):
        return False
    if any(keyword in normalized for keyword in OPEN_RECEIVABLE_STATUS_KEYWORDS):
        return True
    return True


def _is_full_month_period(start: date, end: date) -> bool:
    return start == _month_start(start) and end == _month_end(start)


def _cashflow_cache_ttl_seconds(start: date, end: date, *, today: date | None = None) -> int | None:
    if not _is_full_month_period(start, end):
        return None
    reference_day = today or date.today()
    if start == _month_start(reference_day) and end == _month_end(reference_day):
        return CURRENT_MONTH_CASHFLOW_CACHE_TTL_SECONDS
    return HISTORICAL_MONTH_CASHFLOW_CACHE_TTL_SECONDS


def _cashflow_cache_key(
    company_id: str,
    start: date,
    end: date,
    *,
    account_id: str | None,
    include_purchase_planning: bool,
    include_crediario_receivables: bool,
) -> tuple[str, str, str, str, bool, bool]:
    return (
        company_id,
        start.isoformat(),
        end.isoformat(),
        account_id or "",
        include_purchase_planning,
        include_crediario_receivables,
    )


def _prune_cashflow_overview_cache(now: float) -> None:
    expired_keys = [key for key, entry in _cashflow_overview_cache.items() if entry.expires_at <= now]
    for key in expired_keys:
        _cashflow_overview_cache.pop(key, None)
    if len(_cashflow_overview_cache) <= MAX_CASHFLOW_CACHE_ITEMS:
        return
    keys_by_expiry = sorted(_cashflow_overview_cache.items(), key=lambda item: item[1].expires_at)
    for key, _entry in keys_by_expiry[: len(_cashflow_overview_cache) - MAX_CASHFLOW_CACHE_ITEMS]:
        _cashflow_overview_cache.pop(key, None)


def clear_cashflow_overview_cache(company_id: str | None = None) -> None:
    with _cashflow_overview_cache_lock:
        if company_id is None:
            _cashflow_overview_cache.clear()
            clear_live_cache(None, kinds=[ANALYTICS_CASHFLOW_OVERVIEW])
            return
        keys_to_remove = [key for key in _cashflow_overview_cache if key[0] == company_id]
        for key in keys_to_remove:
            _cashflow_overview_cache.pop(key, None)
    clear_live_cache(company_id, kinds=[ANALYTICS_CASHFLOW_OVERVIEW])


def _rebuild_cashflow_aggregates(
    *,
    current_balance: Decimal,
    account_balances: list[AccountBalance],
    daily_projection: list[CashflowPoint],
) -> CashflowOverview:
    ordered_days = sorted(daily_projection, key=lambda item: item.reference)
    recomputed_daily: list[CashflowPoint] = []
    opening_balance = current_balance
    for point in ordered_days:
        inflows = point.crediario_inflows + point.card_inflows
        outflows = point.launched_outflows + point.planned_purchase_outflows
        closing_balance = opening_balance + inflows - outflows
        recomputed_daily.append(
            CashflowPoint(
                reference=point.reference,
                opening_balance=opening_balance,
                crediario_inflows=point.crediario_inflows,
                card_inflows=point.card_inflows,
                launched_outflows=point.launched_outflows,
                planned_purchase_outflows=point.planned_purchase_outflows,
                inflows=inflows,
                outflows=outflows,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance

    monthly_buckets: dict[str, CashflowBucket] = defaultdict(CashflowBucket)
    weekly_projection: list[CashflowPoint] = []
    for point in recomputed_daily:
        month_bucket = monthly_buckets[point.reference[:7]]
        month_bucket.crediario_inflow += point.crediario_inflows
        month_bucket.card_inflow += point.card_inflows
        month_bucket.launched_outflow += point.launched_outflows
        month_bucket.planned_purchase_outflow += point.planned_purchase_outflows

    monthly_projection: list[CashflowPoint] = []
    opening_balance = current_balance
    for reference in sorted(monthly_buckets):
        bucket = monthly_buckets[reference]
        closing_balance = opening_balance + bucket.inflow - bucket.outflow
        monthly_projection.append(
            CashflowPoint(
                reference=reference,
                opening_balance=opening_balance,
                crediario_inflows=bucket.crediario_inflow,
                card_inflows=bucket.card_inflow,
                launched_outflows=bucket.launched_outflow,
                planned_purchase_outflows=bucket.planned_purchase_outflow,
                inflows=bucket.inflow,
                outflows=bucket.outflow,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance

    opening_balance = current_balance
    cursor = 0
    while cursor < len(recomputed_daily):
        window = recomputed_daily[cursor : cursor + 7]
        bucket = CashflowBucket()
        for point in window:
            bucket.crediario_inflow += point.crediario_inflows
            bucket.card_inflow += point.card_inflows
            bucket.launched_outflow += point.launched_outflows
            bucket.planned_purchase_outflow += point.planned_purchase_outflows
        closing_balance = opening_balance + bucket.inflow - bucket.outflow
        weekly_projection.append(
            CashflowPoint(
                reference=f"{window[0].reference} a {window[-1].reference}",
                opening_balance=opening_balance,
                crediario_inflows=bucket.crediario_inflow,
                card_inflows=bucket.card_inflow,
                launched_outflows=bucket.launched_outflow,
                planned_purchase_outflows=bucket.planned_purchase_outflow,
                inflows=bucket.inflow,
                outflows=bucket.outflow,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance
        cursor += 7

    projected_inflows = sum((point.inflows for point in recomputed_daily), Decimal("0.00"))
    projected_outflows = sum((point.outflows for point in recomputed_daily), Decimal("0.00"))
    planned_purchase_outflows = sum((point.planned_purchase_outflows for point in recomputed_daily), Decimal("0.00"))
    projected_ending_balance = recomputed_daily[-1].closing_balance if recomputed_daily else current_balance
    alerts = [f"Saldo projetado negativo em {point.reference}" for point in recomputed_daily if point.closing_balance < 0][:5]
    return CashflowOverview(
        current_balance=current_balance,
        projected_inflows=projected_inflows,
        projected_outflows=projected_outflows,
        planned_purchase_outflows=planned_purchase_outflows,
        projected_ending_balance=projected_ending_balance,
        alerts=alerts,
        account_balances=account_balances,
        daily_projection=recomputed_daily,
        weekly_projection=weekly_projection,
        monthly_projection=monthly_projection,
    )


def _compose_cashflow_segments(parts: list[CashflowOverview]) -> CashflowOverview:
    current_balance = parts[0].current_balance
    account_balances = parts[0].account_balances
    all_daily_points: list[CashflowPoint] = []
    for part in parts:
        all_daily_points.extend(part.daily_projection)
    return _rebuild_cashflow_aggregates(
        current_balance=current_balance,
        account_balances=account_balances,
        daily_projection=all_daily_points,
    )


def _get_cashflow_segment(
    db: Session,
    company: Company,
    *,
    start_date: date,
    end_date: date,
    account_id: str | None,
    include_purchase_planning: bool,
    include_crediario_receivables: bool,
    refresh: bool = False,
) -> CashflowOverview:
    params = snapshot_params_for_cashflow(
        account_id=account_id,
        include_purchase_planning=include_purchase_planning,
        include_crediario_receivables=include_crediario_receivables,
    )
    if not is_full_month_period(start_date, end_date):
        return build_cashflow_overview(
            db,
            company,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id,
            include_purchase_planning=include_purchase_planning,
            include_crediario_receivables=include_crediario_receivables,
    )
    if is_historical_period(start_date, end_date):
        if refresh:
            overview = build_cashflow_overview(
                db,
                company,
                start_date=start_date,
                end_date=end_date,
                account_id=account_id,
                include_purchase_planning=include_purchase_planning,
                include_crediario_receivables=include_crediario_receivables,
            )
            upsert_monthly_snapshot(
                db,
                overview,
                company_id=company.id,
                kind=ANALYTICS_CASHFLOW_OVERVIEW,
                snapshot_month=start_date,
                params=params,
            )
            return overview
        return read_snapshot_or_rebuild(
            db,
            CashflowOverview,
            company=company,
            kind=ANALYTICS_CASHFLOW_OVERVIEW,
            snapshot_month=start_date,
            params=params,
            build_func=lambda: build_cashflow_overview(
                db,
                company,
                start_date=start_date,
                end_date=end_date,
                account_id=account_id,
                include_purchase_planning=include_purchase_planning,
                include_crediario_receivables=include_crediario_receivables,
            ),
        )
    ttl_seconds = _cashflow_cache_ttl_seconds(start_date, end_date)
    if not refresh:
        cached = read_live_cache(
            CashflowOverview,
            kind=ANALYTICS_CASHFLOW_OVERVIEW,
            company_id=company.id,
            start=start_date,
            end=end_date,
            params=params,
        )
        if cached is not None:
            return cached
    overview = build_cashflow_overview(
        db,
        company,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        include_purchase_planning=include_purchase_planning,
        include_crediario_receivables=include_crediario_receivables,
    )
    if ttl_seconds:
        write_live_cache(
            overview,
            kind=ANALYTICS_CASHFLOW_OVERVIEW,
            company_id=company.id,
            start=start_date,
            end=end_date,
            ttl_seconds=ttl_seconds,
            params=params,
        )
    return overview


def _latest_receivables_batch_id(db: Session, company_id: str) -> str | None:
    latest_batch = db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.company_id == company_id,
            ImportBatch.source_type == "linx_receivables",
            ImportBatch.status == "processed",
        )
        .order_by(desc(ImportBatch.created_at))
        .limit(1)
    )
    return latest_batch.id if latest_batch else None


def _load_open_receivable_events(
    db: Session,
    *,
    company_id: str,
    start_date: date,
    end_date: date,
) -> list[CashflowEvent]:
    open_receivables = list(
        db.scalars(
            select(LinxOpenReceivable).where(
                LinxOpenReceivable.company_id == company_id,
                LinxOpenReceivable.due_date.is_not(None),
                LinxOpenReceivable.due_date >= start_date,
                LinxOpenReceivable.due_date <= end_date,
            )
        )
    )
    if open_receivables:
        events: list[CashflowEvent] = []
        for receivable in open_receivables:
            due_date = receivable.due_date.date() if receivable.due_date else None
            if due_date is None:
                continue
            amount = max(
                Decimal(receivable.amount or 0)
                + Decimal(receivable.interest_amount or 0)
                - Decimal(receivable.discount_amount or 0),
                Decimal("0.00"),
            )
            if amount <= Decimal("0.00"):
                continue
            events.append(CashflowEvent(due_date, crediario_inflow=amount))
        return events

    latest_batch_id = _latest_receivables_batch_id(db, company_id)
    if not latest_batch_id:
        return []

    events: list[CashflowEvent] = []
    receivables = db.scalars(
        select(ReceivableTitle).where(
            ReceivableTitle.company_id == company_id,
            ReceivableTitle.source_batch_id == latest_batch_id,
            ReceivableTitle.due_date.is_not(None),
            ReceivableTitle.due_date >= start_date,
            ReceivableTitle.due_date <= end_date,
        )
    )
    for title in receivables:
        if not _receivable_is_open(title.status):
            continue
        amount = title.amount_with_interest or title.original_amount
        events.append(CashflowEvent(title.due_date, crediario_inflow=Decimal(amount)))
    return events


def _current_balance_for_account(db: Session, company_id: str, account: Account) -> Decimal:
    if account.account_type == RECEIVABLES_CONTROL_ACCOUNT_TYPE:
        open_entries = db.scalars(
            select(FinancialEntry).where(
                FinancialEntry.company_id == company_id,
                FinancialEntry.account_id == account.id,
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.source_system == RECEIVABLES_CONTROL_SOURCE,
            )
        )
        balance = Decimal("0.00")
        for entry in open_entries:
            remaining_amount = Decimal(entry.total_amount or 0) - Decimal(entry.paid_amount or 0)
            if remaining_amount <= 0:
                continue
            if entry.entry_type == "income":
                balance += remaining_amount
            elif entry.entry_type == "expense":
                balance -= remaining_amount
        return balance

    realized_entries = db.scalars(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.account_id == account.id,
            FinancialEntry.is_deleted.is_(False),
        )
    )
    total = Decimal(account.opening_balance)
    for entry in realized_entries:
        paid_amount = Decimal(entry.paid_amount or 0)
        realized_amount = paid_amount if paid_amount > Decimal("0.00") else (
            Decimal(entry.total_amount or 0) if entry.status == "settled" else Decimal("0.00")
        )
        if realized_amount <= Decimal("0.00"):
            continue
        if entry.entry_type == "income":
            total += realized_amount
        elif entry.entry_type == "expense":
            total -= realized_amount
        elif entry.entry_type == "transfer" and entry.transfer_id:
            transfer = db.get(Transfer, entry.transfer_id)
            if transfer:
                if transfer.source_account_id == account.id:
                    total -= realized_amount
                elif transfer.destination_account_id == account.id:
                    total += realized_amount
    return total


def _future_events(
    db: Session,
    company: Company,
    start_date: date,
    end_date: date,
    account_id: str | None = None,
    include_purchase_planning: bool = True,
    include_crediario_receivables: bool = True,
    ignored_account_ids: set[str] | None = None,
) -> list[CashflowEvent]:
    events: list[CashflowEvent] = []

    if include_crediario_receivables:
        events.extend(
            _load_open_receivable_events(
                db,
                company_id=company.id,
                start_date=start_date,
                end_date=end_date,
            )
        )

    planned_entries = db.scalars(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.is_deleted.is_(False),
            FinancialEntry.due_date.is_not(None),
            FinancialEntry.due_date >= start_date,
            FinancialEntry.due_date <= end_date,
            FinancialEntry.status != "settled",
            or_(
                FinancialEntry.source_system.is_(None),
                FinancialEntry.source_system != RECEIVABLES_CONTROL_SOURCE,
            ),
        )
    )
    for entry in planned_entries:
        if account_id and entry.account_id != account_id:
            continue
        if ignored_account_ids and entry.account_id and entry.account_id in ignored_account_ids:
            continue
        remaining_amount = Decimal(entry.total_amount) - Decimal(entry.paid_amount or 0)
        if remaining_amount <= 0:
            continue
        if entry.entry_type == "expense":
            events.append(CashflowEvent(entry.due_date, launched_outflow=remaining_amount))
        elif entry.entry_type == "transfer" and entry.transfer_id and entry.account_id:
            transfer = db.get(Transfer, entry.transfer_id)
            if not transfer:
                continue
            if account_id is None:
                source_ignored = bool(
                    ignored_account_ids and transfer.source_account_id in ignored_account_ids
                )
                destination_ignored = bool(
                    ignored_account_ids and transfer.destination_account_id in ignored_account_ids
                )
                # Internal transfers between accounts that are both inside the same
                # consolidated perimeter do not change company cash and should not
                # inflate projected inflows/outflows.
                if source_ignored == destination_ignored:
                    continue
            if transfer.source_account_id == entry.account_id:
                events.append(CashflowEvent(entry.due_date, launched_outflow=remaining_amount))
            elif transfer.destination_account_id == entry.account_id:
                events.append(CashflowEvent(entry.due_date, card_inflow=remaining_amount))

    if include_purchase_planning and not account_id:
        for installment in build_purchase_planning_cashflow_events(db, company, PurchasePlanningFilters()):
            if installment.due_date is None or installment.due_date < start_date or installment.due_date > end_date:
                continue
            projected_amount = Decimal(installment.amount or 0)
            if projected_amount <= 0:
                continue
            events.append(CashflowEvent(installment.due_date, planned_purchase_outflow=projected_amount))

    return events


def build_cashflow_overview(
    db: Session,
    company: Company,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
    include_purchase_planning: bool = True,
    include_crediario_receivables: bool = True,
) -> CashflowOverview:
    today = date.today()
    range_start = start_date or date(today.year, today.month, 1)
    range_end = end_date or (_add_months(date(today.year, today.month, 1), 1) - timedelta(days=1))
    if range_end < range_start:
        range_end = range_start

    accounts = list(
        db.scalars(
            select(Account).where(
                Account.company_id == company.id,
                or_(Account.is_active.is_(True), Account.exclude_from_balance.is_(True)),
            )
        )
    )
    ignored_account_ids: set[str] = set()
    if account_id:
        accounts = [account for account in accounts if account.id == account_id]
    else:
        ignored_account_ids = {
            account.id for account in accounts if _should_ignore_account_in_consolidated_balance(account)
        }

    account_balances: list[AccountBalance] = []
    current_balance = Decimal("0.00")
    for account in accounts:
        balance = _current_balance_for_account(db, company.id, account)
        is_ignored = account.id in ignored_account_ids

        if not is_ignored:
            current_balance += balance

        if is_ignored and not account_id:
            continue

        account_balances.append(
            AccountBalance(
                account_id=account.id,
                account_name=account.name,
                account_type=account.account_type,
                current_balance=balance,
                exclude_from_balance=is_ignored,
            )
        )

    events = _future_events(
        db,
        company,
        range_start,
        range_end,
        account_id=account_id,
        include_purchase_planning=include_purchase_planning,
        include_crediario_receivables=include_crediario_receivables,
        ignored_account_ids=ignored_account_ids,
    )

    planned_purchase_outflows = sum((event.planned_purchase_outflow for event in events), Decimal("0.00"))

    daily_buckets: dict[date, CashflowBucket] = defaultdict(CashflowBucket)
    monthly_buckets: dict[str, CashflowBucket] = defaultdict(CashflowBucket)
    for event in events:
        daily_bucket = daily_buckets[event.due_date]
        daily_bucket.crediario_inflow += event.crediario_inflow
        daily_bucket.card_inflow += event.card_inflow
        daily_bucket.launched_outflow += event.launched_outflow
        daily_bucket.planned_purchase_outflow += event.planned_purchase_outflow
        month_key = _month_key(event.due_date)
        monthly_bucket = monthly_buckets[month_key]
        monthly_bucket.crediario_inflow += event.crediario_inflow
        monthly_bucket.card_inflow += event.card_inflow
        monthly_bucket.launched_outflow += event.launched_outflow
        monthly_bucket.planned_purchase_outflow += event.planned_purchase_outflow

    daily_points: list[CashflowPoint] = []
    opening_balance = current_balance
    days = max((range_end - range_start).days + 1, 1)
    for offset in range(days):
        reference_date = range_start + timedelta(days=offset)
        bucket = daily_buckets[reference_date]
        closing_balance = opening_balance + bucket.inflow - bucket.outflow
        daily_points.append(
            CashflowPoint(
                reference=reference_date.isoformat(),
                opening_balance=opening_balance,
                crediario_inflows=bucket.crediario_inflow,
                card_inflows=bucket.card_inflow,
                launched_outflows=bucket.launched_outflow,
                planned_purchase_outflows=bucket.planned_purchase_outflow,
                inflows=bucket.inflow,
                outflows=bucket.outflow,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance

    monthly_points: list[CashflowPoint] = []
    weekly_points: list[CashflowPoint] = []
    opening_balance = current_balance
    month_start = date(range_start.year, range_start.month, 1)
    month_cursor = month_start
    while month_cursor <= range_end:
        reference_date = month_cursor
        key = _month_key(reference_date)
        bucket = monthly_buckets[key]
        closing_balance = opening_balance + bucket.inflow - bucket.outflow
        monthly_points.append(
            CashflowPoint(
                reference=key,
                opening_balance=opening_balance,
                crediario_inflows=bucket.crediario_inflow,
                card_inflows=bucket.card_inflow,
                launched_outflows=bucket.launched_outflow,
                planned_purchase_outflows=bucket.planned_purchase_outflow,
                inflows=bucket.inflow,
                outflows=bucket.outflow,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance
        month_cursor = _add_months(month_cursor, 1)

    opening_balance = current_balance
    week_cursor = range_start
    while week_cursor <= range_end:
        week_end = min(week_cursor + timedelta(days=6), range_end)
        bucket = CashflowBucket()
        current_day = week_cursor
        while current_day <= week_end:
            day_bucket = daily_buckets[current_day]
            bucket.crediario_inflow += day_bucket.crediario_inflow
            bucket.card_inflow += day_bucket.card_inflow
            bucket.launched_outflow += day_bucket.launched_outflow
            bucket.planned_purchase_outflow += day_bucket.planned_purchase_outflow
            current_day += timedelta(days=1)
        closing_balance = opening_balance + bucket.inflow - bucket.outflow
        weekly_points.append(
            CashflowPoint(
                reference=f"{week_cursor.isoformat()} a {week_end.isoformat()}",
                opening_balance=opening_balance,
                crediario_inflows=bucket.crediario_inflow,
                card_inflows=bucket.card_inflow,
                launched_outflows=bucket.launched_outflow,
                planned_purchase_outflows=bucket.planned_purchase_outflow,
                inflows=bucket.inflow,
                outflows=bucket.outflow,
                closing_balance=closing_balance,
            )
        )
        opening_balance = closing_balance
        week_cursor = week_end + timedelta(days=1)

    projected_inflows = sum((point.inflows for point in daily_points), Decimal("0.00"))
    projected_outflows = sum((point.outflows for point in daily_points), Decimal("0.00"))
    projected_ending_balance = daily_points[-1].closing_balance if daily_points else current_balance
    alerts = [
        f"Saldo projetado negativo em {point.reference}"
        for point in daily_points
        if point.closing_balance < 0
    ][:5]

    return CashflowOverview(
        current_balance=current_balance,
        projected_inflows=projected_inflows,
        projected_outflows=projected_outflows,
        planned_purchase_outflows=planned_purchase_outflows,
        projected_ending_balance=projected_ending_balance,
        alerts=alerts,
        account_balances=account_balances,
        daily_projection=daily_points,
        weekly_projection=weekly_points,
        monthly_projection=monthly_points,
    )


def get_cached_cashflow_overview(
    db: Session,
    company: Company,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
    include_purchase_planning: bool = True,
    include_crediario_receivables: bool = True,
    refresh: bool = False,
) -> CashflowOverview:
    today = date.today()
    range_start = start_date or date(today.year, today.month, 1)
    range_end = end_date or _month_end(today)
    if range_end < range_start:
        range_end = range_start
    segments = iter_month_segments(range_start, range_end)
    if len(segments) == 1:
        segment_start, segment_end = segments[0]
        return _get_cashflow_segment(
            db,
            company,
            start_date=segment_start,
            end_date=segment_end,
            account_id=account_id,
            include_purchase_planning=include_purchase_planning,
            include_crediario_receivables=include_crediario_receivables,
            refresh=refresh,
        )
    parts = [
        _get_cashflow_segment(
            db,
            company,
            start_date=segment_start,
            end_date=segment_end,
            account_id=account_id,
            include_purchase_planning=include_purchase_planning,
            include_crediario_receivables=include_crediario_receivables,
            refresh=refresh,
        )
        for segment_start, segment_end in segments
    ]
    return _compose_cashflow_segments(parts)

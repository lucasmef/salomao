from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from threading import Lock
from time import monotonic

from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.banking import BankTransaction, Reconciliation, ReconciliationLine
from app.db.models.finance import FinancialEntry
from app.db.models.linx import SalesSnapshot
from app.db.models.security import Company
from app.schemas.dashboard import (
    DashboardAccountBalance,
    DashboardKpis,
    DashboardOverview,
    DashboardPendingItem,
    DashboardRevenueComparison,
    DashboardRevenueComparisonPoint,
    DashboardSeriesPoint,
)
from app.services.cashflow import get_cached_cashflow_overview
from app.services.reports import get_cached_reports_overview

MONTH_LABELS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
CURRENT_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 86400
HISTORICAL_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 604800
MAX_OVERVIEW_CACHE_ITEMS = 24
HISTORICAL_REVENUE_COMPARISON_CACHE_TTL_SECONDS = 21600
MAX_REVENUE_COMPARISON_CACHE_ITEMS = 12


@dataclass(slots=True)
class DashboardOverviewCacheEntry:
    expires_at: float
    payload: DashboardOverview


_dashboard_overview_cache: dict[tuple[str, str, str], DashboardOverviewCacheEntry] = {}
_dashboard_overview_cache_lock = Lock()


@dataclass(slots=True)
class RevenueComparisonHistoryCacheEntry:
    expires_at: float
    totals_by_year_month: dict[tuple[int, int], Decimal]


_revenue_comparison_history_cache: dict[tuple[str, int, str], RevenueComparisonHistoryCacheEntry] = {}
_revenue_comparison_history_cache_lock = Lock()


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_end(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1).replace(day=1) - date.resolution
    return date(value.year, value.month + 1, 1) - date.resolution


def _is_full_month_period(start: date, end: date) -> bool:
    return start == _month_start(start) and end == _month_end(start)


def _overview_cache_ttl_seconds(start: date, end: date, *, today: date | None = None) -> int | None:
    if not _is_full_month_period(start, end):
        return None
    reference_day = today or date.today()
    current_month_start = _month_start(reference_day)
    current_month_end = _month_end(reference_day)
    if start == current_month_start and end == current_month_end:
        return CURRENT_MONTH_OVERVIEW_CACHE_TTL_SECONDS
    return HISTORICAL_MONTH_OVERVIEW_CACHE_TTL_SECONDS


def _overview_cache_key(company_id: str, start: date, end: date) -> tuple[str, str, str]:
    return company_id, start.isoformat(), end.isoformat()

def _prune_dashboard_overview_cache(now: float) -> None:
    expired_keys = [key for key, entry in _dashboard_overview_cache.items() if entry.expires_at <= now]
    for key in expired_keys:
        _dashboard_overview_cache.pop(key, None)
    if len(_dashboard_overview_cache) <= MAX_OVERVIEW_CACHE_ITEMS:
        return
    keys_by_expiry = sorted(_dashboard_overview_cache.items(), key=lambda item: item[1].expires_at)
    for key, _entry in keys_by_expiry[: len(_dashboard_overview_cache) - MAX_OVERVIEW_CACHE_ITEMS]:
        _dashboard_overview_cache.pop(key, None)


def clear_dashboard_overview_cache(company_id: str | None = None) -> None:
    with _dashboard_overview_cache_lock:
        if company_id is None:
            _dashboard_overview_cache.clear()
            return
        keys_to_remove = [key for key in _dashboard_overview_cache if key[0] == company_id]
        for key in keys_to_remove:
            _dashboard_overview_cache.pop(key, None)


def _revenue_comparison_history_cache_key(company_id: str, current_year: int, today: date) -> tuple[str, int, str]:
    return company_id, current_year, today.isoformat()


def _prune_revenue_comparison_history_cache(now: float) -> None:
    expired_keys = [key for key, entry in _revenue_comparison_history_cache.items() if entry.expires_at <= now]
    for key in expired_keys:
        _revenue_comparison_history_cache.pop(key, None)
    if len(_revenue_comparison_history_cache) <= MAX_REVENUE_COMPARISON_CACHE_ITEMS:
        return
    keys_by_expiry = sorted(_revenue_comparison_history_cache.items(), key=lambda item: item[1].expires_at)
    for key, _entry in keys_by_expiry[: len(_revenue_comparison_history_cache) - MAX_REVENUE_COMPARISON_CACHE_ITEMS]:
        _revenue_comparison_history_cache.pop(key, None)


def clear_dashboard_revenue_comparison_cache(company_id: str | None = None) -> None:
    with _revenue_comparison_history_cache_lock:
        if company_id is None:
            _revenue_comparison_history_cache.clear()
            return
        keys_to_remove = [key for key in _revenue_comparison_history_cache if key[0] == company_id]
        for key in keys_to_remove:
            _revenue_comparison_history_cache.pop(key, None)


def _query_revenue_totals_by_year_month(
    db: Session,
    company_id: str,
    *,
    start_date: date,
    end_date: date,
) -> dict[tuple[int, int], Decimal]:
    if end_date < start_date:
        return {}
    year_expr = extract("year", SalesSnapshot.snapshot_date)
    month_expr = extract("month", SalesSnapshot.snapshot_date)
    rows = db.execute(
        select(
            year_expr.label("year"),
            month_expr.label("month"),
            func.coalesce(func.sum(SalesSnapshot.gross_revenue), 0).label("amount"),
        )
        .where(
            SalesSnapshot.company_id == company_id,
            SalesSnapshot.snapshot_date >= start_date,
            SalesSnapshot.snapshot_date <= end_date,
        )
        .group_by(year_expr, month_expr)
    ).all()
    return {
        (int(row.year), int(row.month)): Decimal(row.amount or 0)
        for row in rows
        if row.year and row.month
    }


def _get_revenue_comparison_totals(
    db: Session,
    company_id: str,
    current_year: int,
    *,
    today: date | None = None,
) -> dict[tuple[int, int], Decimal]:
    reference_day = today or date.today()
    previous_year = current_year - 1
    start_date = date(previous_year, 1, 1)
    current_year_end = date(current_year, 12, 31)
    cacheable_end = current_year_end
    live_totals: dict[tuple[int, int], Decimal] = {}

    if current_year == reference_day.year:
        cacheable_end = min(current_year_end, reference_day - timedelta(days=1))
        live_totals = _query_revenue_totals_by_year_month(
            db,
            company_id,
            start_date=reference_day,
            end_date=min(reference_day, current_year_end),
        )

    cache_key = _revenue_comparison_history_cache_key(company_id, current_year, reference_day)
    current_time = monotonic()

    with _revenue_comparison_history_cache_lock:
        cached_entry = _revenue_comparison_history_cache.get(cache_key)
        if cached_entry and cached_entry.expires_at > current_time:
            historical_totals = dict(cached_entry.totals_by_year_month)
        else:
            historical_totals = _query_revenue_totals_by_year_month(
                db,
                company_id,
                start_date=start_date,
                end_date=cacheable_end,
            )
            _prune_revenue_comparison_history_cache(current_time)
            _revenue_comparison_history_cache[cache_key] = RevenueComparisonHistoryCacheEntry(
                expires_at=current_time + HISTORICAL_REVENUE_COMPARISON_CACHE_TTL_SECONDS,
                totals_by_year_month=dict(historical_totals),
            )

    if not live_totals:
        return historical_totals

    combined_totals = dict(historical_totals)
    for key, amount in live_totals.items():
        combined_totals[key] = combined_totals.get(key, Decimal("0.00")) + amount
    return combined_totals


def build_dashboard_overview(
    db: Session,
    company: Company,
    start: date,
    end: date,
) -> DashboardOverview:
    reports = get_cached_reports_overview(db, company, start=start, end=end)
    cashflow = get_cached_cashflow_overview(db, company, start_date=start, end_date=end)

    gross_revenue = Decimal(reports.dre.gross_revenue)
    net_revenue = Decimal(reports.dre.net_revenue)
    cmv = Decimal(reports.dre.cmv)
    purchases_paid = Decimal(reports.dro.purchases_paid)
    operating_expenses = Decimal(reports.dre.operating_expenses)
    financial_expenses = Decimal(reports.dre.financial_expenses)
    net_profit = Decimal(reports.dre.net_profit)
    profit_distribution = Decimal(reports.dre.profit_distribution)
    remaining_profit = Decimal(reports.dre.remaining_profit)

    overdue_filters = [
        FinancialEntry.company_id == company.id,
        FinancialEntry.is_deleted.is_(False),
        FinancialEntry.status.in_(["planned", "partial"]),
        FinancialEntry.due_date.is_not(None),
        FinancialEntry.due_date < date.today(),
        or_(
            FinancialEntry.external_source.is_(None),
            FinancialEntry.external_source != "historical_cashbook",
        ),
        or_(
            FinancialEntry.source_system.is_(None),
            FinancialEntry.source_system != "linx_sales_control",
        ),
    ]
    overdue_payables_entries = list(
        db.scalars(
            select(FinancialEntry)
            .where(*overdue_filters, FinancialEntry.entry_type == "expense")
            .order_by(FinancialEntry.due_date.asc())
            .limit(5)
        )
    )
    overdue_receivables_entries = list(
        db.scalars(
            select(FinancialEntry)
            .where(*overdue_filters, FinancialEntry.entry_type == "income")
            .order_by(FinancialEntry.due_date.asc())
            .limit(5)
        )
    )
    overdue_payables_count = db.scalar(
        select(func.count()).select_from(FinancialEntry).where(*overdue_filters, FinancialEntry.entry_type == "expense")
    ) or 0
    overdue_receivables_count = db.scalar(
        select(func.count()).select_from(FinancialEntry).where(*overdue_filters, FinancialEntry.entry_type == "income")
    ) or 0

    pending_reconciliations = db.scalar(
        select(func.count())
        .select_from(BankTransaction)
        .where(
            BankTransaction.company_id == company.id,
            ~BankTransaction.id.in_(select(Reconciliation.bank_transaction_id)),
            ~BankTransaction.id.in_(select(ReconciliationLine.bank_transaction_id)),
        )
    ) or 0

    current_year = end.year
    previous_year = current_year - 1
    revenue_by_year_month = _get_revenue_comparison_totals(db, company.id, current_year)
    revenue_comparison = DashboardRevenueComparison(
        current_year=current_year,
        previous_year=previous_year,
        points=[
            DashboardRevenueComparisonPoint(
                month=month,
                label=label,
                current_year_value=revenue_by_year_month.get((current_year, month), Decimal("0.00")),
                previous_year_value=revenue_by_year_month.get((previous_year, month), Decimal("0.00")),
            )
            for month, label in enumerate(MONTH_LABELS, start=1)
        ],
    )

    period_label = f"{start.isoformat()} a {end.isoformat()}"
    dre_cards = [
        DashboardSeriesPoint(label=card.label, value=Decimal(card.amount))
        for card in reports.dre.dashboard_cards
    ]
    dre_chart = list(dre_cards)

    def pending_item(entry: FinancialEntry) -> DashboardPendingItem:
        return DashboardPendingItem(
            id=entry.id,
            title=entry.title,
            due_date=entry.due_date.isoformat() if entry.due_date else None,
            amount=Decimal(entry.total_amount or 0) - Decimal(entry.paid_amount or 0),
            counterparty_name=entry.counterparty_name,
            account_name=entry.account.name if entry.account else None,
        )

    return DashboardOverview(
        period_label=period_label,
        kpis=DashboardKpis(
            gross_revenue=gross_revenue,
            net_revenue=net_revenue,
            cmv=cmv,
            purchases_paid=purchases_paid,
            operating_expenses=operating_expenses,
            financial_expenses=financial_expenses,
            net_profit=net_profit,
            profit_distribution=profit_distribution,
            remaining_profit=remaining_profit,
            current_balance=cashflow.current_balance,
            projected_balance=cashflow.projected_ending_balance,
            overdue_payables=overdue_payables_count,
            overdue_receivables=overdue_receivables_count,
            pending_reconciliations=pending_reconciliations,
        ),
        dre_cards=dre_cards,
        dre_chart=dre_chart,
        revenue_comparison=revenue_comparison,
        account_balances=[
            DashboardAccountBalance(
                account_id=balance.account_id,
                account_name=balance.account_name,
                account_type=balance.account_type,
                current_balance=balance.current_balance,
            )
            for balance in cashflow.account_balances
        ],
        overdue_payables=[pending_item(entry) for entry in overdue_payables_entries],
        overdue_receivables=[pending_item(entry) for entry in overdue_receivables_entries],
        pending_reconciliations=pending_reconciliations,
    )


def get_cached_dashboard_overview(
    db: Session,
    company: Company,
    start: date,
    end: date,
) -> DashboardOverview:
    ttl_seconds = _overview_cache_ttl_seconds(start, end)
    if ttl_seconds is None:
        return build_dashboard_overview(db, company, start=start, end=end)

    cache_key = _overview_cache_key(company.id, start, end)
    current_time = monotonic()

    with _dashboard_overview_cache_lock:
        cached_entry = _dashboard_overview_cache.get(cache_key)
        if cached_entry and cached_entry.expires_at > current_time:
            return cached_entry.payload.model_copy(deep=True)

    overview = build_dashboard_overview(db, company, start=start, end=end)

    with _dashboard_overview_cache_lock:
        _prune_dashboard_overview_cache(current_time)
        _dashboard_overview_cache[cache_key] = DashboardOverviewCacheEntry(
            expires_at=current_time + ttl_seconds,
            payload=overview.model_copy(deep=True),
        )

    return overview

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from threading import Lock
from time import monotonic

from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.banking import BankTransaction, Reconciliation, ReconciliationLine
from app.db.models.finance import Account, Category, FinancialEntry, Transfer
from app.db.models.imports import ImportBatch
from app.db.models.linx import ReceivableTitle, SalesSnapshot
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
from app.services.cashflow import build_cashflow_overview
from app.services.reports import build_reports_overview

MONTH_LABELS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
CURRENT_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 90
HISTORICAL_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 1800
MAX_OVERVIEW_CACHE_ITEMS = 24


@dataclass(slots=True)
class DashboardOverviewCacheEntry:
    signature: tuple[str, ...]
    expires_at: float
    payload: DashboardOverview


_dashboard_overview_cache: dict[tuple[str, str, str], DashboardOverviewCacheEntry] = {}
_dashboard_overview_cache_lock = Lock()


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


def _table_version(
    db: Session,
    model: type,
    company_id: str,
    *extra_filters: object,
) -> str:
    updated_at, count = db.execute(
        select(func.max(model.updated_at), func.count()).where(model.company_id == company_id, *extra_filters)
    ).one()
    updated_at_token = updated_at.isoformat() if updated_at else "-"
    return f"{updated_at_token}:{int(count or 0)}"


def _overview_cache_signature(db: Session, company_id: str, start: date, end: date) -> tuple[str, ...]:
    previous_year = end.year - 1
    return (
        date.today().isoformat(),
        _table_version(db, FinancialEntry, company_id),
        _table_version(db, Account, company_id),
        _table_version(db, Transfer, company_id),
        _table_version(db, Category, company_id),
        _table_version(db, BankTransaction, company_id),
        _table_version(db, Reconciliation, company_id),
        _table_version(db, ReconciliationLine, company_id),
        _table_version(
            db,
            SalesSnapshot,
            company_id,
            SalesSnapshot.snapshot_date >= date(previous_year, 1, 1),
            SalesSnapshot.snapshot_date <= date(end.year, 12, 31),
        ),
        _table_version(db, ReceivableTitle, company_id),
        _table_version(
            db,
            ImportBatch,
            company_id,
            ImportBatch.source_type.in_(("linx_receivables", "linx_sales", "linx_movements")),
        ),
    )


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


def build_dashboard_overview(
    db: Session,
    company: Company,
    start: date,
    end: date,
) -> DashboardOverview:
    reports = build_reports_overview(db, company, start=start, end=end)
    cashflow = build_cashflow_overview(db, company, start_date=start, end_date=end)

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
    year_expr = extract("year", SalesSnapshot.snapshot_date)
    month_expr = extract("month", SalesSnapshot.snapshot_date)
    revenue_rows = db.execute(
        select(
            year_expr.label("year"),
            month_expr.label("month"),
            func.coalesce(func.sum(SalesSnapshot.gross_revenue), 0).label("amount"),
        ).where(
            SalesSnapshot.company_id == company.id,
            SalesSnapshot.snapshot_date >= date(previous_year, 1, 1),
            SalesSnapshot.snapshot_date <= date(current_year, 12, 31),
        ).group_by(year_expr, month_expr)
    ).all()
    revenue_by_year_month = {
        (int(row.year), int(row.month)): Decimal(row.amount or 0)
        for row in revenue_rows
        if row.year and row.month
    }
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
    signature = _overview_cache_signature(db, company.id, start, end)
    current_time = monotonic()

    with _dashboard_overview_cache_lock:
        cached_entry = _dashboard_overview_cache.get(cache_key)
        if cached_entry and cached_entry.signature == signature and cached_entry.expires_at > current_time:
            return cached_entry.payload.model_copy(deep=True)

    overview = build_dashboard_overview(db, company, start=start, end=end)

    with _dashboard_overview_cache_lock:
        _prune_dashboard_overview_cache(current_time)
        _dashboard_overview_cache[cache_key] = DashboardOverviewCacheEntry(
            signature=signature,
            expires_at=current_time + ttl_seconds,
            payload=overview.model_copy(deep=True),
        )

    return overview

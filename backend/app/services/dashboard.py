from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from app.core.statuses import UNSETTLED_STATUS_QUERY_VALUES
from app.db.models.banking import BankTransaction, Reconciliation, ReconciliationLine
from app.db.models.finance import FinancialEntry
from app.db.models.linx import SalesSnapshot
from app.db.models.security import Company
from app.schemas.dashboard import (
    DashboardAccountBalance,
    DashboardBirthdayItem,
    DashboardDreLine,
    DashboardKpis,
    DashboardKpiSparklines,
    DashboardOverview,
    DashboardPendingItem,
    DashboardReconciliationItem,
    DashboardRevenueComparison,
    DashboardRevenueComparisonPoint,
    DashboardSeriesPoint,
    DashboardTodaySales,
    DashboardWeekBirthdays,
)
from app.services.analytics_hybrid import (
    ANALYTICS_DASHBOARD_OVERVIEW,
    ANALYTICS_REVENUE_COMPARISON,
    clear_live_cache,
    is_full_month_period,
    is_historical_period,
    read_live_cache,
    read_live_json_cache,
    read_snapshot_or_rebuild,
    upsert_monthly_snapshot,
    write_live_cache,
    write_live_json_cache,
)
from app.services.boletos import _load_all_receivable_items, _receivable_status_bucket
from app.services.cashflow import get_cached_cashflow_overview
from app.services.linx_customer_birthdays import (
    RECENT_PURCHASE_LOOKBACK_YEARS,
    list_birthday_customers_for_dates,
)
from app.services.reports import get_cached_reports_overview

MONTH_LABELS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
WEEKDAY_LABELS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
CURRENT_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 86400
HISTORICAL_MONTH_OVERVIEW_CACHE_TTL_SECONDS = 604800
MAX_OVERVIEW_CACHE_ITEMS = 24
HISTORICAL_REVENUE_COMPARISON_CACHE_TTL_SECONDS = 21600
DASHBOARD_TIMEZONE = ZoneInfo("America/Sao_Paulo")


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


def _today_in_sao_paulo() -> date:
    return datetime.now(DASHBOARD_TIMEZONE).date()


def _week_range(current_day: date) -> tuple[date, date]:
    week_start = current_day - timedelta(days=current_day.weekday())
    return week_start, week_start + timedelta(days=6)


def _format_week_label(start: date, end: date) -> str:
    return (
        f"{WEEKDAY_LABELS[start.weekday()]} {start.strftime('%d/%m')} a "
        f"{WEEKDAY_LABELS[end.weekday()]} {end.strftime('%d/%m')}"
    )


def _bucket_ranges(start: date, end: date, *, max_points: int = 8) -> list[tuple[date, date]]:
    if end < start:
        return []
    total_days = (end - start).days + 1
    bucket_days = max(1, (total_days + max_points - 1) // max_points)
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=bucket_days - 1))
        ranges.append((cursor, bucket_end))
        cursor = bucket_end + timedelta(days=1)
    return ranges


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _variation_percent(current: Decimal, previous: Decimal) -> Decimal | None:
    previous = Decimal(previous or 0)
    if previous == 0:
        return None
    return ((Decimal(current or 0) - previous) / abs(previous) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def build_dashboard_week_birthdays(
    db: Session,
    company: Company,
    *,
    today: date | None = None,
) -> DashboardWeekBirthdays:
    reference_day = today or _today_in_sao_paulo()
    week_start, week_end = _week_range(reference_day)
    target_dates = [week_start + timedelta(days=offset) for offset in range(7)]
    birthdays = list_birthday_customers_for_dates(
        db,
        company,
        target_dates=target_dates,
    )
    return DashboardWeekBirthdays(
        week_label=_format_week_label(week_start, week_end),
        purchase_lookback_years=RECENT_PURCHASE_LOOKBACK_YEARS,
        items=[
            DashboardBirthdayItem(
                linx_code=item.linx_code,
                customer_name=item.customer_name,
                birth_date=item.birth_date,
                birthday_date=item.birthday_date,
                last_purchase_date=item.last_purchase_at.date(),
            )
            for item in birthdays
        ],
    )


def build_dashboard_today_sales(
    db: Session,
    company: Company,
    *,
    today: date | None = None,
) -> DashboardTodaySales:
    reference_day = today or _today_in_sao_paulo()
    summary = db.execute(
        select(
            func.coalesce(func.sum(SalesSnapshot.gross_revenue), 0).label("gross_revenue"),
            func.max(SalesSnapshot.updated_at).label("updated_at"),
        ).where(
            SalesSnapshot.company_id == company.id,
            SalesSnapshot.snapshot_date == reference_day,
        )
    ).one()
    return DashboardTodaySales(
        sales_date=reference_day,
        gross_revenue=Decimal(summary.gross_revenue or 0),
        updated_at=summary.updated_at,
    )


def _build_kpi_sparklines(
    db: Session,
    company: Company,
    *,
    start: date,
    end: date,
    current_balance: Decimal,
    period_invoice_items: list[object],
) -> DashboardKpiSparklines:
    buckets = _bucket_ranges(start, end)
    if not buckets:
        return DashboardKpiSparklines()

    entry_rows = list(
        db.execute(
            select(
                FinancialEntry.entry_type,
                FinancialEntry.status,
                FinancialEntry.due_date,
                FinancialEntry.settled_at,
                FinancialEntry.total_amount,
                FinancialEntry.paid_amount,
            ).where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.is_deleted.is_(False),
                or_(
                    FinancialEntry.due_date.between(start, end),
                    func.date(FinancialEntry.settled_at).between(start, end),
                ),
            )
        )
    )
    sales_rows = list(
        db.execute(
            select(SalesSnapshot.snapshot_date, SalesSnapshot.gross_revenue).where(
                SalesSnapshot.company_id == company.id,
                SalesSnapshot.snapshot_date >= start,
                SalesSnapshot.snapshot_date <= end,
            )
        )
    )

    balance_deltas: list[Decimal] = []
    receivables: list[Decimal] = []
    payables: list[Decimal] = []
    delinquency: list[Decimal] = []
    sales: list[Decimal] = []
    today = _today_in_sao_paulo()

    for bucket_start, bucket_end in buckets:
        settled_delta = Decimal("0.00")
        receivable_total = Decimal("0.00")
        payable_total = Decimal("0.00")
        for row in entry_rows:
            entry_type, status, due_date, settled_at, total_amount, paid_amount = row
            outstanding = Decimal(total_amount or 0) - Decimal(paid_amount or 0)
            if due_date and bucket_start <= due_date <= bucket_end:
                if entry_type == "income" and status in UNSETTLED_STATUS_QUERY_VALUES:
                    receivable_total += outstanding
                if entry_type == "expense" and status in UNSETTLED_STATUS_QUERY_VALUES:
                    payable_total += outstanding
            if settled_at and bucket_start <= settled_at.date() <= bucket_end:
                paid = Decimal(paid_amount or total_amount or 0)
                settled_delta += paid if entry_type == "income" else -paid

        balance_deltas.append(settled_delta)
        receivables.append(_quantize_money(receivable_total))
        payables.append(_quantize_money(payable_total))
        delinquency.append(
            _quantize_money(
                sum(
                    (
                        Decimal(getattr(item, "amount", 0) or 0)
                        for item in period_invoice_items
                        if getattr(item, "due_date", None)
                        and bucket_start <= item.due_date <= bucket_end
                        and _receivable_status_bucket(item.status, item.due_date, today=today)
                        == "overdue"
                    ),
                    Decimal("0.00"),
                )
            )
        )
        sales.append(
            _quantize_money(
                sum(
                    (
                        Decimal(amount or 0)
                        for snapshot_date, amount in sales_rows
                        if bucket_start <= snapshot_date <= bucket_end
                    ),
                    Decimal("0.00"),
                )
            )
        )

    period_delta = sum(balance_deltas, Decimal("0.00"))
    running_balance = Decimal(current_balance or 0) - period_delta
    balance: list[Decimal] = []
    for delta in balance_deltas:
        running_balance += delta
        balance.append(_quantize_money(running_balance))

    return DashboardKpiSparklines(
        balance=balance,
        receivables=receivables,
        payables=payables,
        delinquency=delinquency,
        sales=sales,
    )


def clear_dashboard_overview_cache(company_id: str | None = None) -> None:
    clear_live_cache(company_id, kinds=[ANALYTICS_DASHBOARD_OVERVIEW])


def clear_dashboard_revenue_comparison_cache(company_id: str | None = None) -> None:
    clear_live_cache(company_id, kinds=[ANALYTICS_REVENUE_COMPARISON])


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
    refresh: bool = False,
) -> dict[tuple[int, int], Decimal]:
    reference_day = today or date.today()
    previous_year = current_year - 1
    start_date = date(previous_year, 1, 1)
    current_year_end = date(current_year, 12, 31)
    cacheable_end = current_year_end
    live_totals: dict[tuple[int, int], Decimal] = {}
    cache_params = {
        "current_year": current_year,
        "reference_month": f"{reference_day.year}-{reference_day.month:02d}",
    }

    if current_year == reference_day.year:
        cacheable_end = reference_day - timedelta(days=1)
        live_totals = _query_revenue_totals_by_year_month(
            db,
            company_id,
            start_date=reference_day,
            end_date=reference_day,
        )

    historical_totals: dict[tuple[int, int], Decimal] = {}
    if cacheable_end >= start_date:
        cached_payload = read_live_json_cache(
            kind=ANALYTICS_REVENUE_COMPARISON,
            company_id=company_id,
            start=start_date,
            end=cacheable_end,
            params=cache_params,
        ) if not refresh else None
        if cached_payload is not None:
            historical_totals = {
                (int(item["year"]), int(item["month"])): Decimal(item["amount"])
                for item in cached_payload.get("totals", [])
            }
        else:
            historical_totals = _query_revenue_totals_by_year_month(
                db,
                company_id,
                start_date=start_date,
                end_date=cacheable_end,
            )
            write_live_json_cache(
                {
                    "totals": [
                        {
                            "year": year,
                            "month": month,
                            "amount": str(amount),
                        }
                        for (year, month), amount in sorted(historical_totals.items())
                    ]
                },
                kind=ANALYTICS_REVENUE_COMPARISON,
                company_id=company_id,
                start=start_date,
                end=cacheable_end,
                ttl_seconds=HISTORICAL_REVENUE_COMPARISON_CACHE_TTL_SECONDS,
                params=cache_params,
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
    reports_override=None,
    cashflow_override=None,
    refresh: bool = False,
) -> DashboardOverview:
    reports = reports_override or get_cached_reports_overview(
        db,
        company,
        start=start,
        end=end,
    )
    period_days = max((end - start).days + 1, 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_reports = get_cached_reports_overview(
        db,
        company,
        start=previous_start,
        end=previous_end,
    )
    cashflow = cashflow_override or get_cached_cashflow_overview(
        db,
        company,
        start_date=start,
        end_date=end,
    )

    gross_revenue = Decimal(reports.dre.gross_revenue)
    net_revenue = Decimal(reports.dre.net_revenue)
    cmv = Decimal(reports.dre.cmv)
    purchases_paid = Decimal(reports.dro.purchases_paid)
    operating_expenses = Decimal(reports.dre.operating_expenses)
    financial_expenses = Decimal(reports.dre.financial_expenses)
    net_profit = Decimal(reports.dre.net_profit)
    profit_distribution = Decimal(reports.dre.profit_distribution)
    remaining_profit = Decimal(reports.dre.remaining_profit)

    today = _today_in_sao_paulo()
    unsettled_filters = [
        FinancialEntry.company_id == company.id,
        FinancialEntry.is_deleted.is_(False),
        FinancialEntry.status.in_(UNSETTLED_STATUS_QUERY_VALUES),
        FinancialEntry.due_date.is_not(None),
        or_(
            FinancialEntry.external_source.is_(None),
            FinancialEntry.external_source != "historical_cashbook",
        ),
        or_(
            FinancialEntry.source_system.is_(None),
            FinancialEntry.source_system != "linx_sales_control",
        ),
    ]
    overdue_filters = [
        *unsettled_filters,
        FinancialEntry.due_date < today,
    ]
    period_filters = [
        *unsettled_filters,
        FinancialEntry.due_date >= start,
        FinancialEntry.due_date <= end,
    ]
    outstanding_amount = FinancialEntry.total_amount - FinancialEntry.paid_amount

    def sum_outstanding(entry_type: str, filters: list[object]) -> Decimal:
        return db.scalar(
            select(func.coalesce(func.sum(outstanding_amount), Decimal("0.00"))).where(
                *filters,
                FinancialEntry.entry_type == entry_type,
            )
        ) or Decimal("0.00")

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
        select(func.count())
        .select_from(FinancialEntry)
        .where(*overdue_filters, FinancialEntry.entry_type == "expense")
    ) or 0
    receivables_period = sum_outstanding("income", period_filters)
    payables_period = sum_outstanding("expense", period_filters)
    invoice_items = _load_all_receivable_items(db, company.id)
    period_invoice_items = [
        item
        for item in invoice_items
        if item.due_date and start <= item.due_date <= end
    ]
    delinquency_invoice_items = [
        item
        for item in period_invoice_items
        if _receivable_status_bucket(item.status, item.due_date, today=today) == "overdue"
    ]
    active_invoice_items = [
        item
        for item in period_invoice_items
        if _receivable_status_bucket(item.status, item.due_date, today=today) in {"open", "overdue"}
    ]
    overdue_receivables_count = len(delinquency_invoice_items)
    overdue_receivables_amount = sum(
        (Decimal(item.amount or 0) for item in delinquency_invoice_items),
        Decimal("0.00"),
    )
    delinquency_base = sum(
        (Decimal(item.amount or 0) for item in active_invoice_items),
        Decimal("0.00"),
    )
    delinquency_rate = (
        (overdue_receivables_amount / delinquency_base) * Decimal("100")
        if delinquency_base
        else Decimal("0.00")
    ).quantize(Decimal("0.01"))

    pending_reconciliations = db.scalar(
        select(func.count())
        .select_from(BankTransaction)
        .where(
            BankTransaction.company_id == company.id,
            ~BankTransaction.id.in_(select(Reconciliation.bank_transaction_id)),
            ~BankTransaction.id.in_(select(ReconciliationLine.bank_transaction_id)),
        )
    ) or 0
    pending_reconciliation_transactions = list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.company_id == company.id,
                ~BankTransaction.id.in_(select(Reconciliation.bank_transaction_id)),
                ~BankTransaction.id.in_(select(ReconciliationLine.bank_transaction_id)),
            )
            .order_by(BankTransaction.posted_at.desc(), BankTransaction.created_at.desc())
            .limit(3)
        )
    )

    current_year = end.year
    previous_year = current_year - 1
    revenue_by_year_month = _get_revenue_comparison_totals(
        db,
        company.id,
        current_year,
        today=end,
        refresh=refresh,
    )
    revenue_comparison = DashboardRevenueComparison(
        current_year=current_year,
        previous_year=previous_year,
        points=[
            DashboardRevenueComparisonPoint(
                month=month,
                label=label,
                current_year_value=revenue_by_year_month.get(
                    (current_year, month),
                    Decimal("0.00"),
                ),
                previous_year_value=revenue_by_year_month.get(
                    (previous_year, month),
                    Decimal("0.00"),
                ),
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
    previous_cards_by_label = {
        card.label: Decimal(card.amount)
        for card in previous_reports.dre.dashboard_cards
    }
    dre_base = abs(gross_revenue) or Decimal("1.00")
    dre_lines = [
        DashboardDreLine(
            label=card.label,
            value=Decimal(card.amount),
            percent=(Decimal(card.amount) / dre_base * Decimal("100")).quantize(Decimal("0.01")),
            comparison_percent=_variation_percent(
                Decimal(card.amount),
                previous_cards_by_label.get(card.label, Decimal("0.00")),
            ),
        )
        for card in reports.dre.dashboard_cards
    ]
    kpi_sparklines = _build_kpi_sparklines(
        db,
        company,
        start=start,
        end=end,
        current_balance=cashflow.current_balance,
        period_invoice_items=period_invoice_items,
    )

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
            receivables_period=receivables_period,
            payables_period=payables_period,
            receivables_30d=receivables_period,
            payables_30d=payables_period,
            overdue_receivables_amount=overdue_receivables_amount,
            delinquency_rate=delinquency_rate,
            overdue_payables=overdue_payables_count,
            overdue_receivables=overdue_receivables_count,
            pending_reconciliations=pending_reconciliations,
        ),
        dre_cards=dre_cards,
        dre_chart=dre_chart,
        dre_lines=dre_lines,
        kpi_sparklines=kpi_sparklines,
        revenue_comparison=revenue_comparison,
        account_balances=[
            DashboardAccountBalance(
                account_id=balance.account_id,
                account_name=balance.account_name,
                account_type=balance.account_type,
                current_balance=balance.current_balance,
                exclude_from_balance=balance.exclude_from_balance,
            )
            for balance in cashflow.account_balances
        ],
        overdue_payables=[pending_item(entry) for entry in overdue_payables_entries],
        overdue_receivables=[pending_item(entry) for entry in overdue_receivables_entries],
        pending_reconciliations=pending_reconciliations,
        pending_reconciliation_items=[
            DashboardReconciliationItem(
                id=transaction.id,
                bank_name=transaction.bank_name,
                posted_at=transaction.posted_at,
                description=transaction.memo or transaction.name or transaction.fit_id,
                amount=transaction.amount,
                account_name=transaction.account.name if transaction.account else None,
            )
            for transaction in pending_reconciliation_transactions
        ],
    )


def get_cached_dashboard_overview(
    db: Session,
    company: Company,
    start: date,
    end: date,
    refresh: bool = False,
) -> DashboardOverview:

    if not is_full_month_period(start, end):
        if refresh:
            reports = get_cached_reports_overview(db, company, start=start, end=end, refresh=True)
            cashflow = get_cached_cashflow_overview(
                db,
                company,
                start_date=start,
                end_date=end,
                refresh=True,
            )
            return build_dashboard_overview(
                db,
                company,
                start=start,
                end=end,
                reports_override=reports,
                cashflow_override=cashflow,
                refresh=refresh,
            )
        return build_dashboard_overview(db, company, start=start, end=end)
    if is_historical_period(start, end):
        if refresh:
            reports = get_cached_reports_overview(db, company, start=start, end=end, refresh=True)
            cashflow = get_cached_cashflow_overview(
                db,
                company,
                start_date=start,
                end_date=end,
                refresh=True,
            )
            overview = build_dashboard_overview(
                db,
                company,
                start=start,
                end=end,
                reports_override=reports,
                cashflow_override=cashflow,
                refresh=refresh,
            )
            upsert_monthly_snapshot(
                db,
                overview,
                company_id=company.id,
                kind=ANALYTICS_DASHBOARD_OVERVIEW,
                snapshot_month=start,
            )
            return overview
        return read_snapshot_or_rebuild(
            db,
            DashboardOverview,
            company=company,
            kind=ANALYTICS_DASHBOARD_OVERVIEW,
            snapshot_month=start,
            build_func=lambda: build_dashboard_overview(
                db,
                company,
                start=start,
                end=end,
                refresh=refresh,
            ),
        )
    ttl_seconds = _overview_cache_ttl_seconds(start, end)
    if not refresh:
        cached = read_live_cache(
            DashboardOverview,
            kind=ANALYTICS_DASHBOARD_OVERVIEW,
            company_id=company.id,
            start=start,
            end=end,
        )
        if cached is not None:
            return cached
    if refresh:
        reports = get_cached_reports_overview(db, company, start=start, end=end, refresh=True)
        cashflow = get_cached_cashflow_overview(
            db,
            company,
            start_date=start,
            end_date=end,
            refresh=True,
        )
        overview = build_dashboard_overview(
            db,
            company,
            start=start,
            end=end,
            reports_override=reports,
            cashflow_override=cashflow,
            refresh=refresh,
        )
    else:
        overview = build_dashboard_overview(db, company, start=start, end=end, refresh=refresh)
    if ttl_seconds:
        write_live_cache(
            overview,
            kind=ANALYTICS_DASHBOARD_OVERVIEW,
            company_id=company.id,
            start=start,
            end=end,
            ttl_seconds=ttl_seconds,
        )
    return overview

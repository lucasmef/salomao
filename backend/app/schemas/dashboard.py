from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardKpis(BaseModel):
    gross_revenue: Decimal
    net_revenue: Decimal
    cmv: Decimal
    purchases_paid: Decimal
    operating_expenses: Decimal
    financial_expenses: Decimal
    net_profit: Decimal
    profit_distribution: Decimal
    remaining_profit: Decimal
    current_balance: Decimal
    projected_balance: Decimal
    receivables_30d: Decimal = Decimal("0.00")
    payables_30d: Decimal = Decimal("0.00")
    overdue_receivables_amount: Decimal = Decimal("0.00")
    delinquency_rate: Decimal = Decimal("0.00")
    overdue_payables: int
    overdue_receivables: int
    pending_reconciliations: int


class DashboardSeriesPoint(BaseModel):
    label: str
    value: Decimal


class DashboardRevenueComparisonPoint(BaseModel):
    month: int
    label: str
    current_year_value: Decimal
    previous_year_value: Decimal


class DashboardRevenueComparison(BaseModel):
    current_year: int
    previous_year: int
    points: list[DashboardRevenueComparisonPoint]


class DashboardPendingItem(BaseModel):
    id: str
    title: str
    due_date: str | None
    amount: Decimal
    counterparty_name: str | None
    account_name: str | None


class DashboardReconciliationItem(BaseModel):
    id: str
    bank_name: str | None
    posted_at: date
    description: str
    amount: Decimal
    account_name: str | None


class DashboardAccountBalance(BaseModel):
    account_id: str
    account_name: str
    account_type: str
    current_balance: Decimal
    exclude_from_balance: bool = False


class DashboardBirthdayItem(BaseModel):
    linx_code: int
    customer_name: str
    birth_date: date
    birthday_date: date
    last_purchase_date: date


class DashboardWeekBirthdays(BaseModel):
    week_label: str | None = None
    purchase_lookback_years: int = 5
    items: list[DashboardBirthdayItem] = Field(default_factory=list)


class DashboardTodaySales(BaseModel):
    sales_date: date
    gross_revenue: Decimal = Decimal("0.00")
    updated_at: datetime | None = None


class DashboardOverview(BaseModel):
    period_label: str
    kpis: DashboardKpis
    dre_cards: list[DashboardSeriesPoint]
    dre_chart: list[DashboardSeriesPoint]
    revenue_comparison: DashboardRevenueComparison
    account_balances: list[DashboardAccountBalance]
    overdue_payables: list[DashboardPendingItem]
    overdue_receivables: list[DashboardPendingItem]
    pending_reconciliations: int
    pending_reconciliation_items: list[DashboardReconciliationItem] = Field(default_factory=list)
    week_birthdays: DashboardWeekBirthdays = Field(default_factory=DashboardWeekBirthdays)
    today_sales: DashboardTodaySales | None = None

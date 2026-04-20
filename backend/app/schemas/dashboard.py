from datetime import date
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
    items: list[DashboardBirthdayItem] = Field(default_factory=list)


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
    week_birthdays: DashboardWeekBirthdays = Field(default_factory=DashboardWeekBirthdays)

from decimal import Decimal

from pydantic import BaseModel


class AccountBalance(BaseModel):
    account_id: str
    account_name: str
    account_type: str
    current_balance: Decimal
    exclude_from_balance: bool = False


class CashflowPoint(BaseModel):
    reference: str
    opening_balance: Decimal
    crediario_inflows: Decimal
    card_inflows: Decimal
    launched_outflows: Decimal
    planned_purchase_outflows: Decimal
    inflows: Decimal
    outflows: Decimal
    closing_balance: Decimal


class CashflowOverview(BaseModel):
    current_balance: Decimal
    projected_inflows: Decimal
    projected_outflows: Decimal
    planned_purchase_outflows: Decimal
    projected_ending_balance: Decimal
    alerts: list[str]
    account_balances: list[AccountBalance]
    daily_projection: list[CashflowPoint]
    weekly_projection: list[CashflowPoint]
    monthly_projection: list[CashflowPoint]

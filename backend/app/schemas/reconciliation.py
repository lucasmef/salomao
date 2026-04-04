from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.dashboard import DashboardAccountBalance


class ReconciliationCandidate(BaseModel):
    financial_entry_id: str
    title: str
    counterparty_name: str | None
    entry_type: str
    status: str
    due_date: date | None
    total_amount: Decimal
    account_name: str | None
    score: float
    reasons: list[str]


class ReconciliationAppliedEntry(BaseModel):
    financial_entry_id: str
    title: str
    amount_applied: Decimal
    status: str
    can_delete_on_unreconcile: bool = False


class BankTransactionWorkItem(BaseModel):
    bank_transaction_id: str
    account_id: str | None = None
    posted_at: date
    amount: Decimal
    trn_type: str
    fit_id: str
    memo: str | None
    name: str | None
    account_name: str | None
    reconciliation_status: str
    undo_mode: str | None = None
    applied_entries: list[ReconciliationAppliedEntry] = []
    candidates: list[ReconciliationCandidate]


class ReconciliationWorklist(BaseModel):
    unreconciled_count: int
    overall_unreconciled_count: int
    matched_count: int
    total: int
    page: int
    page_size: int
    total_account_balance: Decimal = Decimal("0.00")
    account_balances: list[DashboardAccountBalance] = []
    items: list[BankTransactionWorkItem]


class ReconciliationCreate(BaseModel):
    bank_transaction_ids: list[str] = Field(min_length=1)
    financial_entry_ids: list[str] = Field(min_length=1)
    match_type: str = "manual"
    notes: str | None = None
    principal_amount: Decimal | None = None
    interest_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    penalty_amount: Decimal | None = None

    @model_validator(mode="after")
    def ensure_ids(self) -> "ReconciliationCreate":
        if not self.bank_transaction_ids or not self.financial_entry_ids:
            raise ValueError("E necessario informar movimentos bancarios e lancamentos")
        return self


class BankTransactionActionCreate(BaseModel):
    bank_transaction_ids: list[str] = Field(default_factory=list)
    bank_transaction_id: str | None = None
    action_type: str = Field(pattern="^(create_entry|mark_bank_fee|mark_transfer)$")
    title: str | None = None
    category_id: str | None = None
    supplier_id: str | None = None
    account_id: str | None = None
    counterparty_name: str | None = None
    notes: str | None = None
    destination_account_id: str | None = None

    @model_validator(mode="after")
    def ensure_bank_transactions(self) -> "BankTransactionActionCreate":
        if self.bank_transaction_id and self.bank_transaction_id not in self.bank_transaction_ids:
            self.bank_transaction_ids.append(self.bank_transaction_id)
        if not self.bank_transaction_ids:
            raise ValueError("E necessario informar pelo menos um movimento bancario")
        return self


class ReconciliationLineRead(BaseModel):
    bank_transaction_id: str
    financial_entry_id: str
    amount_applied: Decimal


class ReconciliationRead(BaseModel):
    id: str
    match_type: str
    confidence_score: float | None
    notes: str | None
    created_at: datetime
    lines: list[ReconciliationLineRead] = []

    model_config = {"from_attributes": True}


class ReconciliationUndoRequest(BaseModel):
    bank_transaction_id: str
    delete_generated_entries: bool = False


class ReconciliationUndoResponse(BaseModel):
    bank_transaction_ids: list[str]
    reopened_entry_ids: list[str] = []
    deleted_entry_ids: list[str] = []

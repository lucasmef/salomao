from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.reconciliation import (
    BankTransactionActionCreate,
    ReconciliationCreate,
    ReconciliationUndoRequest,
    ReconciliationUndoResponse,
    ReconciliationLineRead,
    ReconciliationRead,
    ReconciliationWorklist,
)
from app.services.cache_invalidation import clear_finance_analytics_caches
from app.services.company_context import get_current_company
from app.services.reconciliation import (
    build_reconciliation_worklist,
    create_entry_from_bank_transaction,
    create_reconciliation,
    undo_reconciliation_by_bank_transaction,
)

router = APIRouter()


@router.get("/worklist", response_model=ReconciliationWorklist)
def get_reconciliation_worklist(
    db: DbSession,
    page: int = Query(default=1, ge=1, le=10000),
    limit: int = Query(default=25, ge=1, le=5000),
    account_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    min_amount: Decimal | None = Query(default=None),
    max_amount: Decimal | None = Query(default=None),
) -> ReconciliationWorklist:
    company = get_current_company(db)
    return build_reconciliation_worklist(
        db,
        company,
        page=page,
        limit=limit,
        account_id=account_id,
        search=search,
        date_from=start,
        date_to=end,
        min_amount=min_amount,
        max_amount=max_amount,
    )


@router.post("/matches", response_model=ReconciliationRead, status_code=status.HTTP_201_CREATED)
def create_match(
    payload: ReconciliationCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ReconciliationRead:
    company = get_current_company(db)
    try:
        reconciliation = create_reconciliation(db, company, payload, current_user)
        db.commit()
        clear_finance_analytics_caches(company.id)
        db.refresh(reconciliation)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    lines = [
        ReconciliationLineRead(
            bank_transaction_id=line.bank_transaction_id,
            financial_entry_id=line.financial_entry_id,
            amount_applied=line.amount_applied,
        )
        for line in reconciliation.reconciliation_lines
    ] if hasattr(reconciliation, "reconciliation_lines") else []
    return ReconciliationRead(
        id=reconciliation.id,
        match_type=reconciliation.match_type,
        confidence_score=reconciliation.confidence_score,
        notes=reconciliation.notes,
        created_at=reconciliation.created_at,
        lines=lines,
    )


@router.post("/actions", response_model=dict[str, str], status_code=status.HTTP_201_CREATED)
def create_action_from_bank(
    payload: BankTransactionActionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, str]:
    company = get_current_company(db)
    try:
        result = create_entry_from_bank_transaction(db, company, payload, current_user)
        db.commit()
        clear_finance_analytics_caches(company.id)
        return {key: str(value) for key, value in result.items()}
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/unmatch", response_model=ReconciliationUndoResponse)
def undo_match(
    payload: ReconciliationUndoRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ReconciliationUndoResponse:
    company = get_current_company(db)
    try:
        result = undo_reconciliation_by_bank_transaction(
            db,
            company,
            payload.bank_transaction_id,
            payload.delete_generated_entries,
            current_user,
        )
        db.commit()
        clear_finance_analytics_caches(company.id)
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error

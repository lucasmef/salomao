from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.transfer import TransferCreate, TransferRead
from app.services.cache_invalidation import clear_finance_analytics_caches
from app.services.company_context import get_current_company
from app.services.finance_ops import create_transfer, delete_transfer, list_transfers

router = APIRouter()


def _serialize_transfer(transfer) -> TransferRead:
    return TransferRead(
        id=transfer.id,
        company_id=transfer.company_id,
        source_account_id=transfer.source_account_id,
        destination_account_id=transfer.destination_account_id,
        transfer_date=transfer.transfer_date,
        amount=transfer.amount,
        status=transfer.status,
        description=transfer.description,
        notes=transfer.notes,
        source_entry_id=transfer.source_entry_id,
        destination_entry_id=transfer.destination_entry_id,
        source_account_name=transfer.source_account.name if transfer.source_account else None,
        destination_account_name=transfer.destination_account.name if transfer.destination_account else None,
    )


@router.get("", response_model=list[TransferRead])
def get_transfers(db: DbSession, limit: int = Query(default=200, ge=1, le=1000)) -> list[TransferRead]:
    company = get_current_company(db)
    return [_serialize_transfer(item) for item in list_transfers(db, company, limit=limit)]


@router.post("", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def post_transfer(payload: TransferCreate, db: DbSession, current_user: CurrentUser) -> TransferRead:
    company = get_current_company(db)
    transfer = create_transfer(db, company, payload, current_user)
    db.commit()
    clear_finance_analytics_caches(
        company.id,
        db=db,
        company=company,
        affected_dates=[transfer.transfer_date] if transfer.transfer_date else None,
    )
    db.refresh(transfer)
    return _serialize_transfer(transfer)


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer_route(transfer_id: str, db: DbSession, current_user: CurrentUser) -> None:
    company = get_current_company(db)
    transfer = delete_transfer(db, company, transfer_id, current_user)
    db.commit()
    clear_finance_analytics_caches(
        company.id,
        db=db,
        company=company,
        affected_dates=[transfer.transfer_date] if transfer.transfer_date else None,
    )

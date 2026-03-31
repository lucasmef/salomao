from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models.finance import Account
from app.schemas.account import AccountCreate, AccountRead
from app.services.audit import write_audit_log
from app.services.company_context import get_current_company

router = APIRouter()


@router.get("", response_model=list[AccountRead])
def list_accounts(db: DbSession) -> list[Account]:
    company = get_current_company(db)
    return list(
        db.scalars(
            select(Account)
            .where(Account.company_id == company.id)
            .order_by(Account.name.asc())
        )
    )


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession, current_user: CurrentUser) -> Account:
    company = get_current_company(db)
    account = Account(company_id=company.id, **payload.model_dump())
    db.add(account)
    db.flush()
    write_audit_log(
        db,
        action="create_account",
        entity_name="account",
        entity_id=account.id,
        company_id=company.id,
        actor_user=current_user,
        after_state={
            "name": account.name,
            "account_type": account.account_type,
            "import_ofx_enabled": account.import_ofx_enabled,
        },
    )
    db.commit()
    db.refresh(account)
    return account


@router.put("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Account:
    company = get_current_company(db)
    account = db.get(Account, account_id)
    if not account or account.company_id != company.id:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")
    before_state = {
        "name": account.name,
        "account_type": account.account_type,
        "is_active": account.is_active,
        "import_ofx_enabled": account.import_ofx_enabled,
    }
    for field_name, value in payload.model_dump().items():
        setattr(account, field_name, value)
    db.flush()
    write_audit_log(
        db,
        action="update_account",
        entity_name="account",
        entity_id=account.id,
        company_id=company.id,
        actor_user=current_user,
        before_state=before_state,
        after_state={
            "name": account.name,
            "account_type": account.account_type,
            "is_active": account.is_active,
            "import_ofx_enabled": account.import_ofx_enabled,
        },
    )
    db.commit()
    db.refresh(account)
    return account

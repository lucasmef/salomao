from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.crypto import encrypt_text
from app.db.models.finance import Account
from app.schemas.account import AccountCreate, AccountRead
from app.services.audit import write_audit_log
from app.services.company_context import get_current_company

router = APIRouter()


def _serialize_account(account: Account) -> AccountRead:
    return AccountRead(
        id=account.id,
        company_id=account.company_id,
        name=account.name,
        account_type=account.account_type,
        bank_code=account.bank_code,
        branch_number=account.branch_number,
        account_number=account.account_number,
        opening_balance=account.opening_balance,
        is_active=account.is_active,
        import_ofx_enabled=account.import_ofx_enabled,
        inter_api_enabled=account.inter_api_enabled,
        inter_environment=account.inter_environment,
        inter_api_base_url=account.inter_api_base_url,
        inter_api_key=account.inter_api_key,
        inter_account_number=account.inter_account_number,
        c6_api_enabled=account.c6_api_enabled,
        c6_environment=account.c6_environment,
        c6_api_base_url=account.c6_api_base_url,
        c6_client_id=account.c6_client_id,
        c6_partner_software_name=account.c6_partner_software_name,
        c6_partner_software_version=account.c6_partner_software_version,
        has_inter_client_secret=bool(account.inter_client_secret_encrypted),
        has_inter_certificate=bool(account.inter_certificate_pem_encrypted),
        has_inter_private_key=bool(account.inter_private_key_pem_encrypted),
        has_c6_client_secret=bool(account.c6_client_secret_encrypted),
        has_c6_certificate=bool(account.c6_certificate_pem_encrypted),
        has_c6_private_key=bool(account.c6_private_key_pem_encrypted),
    )


def _normalize_optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _apply_account_payload(account: Account, payload: AccountCreate, *, preserve_inter_secrets: bool) -> None:
    data = payload.model_dump(
        exclude={
            "inter_client_secret",
            "inter_certificate_pem",
            "inter_private_key_pem",
            "c6_client_secret",
            "c6_certificate_pem",
            "c6_private_key_pem",
        }
    )
    for field_name, value in data.items():
        setattr(account, field_name, value)

    secret_value = _normalize_optional_text(payload.inter_client_secret)
    certificate_value = _normalize_optional_text(payload.inter_certificate_pem)
    private_key_value = _normalize_optional_text(payload.inter_private_key_pem)
    c6_secret_value = _normalize_optional_text(payload.c6_client_secret)
    c6_certificate_value = _normalize_optional_text(payload.c6_certificate_pem)
    c6_private_key_value = _normalize_optional_text(payload.c6_private_key_pem)

    if not preserve_inter_secrets or secret_value is not None:
        account.inter_client_secret_encrypted = encrypt_text(secret_value)
    if not preserve_inter_secrets or certificate_value is not None:
        account.inter_certificate_pem_encrypted = encrypt_text(certificate_value)
    if not preserve_inter_secrets or private_key_value is not None:
        account.inter_private_key_pem_encrypted = encrypt_text(private_key_value)
    if not preserve_inter_secrets or c6_secret_value is not None:
        account.c6_client_secret_encrypted = encrypt_text(c6_secret_value)
    if not preserve_inter_secrets or c6_certificate_value is not None:
        account.c6_certificate_pem_encrypted = encrypt_text(c6_certificate_value)
    if not preserve_inter_secrets or c6_private_key_value is not None:
        account.c6_private_key_pem_encrypted = encrypt_text(c6_private_key_value)


def _ensure_single_inter_account(db: DbSession, company_id: str, active_account_id: str) -> None:
    for account in db.scalars(
        select(Account).where(
            Account.company_id == company_id,
            Account.id != active_account_id,
            Account.inter_api_enabled.is_(True),
        )
        ):
            account.inter_api_enabled = False


def _ensure_single_c6_account(db: DbSession, company_id: str, active_account_id: str) -> None:
    for account in db.scalars(
        select(Account).where(
            Account.company_id == company_id,
            Account.id != active_account_id,
            Account.c6_api_enabled.is_(True),
        )
    ):
        account.c6_api_enabled = False


@router.get("", response_model=list[AccountRead])
def list_accounts(db: DbSession) -> list[AccountRead]:
    company = get_current_company(db)
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.company_id == company.id)
            .order_by(Account.name.asc())
        )
    )
    return [_serialize_account(account) for account in accounts]


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession, current_user: CurrentUser) -> AccountRead:
    company = get_current_company(db)
    account = Account(company_id=company.id)
    _apply_account_payload(account, payload, preserve_inter_secrets=False)
    db.add(account)
    db.flush()
    if account.inter_api_enabled:
        _ensure_single_inter_account(db, company.id, account.id)
    if account.c6_api_enabled:
        _ensure_single_c6_account(db, company.id, account.id)
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
    return _serialize_account(account)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> AccountRead:
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
    _apply_account_payload(account, payload, preserve_inter_secrets=True)
    db.flush()
    if account.inter_api_enabled:
        _ensure_single_inter_account(db, company.id, account.id)
    if account.c6_api_enabled:
        _ensure_single_c6_account(db, company.id, account.id)
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
    return _serialize_account(account)

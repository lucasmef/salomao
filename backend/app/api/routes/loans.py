from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.loan import LoanContractCreate, LoanContractRead, LoanInstallmentRead
from app.services.company_context import get_current_company
from app.services.finance_ops import create_loan_contract, list_loans

router = APIRouter()


def _serialize_loan(contract) -> LoanContractRead:
    installments = [
        LoanInstallmentRead.model_validate(item)
        for item in contract.installments
    ] if hasattr(contract, "installments") else []
    return LoanContractRead(
        id=contract.id,
        company_id=contract.company_id,
        account_id=contract.account_id,
        lender_name=contract.lender_name,
        contract_number=contract.contract_number,
        title=contract.title,
        start_date=contract.start_date,
        first_due_date=contract.first_due_date,
        installments_count=contract.installments_count,
        principal_total=contract.principal_total,
        interest_total=contract.interest_total,
        installment_amount=contract.installment_amount,
        notes=contract.notes,
        is_active=contract.is_active,
        installments=installments,
    )


@router.get("", response_model=list[LoanContractRead])
def get_loans(db: DbSession) -> list[LoanContractRead]:
    company = get_current_company(db)
    return [_serialize_loan(item) for item in list_loans(db, company)]


@router.post("", response_model=LoanContractRead, status_code=status.HTTP_201_CREATED)
def post_loan(
    payload: LoanContractCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> LoanContractRead:
    company = get_current_company(db)
    contract = create_loan_contract(db, company, payload, current_user)
    db.commit()
    db.refresh(contract)
    return _serialize_loan(contract)

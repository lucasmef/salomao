from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.linx_customers import LinxCustomerDirectoryRead
from app.services.company_context import get_current_company
from app.services.linx_customers import list_linx_customer_directory

router = APIRouter()


@router.get("", response_model=LinxCustomerDirectoryRead)
def get_linx_customers_directory(
    db: DbSession,
) -> LinxCustomerDirectoryRead:
    company = get_current_company(db)
    return list_linx_customer_directory(db, company)

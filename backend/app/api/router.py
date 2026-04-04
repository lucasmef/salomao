from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.routes import (
    accounts,
    auth,
    backup,
    boletos,
    cashflow,
    categories,
    company_settings,
    dashboard,
    entries,
    health,
    imports,
    loans,
    meta,
    purchase_planning,
    recurrences,
    reconciliation,
    reports,
    transfers,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
protected = [Depends(get_current_user)]
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"], dependencies=protected)
api_router.include_router(backup.router, prefix="/backup", tags=["backup"], dependencies=protected)
api_router.include_router(boletos.router, prefix="/boletos", tags=["boletos"], dependencies=protected)
api_router.include_router(categories.router, prefix="/categories", tags=["categories"], dependencies=protected)
api_router.include_router(
    company_settings.router,
    prefix="/company-settings",
    tags=["company-settings"],
    dependencies=protected,
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"], dependencies=protected)
api_router.include_router(entries.router, prefix="/entries", tags=["entries"], dependencies=protected)
api_router.include_router(imports.router, prefix="/imports", tags=["imports"], dependencies=protected)
api_router.include_router(loans.router, prefix="/loans", tags=["loans"], dependencies=protected)
api_router.include_router(purchase_planning.router, prefix="", tags=["purchase-planning"], dependencies=protected)
api_router.include_router(recurrences.router, prefix="/recurrences", tags=["recurrences"], dependencies=protected)
api_router.include_router(cashflow.router, prefix="/cashflow", tags=["cashflow"], dependencies=protected)
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"], dependencies=protected)
api_router.include_router(reports.router, prefix="/reports", tags=["reports"], dependencies=protected)
api_router.include_router(transfers.router, prefix="/transfers", tags=["transfers"], dependencies=protected)

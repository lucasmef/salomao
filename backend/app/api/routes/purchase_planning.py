from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.imports import ImportResult
from app.schemas.purchase_planning import (
    CollectionSeasonCreate,
    CollectionSeasonRead,
    CollectionSeasonUpdate,
    PurchaseBrandCreate,
    PurchaseBrandRead,
    PurchaseBrandUpdate,
    PurchaseInstallmentLinkRequest,
    PurchaseInstallmentRead,
    PurchaseInvoiceCreate,
    PurchaseInvoiceDraft,
    PurchaseInvoiceImportTextRequest,
    PurchaseInvoiceRead,
    PurchasePlanCreate,
    PurchasePlanningMonthlyProjection,
    PurchasePlanningOverview,
    PurchasePlanRead,
    PurchasePlanUpdate,
    PurchaseReturnCreate,
    PurchaseReturnRead,
    PurchaseReturnUpdate,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from app.services.company_context import get_current_company
from app.services.data_refresh import build_data_refresh_request, finalize_data_refresh
from app.services.purchase_planning import (
    PurchasePlanningFilters,
    build_purchase_planning_cashflow,
    clear_purchase_planning_overview_cache,
    create_brand,
    create_collection,
    create_purchase_invoice,
    create_purchase_plan,
    create_purchase_return,
    get_cached_purchase_planning_overview,
    create_supplier,
    delete_brand,
    delete_collection,
    delete_purchase_plan,
    delete_purchase_return,
    delete_supplier,
    link_installment_to_entry,
    list_brands,
    list_collections,
    list_purchase_invoice_suppliers,
    list_purchase_invoices,
    list_purchase_plans,
    list_purchase_returns,
    list_suppliers,
    parse_purchase_invoice_text,
    parse_purchase_invoice_xml,
    sync_linx_purchase_payables,
    update_brand,
    update_collection,
    update_purchase_plan,
    update_purchase_return,
    update_supplier,
)

router = APIRouter()


def _finalize_purchase_refresh(db: DbSession, company) -> None:
    refresh_request = build_data_refresh_request("purchase_payables")
    finalize_data_refresh(db, company, refresh_request)


@router.get("/brands", response_model=list[PurchaseBrandRead])
def get_brands(db: DbSession) -> list[PurchaseBrandRead]:
    company = get_current_company(db)
    return list_brands(db, company)


@router.post("/brands", response_model=PurchaseBrandRead, status_code=status.HTTP_201_CREATED)
def post_brand(payload: PurchaseBrandCreate, db: DbSession, current_user: CurrentUser) -> PurchaseBrandRead:
    company = get_current_company(db)
    brand = create_brand(db, company, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return brand


@router.put("/brands/{brand_id}", response_model=PurchaseBrandRead)
def put_brand(
    brand_id: str,
    payload: PurchaseBrandUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> PurchaseBrandRead:
    company = get_current_company(db)
    brand = update_brand(db, company, brand_id, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return brand


@router.delete("/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand_route(
    brand_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    company = get_current_company(db)
    delete_brand(db, company, brand_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()


@router.get("/suppliers", response_model=list[SupplierRead])
def get_suppliers(db: DbSession) -> list[SupplierRead]:
    company = get_current_company(db)
    return list_suppliers(db, company)


@router.get("/purchase-suppliers", response_model=list[SupplierRead])
def get_purchase_suppliers(db: DbSession) -> list[SupplierRead]:
    company = get_current_company(db)
    return list_purchase_invoice_suppliers(db, company)


@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def post_supplier(payload: SupplierCreate, db: DbSession, current_user: CurrentUser) -> SupplierRead:
    company = get_current_company(db)
    supplier = create_supplier(db, company, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return supplier


@router.put("/suppliers/{supplier_id}", response_model=SupplierRead)
def put_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> SupplierRead:
    company = get_current_company(db)
    supplier = update_supplier(db, company, supplier_id, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return supplier


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_route(
    supplier_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    company = get_current_company(db)
    delete_supplier(db, company, supplier_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()


@router.get("/collections", response_model=list[CollectionSeasonRead])
def get_collections(db: DbSession) -> list[CollectionSeasonRead]:
    company = get_current_company(db)
    return list_collections(db, company)


@router.post("/collections", response_model=CollectionSeasonRead, status_code=status.HTTP_201_CREATED)
def post_collection(payload: CollectionSeasonCreate, db: DbSession, current_user: CurrentUser) -> CollectionSeasonRead:
    company = get_current_company(db)
    collection = create_collection(db, company, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return collection


@router.put("/collections/{collection_id}", response_model=CollectionSeasonRead)
def put_collection(
    collection_id: str,
    payload: CollectionSeasonUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> CollectionSeasonRead:
    company = get_current_company(db)
    collection = update_collection(db, company, collection_id, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return collection


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_route(
    collection_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    company = get_current_company(db)
    delete_collection(db, company, collection_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()


@router.get("/purchase-plans", response_model=list[PurchasePlanRead])
def get_purchase_plans(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PurchasePlanRead]:
    company = get_current_company(db)
    return list_purchase_plans(db, company, limit=limit)


@router.post("/purchase-plans", response_model=PurchasePlanRead, status_code=status.HTTP_201_CREATED)
def post_purchase_plan(payload: PurchasePlanCreate, db: DbSession, current_user: CurrentUser) -> PurchasePlanRead:
    company = get_current_company(db)
    plan = create_purchase_plan(db, company, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return plan


@router.put("/purchase-plans/{plan_id}", response_model=PurchasePlanRead)
def put_purchase_plan(
    plan_id: str,
    payload: PurchasePlanUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> PurchasePlanRead:
    company = get_current_company(db)
    plan = update_purchase_plan(db, company, plan_id, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return plan


@router.delete("/purchase-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_plan_route(
    plan_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    company = get_current_company(db)
    delete_purchase_plan(db, company, plan_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()


@router.get("/purchase-returns", response_model=list[PurchaseReturnRead])
def get_purchase_returns(
    db: DbSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[PurchaseReturnRead]:
    company = get_current_company(db)
    return list_purchase_returns(db, company, year=year, limit=limit)


@router.post("/purchase-returns", response_model=PurchaseReturnRead, status_code=status.HTTP_201_CREATED)
def post_purchase_return(
    payload: PurchaseReturnCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> PurchaseReturnRead:
    company = get_current_company(db)
    purchase_return = create_purchase_return(db, company, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return purchase_return


@router.put("/purchase-returns/{purchase_return_id}", response_model=PurchaseReturnRead)
def put_purchase_return(
    purchase_return_id: str,
    payload: PurchaseReturnUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> PurchaseReturnRead:
    company = get_current_company(db)
    purchase_return = update_purchase_return(db, company, purchase_return_id, payload, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return purchase_return


@router.delete("/purchase-returns/{purchase_return_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_return_route(
    purchase_return_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    company = get_current_company(db)
    delete_purchase_return(db, company, purchase_return_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()


@router.post("/purchase-invoices/import-text", response_model=PurchaseInvoiceDraft)
def post_purchase_invoice_import_text(payload: PurchaseInvoiceImportTextRequest) -> PurchaseInvoiceDraft:
    return parse_purchase_invoice_text(payload.raw_text)


@router.post("/purchase-invoices/import-xml", response_model=PurchaseInvoiceDraft)
async def post_purchase_invoice_import_xml(file: UploadFile = File(...)) -> PurchaseInvoiceDraft:
    content = await file.read()
    return parse_purchase_invoice_xml(content)


@router.get("/purchase-invoices", response_model=list[PurchaseInvoiceRead])
def get_purchase_invoices(
    db: DbSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PurchaseInvoiceRead]:
    company = get_current_company(db)
    return list_purchase_invoices(db, company, year=year, limit=limit)


@router.post("/purchase-invoices", response_model=PurchaseInvoiceRead, status_code=status.HTTP_201_CREATED)
def post_purchase_invoice(payload: PurchaseInvoiceCreate, db: DbSession, current_user: CurrentUser) -> PurchaseInvoiceRead:
    company = get_current_company(db)
    source_type = "xml" if payload.raw_xml else "text"
    invoice = create_purchase_invoice(db, company, payload, current_user, source_type=source_type)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return invoice


@router.post("/purchase-invoices/linx-sync", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def post_purchase_invoice_linx_sync(
    db: DbSession,
    current_user: CurrentUser,
) -> ImportResult:
    company = get_current_company(db)
    result = sync_linx_purchase_payables(db, company, current_user)
    _invalidate_purchase_related_caches(db, company)
    return result


@router.post("/purchase-installments/{installment_id}/link-entry", response_model=PurchaseInstallmentRead)
def post_purchase_installment_link(
    installment_id: str,
    payload: PurchaseInstallmentLinkRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PurchaseInstallmentRead:
    company = get_current_company(db)
    installment = link_installment_to_entry(db, company, installment_id, payload.financial_entry_id, current_user)
    _finalize_purchase_refresh(db, company)
    db.commit()
    return installment


@router.get("/purchase-planning/overview", response_model=PurchasePlanningOverview)
def get_purchase_planning_overview(
    db: DbSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
    brand_id: str | None = Query(default=None),
    supplier_id: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    mode: str = Query(default="summary", pattern="^(summary|planning)$"),
) -> PurchasePlanningOverview:
    company = get_current_company(db)
    filters = PurchasePlanningFilters(
        year=year,
        brand_id=brand_id,
        supplier_id=supplier_id,
        collection_id=collection_id,
        status=status,
    )
    return get_cached_purchase_planning_overview(db, company, filters, mode=mode)


@router.get("/purchase-planning/cashflow", response_model=list[PurchasePlanningMonthlyProjection])
def get_purchase_planning_cashflow(
    db: DbSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
    brand_id: str | None = Query(default=None),
    supplier_id: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[PurchasePlanningMonthlyProjection]:
    company = get_current_company(db)
    filters = PurchasePlanningFilters(
        year=year,
        brand_id=brand_id,
        supplier_id=supplier_id,
        collection_id=collection_id,
        status=status,
    )
    return build_purchase_planning_cashflow(db, company, filters)

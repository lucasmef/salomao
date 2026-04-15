from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import DbSession
from app.schemas.inter import InterStatementSyncRequest
from app.schemas.imports import (
    ImportResult,
    ImportSummary,
    LinxCustomerSyncRequest,
    LinxMovementSyncRequest,
    LinxOpenReceivableSyncRequest,
    LinxProductSyncRequest,
    LinxSyncRequest,
)
from app.services.backup import ensure_pre_import_backup
from app.services.company_context import get_current_company
from app.services.data_refresh import build_data_refresh_request, finalize_data_refresh
from app.services.imports import (
    build_import_summary,
    import_historical_cashbook,
    import_linx_receivables,
    import_linx_sales,
    import_ofx,
    sync_linx_receivables,
    sync_linx_sales,
)
from app.services.linx_customers import sync_linx_customers
from app.services.linx_movements import sync_linx_movements
from app.services.linx_open_receivables import sync_linx_open_receivables
from app.services.linx_products import sync_linx_products
from app.services.inter import sync_inter_statement

router = APIRouter()


def _finalize_import_refresh(
    db: DbSession,
    company,
    *,
    source_family,
    affected_dates=None,
) -> None:
    refresh_request = build_data_refresh_request(
        source_family,
        affected_dates=affected_dates,
    )
    finalize_data_refresh(db, company, refresh_request)


@router.get("/summary", response_model=ImportSummary)
def get_import_summary(db: DbSession) -> ImportSummary:
    company = get_current_company(db)
    return build_import_summary(db, company)


@router.post("/linx-sales", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_linx_sales(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-sales")
        content = await file.read()
        result = import_linx_sales(db, company, file.filename or "linx-sales.xls", content)
        _finalize_import_refresh(db, company, source_family="sales")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/linx-sales/sync", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def trigger_linx_sales_sync(
    payload: LinxSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-sales")
        result = sync_linx_sales(
            db,
            company,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        affected_dates = [item for item in (payload.start_date, payload.end_date) if item is not None]
        _finalize_import_refresh(db, company, source_family="sales", affected_dates=affected_dates)
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/linx-receivables", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_linx_receivables(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-receivables")
        content = await file.read()
        result = import_linx_receivables(db, company, file.filename or "linx-receivables.xls", content)
        _finalize_import_refresh(db, company, source_family="receivables")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/linx-customers/sync",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def trigger_linx_customers_sync(
    payload: LinxCustomerSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-customers")
        result = sync_linx_customers(
            db,
            company,
            start_date=payload.start_date,
            end_date=payload.end_date,
            full_refresh=payload.full_refresh,
        )
        _finalize_import_refresh(db, company, source_family="customers")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/linx-products/sync",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def trigger_linx_products_sync(
    payload: LinxProductSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-products")
        result = sync_linx_products(
            db,
            company,
            full_refresh=payload.full_refresh,
        )
        _finalize_import_refresh(db, company, source_family="products")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/linx-open-receivables/sync",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def trigger_linx_open_receivables_sync(
    payload: LinxOpenReceivableSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-open-receivables")
        result = sync_linx_open_receivables(
            db,
            company,
            full_refresh=payload.full_refresh,
        )
        _finalize_import_refresh(db, company, source_family="receivables")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/linx-movements/sync",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def trigger_linx_movements_sync(
    payload: LinxMovementSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-movements")
        result = sync_linx_movements(
            db,
            company,
            full_refresh=payload.full_refresh,
        )
        _finalize_import_refresh(db, company, source_family="movements")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/linx-receivables/sync",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
def trigger_linx_receivables_sync(
    payload: LinxSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("linx-receivables")
        result = sync_linx_receivables(
            db,
            company,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        affected_dates = [item for item in (payload.start_date, payload.end_date) if item is not None]
        _finalize_import_refresh(db, company, source_family="receivables", affected_dates=affected_dates)
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ofx", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_ofx(
    db: DbSession,
    account_id: str = Form(...),
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("ofx")
        content = await file.read()
        result = import_ofx(db, company, account_id, file.filename or "extrato.ofx", content)
        _finalize_import_refresh(db, company, source_family="ofx")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/historical-cashbook",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_historical_cashbook(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        ensure_pre_import_backup("historical-cashbook")
        content = await file.read()
        result = import_historical_cashbook(
            db,
            company,
            file.filename or "livro-caixa-historico.xlsx",
            content,
        )
        _finalize_import_refresh(db, company, source_family="historical_cashbook")
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/inter/statement-sync", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def trigger_inter_statement_sync(
    payload: InterStatementSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        result = sync_inter_statement(
            db,
            company,
            account_id=payload.account_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        affected_dates = [item for item in (payload.start_date, payload.end_date) if item is not None]
        _finalize_import_refresh(
            db,
            company,
            source_family="inter_statement",
            affected_dates=affected_dates,
        )
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error

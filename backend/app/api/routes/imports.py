from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import DbSession
from app.schemas.imports import ImportResult, ImportSummary
from app.services.backup import ensure_pre_import_backup
from app.services.company_context import get_current_company
from app.services.imports import (
    build_import_summary,
    import_historical_cashbook,
    import_linx_receivables,
    import_linx_sales,
    import_ofx,
)

router = APIRouter()


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
        return import_linx_sales(db, company, file.filename or "linx-sales.xls", content)
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
        return import_linx_receivables(db, company, file.filename or "linx-receivables.xls", content)
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
        return import_ofx(db, company, account_id, file.filename or "extrato.ofx", content)
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
        return import_historical_cashbook(
            db,
            company,
            file.filename or "livro-caixa-historico.xlsx",
            content,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error

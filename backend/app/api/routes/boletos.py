from io import BytesIO

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession
from app.schemas.boletos import (
    BoletoClientConfigBulkUpdate,
    BoletoDashboardRead,
    BoletoMissingExportRequest,
    BoletoPdfBatchRequest,
)
from app.schemas.inter import InterChargeIssueRequest, InterChargeSyncRequest
from app.schemas.imports import ImportResult
from app.services.boletos import (
    build_boleto_dashboard,
    build_missing_boletos_export,
    import_boleto_customer_data,
    import_boleto_report,
    update_boleto_configs,
)
from app.services.company_context import get_current_company
from app.services.inter import (
    download_inter_charge_pdf,
    download_inter_charge_pdfs_zip,
    issue_inter_charges,
    sync_inter_charges,
)

router = APIRouter()


@router.get("/dashboard", response_model=BoletoDashboardRead)
def get_boleto_dashboard(
    db: DbSession,
    include_all_monthly_missing: bool = Query(default=False),
) -> BoletoDashboardRead:
    company = get_current_company(db)
    return build_boleto_dashboard(db, company, include_all_monthly_missing=include_all_monthly_missing)


@router.post("/missing/export")
def export_missing_boletos(
    payload: BoletoMissingExportRequest,
    db: DbSession,
) -> StreamingResponse:
    company = get_current_company(db)
    try:
        content, filename = build_missing_boletos_export(db, company, payload.selection_keys)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/clients", status_code=status.HTTP_204_NO_CONTENT)
def save_boleto_clients(
    payload: BoletoClientConfigBulkUpdate,
    db: DbSession,
) -> None:
    company = get_current_company(db)
    update_boleto_configs(db, company, payload)


@router.post("/import/inter", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_inter_boletos(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        content = await file.read()
        return import_boleto_report(
            db,
            company,
            bank="INTER",
            filename=file.filename or "relatorio-inter.xlsx",
            content=content,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/import/c6", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_c6_boletos(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        content = await file.read()
        return import_boleto_report(
            db,
            company,
            bank="C6",
            filename=file.filename or "relatorio-c6.csv",
            content=content,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/import/customer-data", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def upload_customer_data(
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResult:
    company = get_current_company(db)
    try:
        content = await file.read()
        return import_boleto_customer_data(
            db,
            company,
            filename=file.filename or "etiquetas.txt",
            content=content,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/inter/sync", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def trigger_inter_charge_sync(
    payload: InterChargeSyncRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return sync_inter_charges(
            db,
            company,
            account_id=payload.account_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/inter/issue", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def trigger_inter_issue(
    payload: InterChargeIssueRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return issue_inter_charges(
            db,
            company,
            account_id=payload.account_id,
            selection_keys=payload.selection_keys,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/inter/{boleto_id}/pdf")
def download_inter_boleto_pdf(
    boleto_id: str,
    db: DbSession,
) -> StreamingResponse:
    company = get_current_company(db)
    try:
        content, filename = download_inter_charge_pdf(db, company, boleto_id=boleto_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/inter/pdf-batch")
def download_inter_boleto_pdf_batch(
    payload: BoletoPdfBatchRequest,
    db: DbSession,
) -> StreamingResponse:
    company = get_current_company(db)
    try:
        content, filename = download_inter_charge_pdfs_zip(db, company, boleto_ids=payload.boleto_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

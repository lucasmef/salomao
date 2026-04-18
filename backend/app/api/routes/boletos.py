from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import DbSession
from app.db.models.imports import ImportBatch
from app.db.models.export_jobs import BoletoExportJob
from app.db.session import SessionLocal
from app.schemas.boletos import (
    BoletoClientConfigBulkUpdate,
    BoletoInterCancelRequest,
    BoletoInterReceiveRequest,
    BoletoDashboardRead,
    BoletoExportJobRead,
    BoletoMissingExportRequest,
    BoletoPdfBatchRequest,
    StandaloneBoletoCreateRequest,
)
from app.schemas.inter import InterChargeIssueRequest, InterChargeSyncRequest
from app.schemas.imports import ImportBatchRead, ImportResult
from app.services.boletos import (
    build_boleto_dashboard,
    build_missing_boletos_export,
    import_boleto_customer_data,
    import_boleto_report,
    update_boleto_configs,
)
from app.services.company_context import get_current_company
from app.services.inter import (
    cancel_inter_charge,
    cancel_standalone_inter_charge,
    create_standalone_inter_charge,
    download_inter_charge_pdf,
    download_inter_charge_pdfs_zip,
    download_standalone_inter_charge_pdf,
    issue_inter_charges,
    mark_standalone_boleto_downloaded,
    receive_inter_charge,
    sync_standalone_inter_charges,
    sync_inter_charges,
)
from app.services.inter_export import (
    cleanup_old_exports,
    create_export_job,
    run_export_job,
)
from app.services.linx_receivable_settlement import settle_paid_pending_inter_receivables

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
        result = import_boleto_report(
            db,
            company,
            bank="C6",
            filename=file.filename or "relatorio-c6.csv",
            content=content,
        )
        settlement_notes: list[str] = []
        try:
            settlement_summary = settle_paid_pending_inter_receivables(
                db,
                company,
                filter_banks={"C6"},
            )
            if settlement_summary.attempted_invoice_count:
                settlement_notes.append(settlement_summary.message)
            if settlement_summary.failed_invoice_count:
                settlement_notes.append("; ".join(settlement_summary.failure_messages))
            elif settlement_summary.email_error:
                settlement_notes.append(f"Resumo de baixa automatica nao enviado: {settlement_summary.email_error}")
        except Exception as error:
            settlement_notes.append(f"Baixa automatica no Linx nao executada: {error}")

        if settlement_notes:
            batch = db.get(ImportBatch, result.batch.id)
            joined_notes = " ".join(note for note in settlement_notes if note).strip()
            if batch:
                current_summary = (batch.error_summary or "").strip()
                batch.error_summary = " ".join(part for part in [current_summary, joined_notes] if part).strip() or None
                db.commit()
                db.refresh(batch)
                result.batch = ImportBatchRead.model_validate(batch)
            result.message = " ".join([result.message, joined_notes]).strip()
        return result
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


@router.post("/inter/export", response_model=BoletoExportJobRead, status_code=status.HTTP_201_CREATED)
def trigger_inter_pdf_export(
    payload: BoletoPdfBatchRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> BoletoExportJobRead:
    company = get_current_company(db)
    cleanup_old_exports()
    job = create_export_job(db, company, boleto_ids=payload.boleto_ids)
    background_tasks.add_task(
        run_export_job,
        SessionLocal,
        job.id,
        company.id,
        payload.boleto_ids,
    )
    return BoletoExportJobRead.model_validate(job)


@router.get("/inter/export/{job_id}", response_model=BoletoExportJobRead)
def get_inter_pdf_export_status(
    job_id: str,
    db: DbSession,
) -> BoletoExportJobRead:
    company = get_current_company(db)
    job = db.get(BoletoExportJob, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=404, detail="Trabalho de exportacao nao encontrado.")
    return BoletoExportJobRead.model_validate(job)


@router.get("/inter/export/{job_id}/file")
def download_inter_pdf_export_file(
    job_id: str,
    db: DbSession,
) -> FileResponse:
    company = get_current_company(db)
    job = db.get(BoletoExportJob, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=404, detail="Trabalho de exportacao nao encontrado.")
    if job.status != "completed" or not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=400, detail="Arquivo de exportacao nao disponível.")
    
    return FileResponse(
        job.file_path,
        filename=job.filename or "export.pdf",
        media_type="application/pdf" if job.filename and job.filename.endswith(".pdf") else "application/zip",
    )


@router.post("/inter/{boleto_id}/cancel", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def cancel_inter_boleto(
    boleto_id: str,
    payload: BoletoInterCancelRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return cancel_inter_charge(
            db,
            company,
            boleto_id=boleto_id,
            motivo_cancelamento=payload.motivo_cancelamento,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/inter/{boleto_id}/receive", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def receive_inter_boleto(
    boleto_id: str,
    payload: BoletoInterReceiveRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return receive_inter_charge(
            db,
            company,
            boleto_id=boleto_id,
            pagar_com=payload.pagar_com,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/standalone", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def create_standalone_boleto(
    payload: StandaloneBoletoCreateRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return create_standalone_inter_charge(
            db,
            company,
            account_id=payload.account_id,
            client_name=payload.client_name,
            amount=payload.amount,
            due_date=payload.due_date,
            notes=payload.notes,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/standalone/sync", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def sync_standalone_boletos(
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return sync_standalone_inter_charges(db, company)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/standalone/{boleto_id}/pdf")
def download_standalone_boleto_pdf(
    boleto_id: str,
    db: DbSession,
) -> StreamingResponse:
    company = get_current_company(db)
    try:
        content, filename = download_standalone_inter_charge_pdf(db, company, boleto_id=boleto_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/standalone/{boleto_id}/cancel", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def cancel_standalone_boleto(
    boleto_id: str,
    payload: BoletoInterCancelRequest,
    db: DbSession,
) -> ImportResult:
    company = get_current_company(db)
    try:
        return cancel_standalone_inter_charge(
            db,
            company,
            boleto_id=boleto_id,
            motivo_cancelamento=payload.motivo_cancelamento,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/standalone/{boleto_id}/downloaded", status_code=status.HTTP_204_NO_CONTENT)
def set_standalone_boleto_downloaded(
    boleto_id: str,
    db: DbSession,
) -> None:
    company = get_current_company(db)
    try:
        mark_standalone_boleto_downloaded(db, company, boleto_id=boleto_id)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error

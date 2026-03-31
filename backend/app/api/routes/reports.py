from datetime import date

from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DbSession
from app.schemas.reports import ReportConfig, ReportConfigUpdate, ReportsOverview
from app.services.company_context import get_current_company
from app.services.report_layouts import get_or_create_report_config, update_report_config
from app.services.report_exports import build_reports_csv, build_reports_pdf, build_reports_xls
from app.services.reports import build_reports_overview

router = APIRouter()


@router.get("/overview", response_model=ReportsOverview)
def get_reports_overview(
    db: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> ReportsOverview:
    company = get_current_company(db)
    return build_reports_overview(db, company, start=start, end=end)


@router.get("/config/{kind}", response_model=ReportConfig)
def get_report_config(
    kind: str,
    db: DbSession,
) -> ReportConfig:
    company = get_current_company(db)
    return get_or_create_report_config(db, company, kind)


@router.put("/config/{kind}", response_model=ReportConfig)
def save_report_config(
    kind: str,
    payload: ReportConfigUpdate,
    db: DbSession,
) -> ReportConfig:
    company = get_current_company(db)
    return update_report_config(db, company, kind, payload)


@router.get("/export")
def export_report(
    db: DbSession,
    kind: str = Query(default="dre", pattern="^(dre|dro)$"),
    format: str = Query(default="pdf", pattern="^(pdf|csv|xls)$"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> Response:
    company = get_current_company(db)
    report = build_reports_overview(db, company, start=start, end=end)
    filename = f"{kind}.{format}"
    if format == "csv":
        payload = build_reports_csv(report, kind)
        media_type = "text/csv"
    elif format == "xls":
        payload = build_reports_xls(report, kind)
        media_type = "application/vnd.ms-excel"
    else:
        payload = build_reports_pdf(report, kind)
        media_type = "application/pdf"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{Path(filename).name}"'},
    )

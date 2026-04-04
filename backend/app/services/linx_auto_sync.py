from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.audit import write_audit_log
from app.services.backup import ensure_pre_import_backup
from app.services.imports import sync_linx_receivables, sync_linx_sales
from app.services.security_alerts import send_email

AUTO_SYNC_TIMEZONE = ZoneInfo("America/Sao_Paulo")
AUTO_SYNC_TRIGGER_TIME = time(hour=22, minute=0)
RECEIVABLES_LOOKBACK_DAYS = 730
RECEIVABLES_LOOKAHEAD_DAYS = 365


@dataclass(frozen=True)
class LinxAutoSyncRun:
    company_id: str
    company_name: str
    status: str
    attempted: bool
    sales_message: str | None = None
    receivables_message: str | None = None
    error_message: str | None = None


def _now_in_sao_paulo(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(AUTO_SYNC_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=AUTO_SYNC_TIMEZONE)
    return now.astimezone(AUTO_SYNC_TIMEZONE)


def _split_recipients(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _month_start(target_date: date) -> date:
    return target_date.replace(day=1)


def _sales_period(target_date: date) -> tuple[date, date]:
    # Reprocess the month to date so late corrections in Linx are refreshed nightly.
    return _month_start(target_date), target_date


def _receivables_period(target_date: date) -> tuple[date, date]:
    # The receivables import replaces the current snapshot, so use a broad window
    # to keep overdue and future installments visible in the nightly refresh.
    return (
        target_date - timedelta(days=RECEIVABLES_LOOKBACK_DAYS),
        target_date + timedelta(days=RECEIVABLES_LOOKAHEAD_DAYS),
    )


def _should_run_now(company: Company, *, now: datetime, force: bool) -> tuple[bool, str]:
    if not company.linx_auto_sync_enabled and not force:
        return False, "disabled"
    if force:
        return True, "forced"
    if now.time() < AUTO_SYNC_TRIGGER_TIME:
        return False, "before-window"
    last_run_at = company.linx_auto_sync_last_run_at
    if last_run_at is None:
        return True, "first-run"
    if last_run_at.tzinfo is None:
        last_run_local = last_run_at.replace(tzinfo=AUTO_SYNC_TIMEZONE)
    else:
        last_run_local = last_run_at.astimezone(AUTO_SYNC_TIMEZONE)
    if last_run_local.date() >= now.date():
        return False, "already-ran"
    return True, "scheduled"


def _run_sales_sync(db: Session, company: Company, *, target_date: date) -> str:
    start_date, end_date = _sales_period(target_date)
    result = sync_linx_sales(db, company, start_date=start_date, end_date=end_date)
    return result.message


def _run_receivables_sync(db: Session, company: Company, *, target_date: date) -> str:
    start_date, end_date = _receivables_period(target_date)
    result = sync_linx_receivables(db, company, start_date=start_date, end_date=end_date)
    return result.message


def _build_failure_email(
    company: Company,
    *,
    attempted_at: datetime,
    error_message: str,
) -> tuple[str, str]:
    subject = f"[Linx] Falha na sincronizacao automatica - {company.trade_name}"
    body = "\n".join(
        [
            f"Empresa: {company.trade_name}",
            f"Data/hora: {attempted_at.strftime('%d/%m/%Y %H:%M:%S %Z')}",
            "Origem: sincronizacao automatica diaria do Linx",
            "",
            "Resumo da falha:",
            error_message,
            "",
            "Possiveis causas:",
            "- senha do Linx expirada ou alterada",
            "- visao do relatorio alterada no Microvix",
            "- indisponibilidade temporaria do portal",
        ]
    )
    return subject, body


def run_linx_auto_sync_for_company(
    db: Session,
    company: Company,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> LinxAutoSyncRun:
    local_now = _now_in_sao_paulo(now)
    should_run, reason = _should_run_now(company, now=local_now, force=force)
    company_name = company.trade_name or company.legal_name or company.id

    if not should_run:
        return LinxAutoSyncRun(
            company_id=company.id,
            company_name=company_name,
            status=reason,
            attempted=False,
        )

    target_date = local_now.date()
    errors: list[str] = []
    sales_message: str | None = None
    receivables_message: str | None = None

    try:
        ensure_pre_import_backup(f"linx-auto-sync:{company.id}")
    except Exception as error:  # pragma: no cover - safeguard for operational environment
        db.rollback()
        errors.append(f"Preparacao do backup: {error}")
    else:
        try:
            sales_message = _run_sales_sync(db, company, target_date=target_date)
        except Exception as error:  # pragma: no cover - exercised via service tests
            db.rollback()
            errors.append(f"Faturamento: {error}")

        try:
            receivables_message = _run_receivables_sync(db, company, target_date=target_date)
        except Exception as error:  # pragma: no cover - exercised via service tests
            db.rollback()
            errors.append(f"Faturas a receber: {error}")

    if errors:
        status = "partial_failure" if sales_message or receivables_message else "failed"
        error_message = "\n".join(errors)
    else:
        status = "success"
        error_message = None

    company.linx_auto_sync_last_run_at = local_now
    company.linx_auto_sync_last_status = status
    company.linx_auto_sync_last_error = error_message
    db.flush()
    write_audit_log(
        db,
        action="linx_auto_sync_run",
        entity_name="company",
        entity_id=company.id,
        company_id=company.id,
        after_state={
            "trigger": reason,
            "status": status,
            "sales_message": sales_message,
            "receivables_message": receivables_message,
            "error_message": error_message,
        },
    )
    db.commit()

    if error_message:
        subject, body = _build_failure_email(
            company,
            attempted_at=local_now,
            error_message=error_message,
        )
        try:
            send_email(
                subject,
                body,
                recipients=_split_recipients(company.linx_auto_sync_alert_email),
            )
        except Exception as email_error:  # pragma: no cover - depends on SMTP runtime
            company.linx_auto_sync_last_error = (
                f"{error_message}\nAlerta por email nao enviado: {email_error}"
            )
            db.flush()
            db.commit()
            error_message = company.linx_auto_sync_last_error

    return LinxAutoSyncRun(
        company_id=company.id,
        company_name=company_name,
        status=status,
        attempted=True,
        sales_message=sales_message,
        receivables_message=receivables_message,
        error_message=error_message,
    )


def run_linx_auto_sync_cycle(
    db: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> list[LinxAutoSyncRun]:
    statement = select(Company).where(Company.is_active.is_(True))
    if not force:
        statement = statement.where(Company.linx_auto_sync_enabled.is_(True))
    statement = statement.order_by(Company.trade_name.asc(), Company.legal_name.asc())
    companies = list(db.scalars(statement))
    return [
        run_linx_auto_sync_for_company(db, company, now=now, force=force)
        for company in companies
    ]

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxMovement
from app.db.models.security import Company
from app.services.audit import write_audit_log
from app.services.backup import ensure_pre_import_backup
from app.services.linx_customers import sync_linx_customers
from app.services.linx_movements import sync_linx_movements
from app.services.linx_open_receivables import sync_linx_open_receivables
from app.services.linx_products import LINX_PRODUCTS_SOURCE, sync_linx_products
from app.services.purchase_planning import LINX_PURCHASE_PAYABLES_API_SOURCE, sync_linx_purchase_payables
from app.services.security_alerts import send_email

AUTO_SYNC_TIMEZONE = ZoneInfo("America/Sao_Paulo")
AUTO_SYNC_WINDOW_START_TIME = time(hour=6, minute=0)
AUTO_SYNC_WINDOW_END_HOUR = 22
PRODUCTS_SYNC_START_HOUR = 7


@dataclass(frozen=True)
class LinxAutoSyncSummary:
    customers_changed_count: int = 0
    receivables_changed_count: int = 0
    movements_changed_count: int = 0
    products_changed_count: int = 0
    purchase_payables_changed_count: int = 0


@dataclass(frozen=True)
class LinxAutoSyncRun:
    company_id: str
    company_name: str
    status: str
    attempted: bool
    customers_message: str | None = None
    receivables_message: str | None = None
    movements_message: str | None = None
    products_message: str | None = None
    purchase_payables_message: str | None = None
    summary: LinxAutoSyncSummary = LinxAutoSyncSummary()
    error_message: str | None = None


def _now_in_sao_paulo(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(AUTO_SYNC_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=AUTO_SYNC_TIMEZONE)
    return now.astimezone(AUTO_SYNC_TIMEZONE)


def _split_recipients(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _should_run_now(company: Company, *, now: datetime, force: bool) -> tuple[bool, str]:
    if not company.linx_auto_sync_enabled and not force:
        return False, "disabled"
    if force:
        return True, "forced"
    if now.time() < AUTO_SYNC_WINDOW_START_TIME:
        return False, "before-window"
    if now.hour > AUTO_SYNC_WINDOW_END_HOUR:
        return False, "after-window"

    current_slot = now.replace(minute=0, second=0, microsecond=0)
    last_run_at = company.linx_auto_sync_last_run_at
    if last_run_at is None:
        return True, "first-run"
    if last_run_at.tzinfo is None:
        last_run_local = last_run_at.replace(tzinfo=AUTO_SYNC_TIMEZONE)
    else:
        last_run_local = last_run_at.astimezone(AUTO_SYNC_TIMEZONE)
    last_slot = last_run_local.replace(minute=0, second=0, microsecond=0)
    if last_slot >= current_slot:
        return False, "already-ran"
    return True, "scheduled"


def _local_day_range_utc(now: datetime) -> tuple[datetime, datetime]:
    day_start_local = datetime.combine(now.date(), time.min, tzinfo=AUTO_SYNC_TIMEZONE)
    next_day_local = day_start_local + timedelta(days=1)
    return day_start_local.astimezone(timezone.utc), next_day_local.astimezone(timezone.utc)


def _has_processed_batch_today(
    db: Session,
    *,
    company_id: str,
    source_type: str,
    now: datetime,
) -> bool:
    start_utc, end_utc = _local_day_range_utc(now)
    return bool(
        db.scalar(
            select(ImportBatch.id)
            .where(
                ImportBatch.company_id == company_id,
                ImportBatch.source_type == source_type,
                ImportBatch.status == "processed",
                ImportBatch.created_at >= start_utc,
                ImportBatch.created_at < end_utc,
            )
            .limit(1)
        )
    )


def _should_run_products_now(
    db: Session,
    company: Company,
    *,
    now: datetime,
    force: bool,
    purchase_activity_found: bool,
) -> bool:
    if force or purchase_activity_found:
        return True
    if now.hour < PRODUCTS_SYNC_START_HOUR:
        return False
    return not _has_processed_batch_today(
        db,
        company_id=company.id,
        source_type=LINX_PRODUCTS_SOURCE,
        now=now,
    )


def _count_touched_purchase_movements(db: Session, *, company_id: str, batch_id: str | None) -> int:
    if not batch_id:
        return 0
    return int(
        db.scalar(
            select(func.count())
            .select_from(LinxMovement)
            .where(
                LinxMovement.company_id == company_id,
                LinxMovement.last_seen_batch_id == batch_id,
                LinxMovement.movement_type == "purchase",
            )
        )
        or 0
    )


def _should_run_purchase_payables_now(
    db: Session,
    company: Company,
    *,
    now: datetime,
    force: bool,
    purchase_activity_found: bool,
) -> bool:
    if force or purchase_activity_found:
        return True
    if now.hour < PRODUCTS_SYNC_START_HOUR:
        return False
    return not _has_processed_batch_today(
        db,
        company_id=company.id,
        source_type=LINX_PURCHASE_PAYABLES_API_SOURCE,
        now=now,
    )


def _extract_count(message: str | None, pattern: str) -> int:
    if not message:
        return 0
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if match is None:
        return 0
    return int(match.group(1))


def _build_summary(
    *,
    customers_message: str | None,
    receivables_message: str | None,
    movements_message: str | None,
    products_message: str | None,
    purchase_payables_message: str | None,
) -> LinxAutoSyncSummary:
    return LinxAutoSyncSummary(
        customers_changed_count=(
            _extract_count(customers_message, r"(\d+)\s+novo\(s\)")
            + _extract_count(customers_message, r"(\d+)\s+atualizado\(s\)")
        ),
        receivables_changed_count=(
            _extract_count(receivables_message, r"(\d+)\s+nova\(s\)")
            + _extract_count(receivables_message, r"(\d+)\s+atualizada\(s\)")
            + _extract_count(receivables_message, r"(\d+)\s+removida\(s\)")
        ),
        movements_changed_count=(
            _extract_count(movements_message, r"(\d+)\s+novo\(s\)")
            + _extract_count(movements_message, r"(\d+)\s+atualizado\(s\)")
            + _extract_count(movements_message, r"(\d+)\s+removido\(s\)")
        ),
        products_changed_count=(
            _extract_count(products_message, r"(\d+)\s+novo\(s\)")
            + _extract_count(products_message, r"(\d+)\s+atualizado\(s\)")
        ),
        purchase_payables_changed_count=(
            _extract_count(purchase_payables_message, r"(\d+)\s+fatura\(s\)\s+nova\(s\)\s+inclu")
            + _extract_count(purchase_payables_message, r"(\d+)\s+titulo\(s\)")
        ),
    )


def _build_error_email(
    company: Company,
    *,
    attempted_at: datetime,
    status: str,
    summary: LinxAutoSyncSummary,
    customers_message: str | None,
    receivables_message: str | None,
    movements_message: str | None,
    products_message: str | None,
    purchase_payables_message: str | None,
    error_message: str,
) -> tuple[str, str]:
    company_name = company.trade_name or company.legal_name or company.id
    subject = f"[Linx] Falha na sincronizacao automatica - {company_name}"
    body = "\n".join(
        [
            f"Empresa: {company_name}",
            f"Data/hora: {attempted_at.strftime('%d/%m/%Y %H:%M:%S %Z')}",
            "Origem: sincronizacao automatica horaria via API",
            f"Status: {status}",
            "",
            "Resumo parcial:",
            f"- Clientes/fornecedores alterados: {summary.customers_changed_count}",
            f"- Faturas a receber alteradas: {summary.receivables_changed_count}",
            f"- Movimentos alterados: {summary.movements_changed_count}",
            f"- Produtos alterados: {summary.products_changed_count}",
            f"- Faturas de compra alteradas: {summary.purchase_payables_changed_count}",
            "",
            "Detalhes dos retornos:",
            f"- Clientes/fornecedores: {customers_message or 'nao executado'}",
            f"- Faturas a receber: {receivables_message or 'nao executado'}",
            f"- Movimentos: {movements_message or 'nao executado'}",
            f"- Produtos: {products_message or 'nao executado'}",
            f"- Faturas de compra: {purchase_payables_message or 'nao executado'}",
            "",
            "Falhas encontradas:",
            error_message,
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

    errors: list[str] = []
    customers_message: str | None = None
    receivables_message: str | None = None
    movements_message: str | None = None
    products_message: str | None = None
    purchase_payables_message: str | None = None

    try:
        ensure_pre_import_backup(f"linx-auto-sync:{company.id}")
    except Exception as error:  # pragma: no cover
        db.rollback()
        errors.append(f"Preparacao do backup: {error}")
    else:
        try:
            customers_result = sync_linx_customers(db, company)
            customers_message = customers_result.message
        except Exception as error:  # pragma: no cover
            db.rollback()
            errors.append(f"Clientes/fornecedores: {error}")

        purchase_activity_found = False
        try:
            movements_result = sync_linx_movements(db, company)
            movements_message = movements_result.message
            purchase_activity_found = _count_touched_purchase_movements(
                db,
                company_id=company.id,
                batch_id=getattr(movements_result.batch, "id", None),
            ) > 0
        except Exception as error:  # pragma: no cover
            db.rollback()
            errors.append(f"Movimentos: {error}")

        if _should_run_products_now(
            db,
            company,
            now=local_now,
            force=force,
            purchase_activity_found=purchase_activity_found,
        ):
            try:
                products_result = sync_linx_products(db, company)
                products_message = products_result.message
            except Exception as error:  # pragma: no cover
                db.rollback()
                errors.append(f"Produtos: {error}")

        try:
            receivables_result = sync_linx_open_receivables(db, company)
            receivables_message = receivables_result.message
        except Exception as error:  # pragma: no cover
            db.rollback()
            errors.append(f"Faturas a receber: {error}")

        if _should_run_purchase_payables_now(
            db,
            company,
            now=local_now,
            force=force,
            purchase_activity_found=purchase_activity_found,
        ):
            try:
                purchase_payables_result = sync_linx_purchase_payables(db, company, actor_user=None)
                purchase_payables_message = purchase_payables_result.message
            except Exception as error:  # pragma: no cover
                db.rollback()
                errors.append(f"Faturas de compra: {error}")

    summary = _build_summary(
        customers_message=customers_message,
        receivables_message=receivables_message,
        movements_message=movements_message,
        products_message=products_message,
        purchase_payables_message=purchase_payables_message,
    )

    if errors:
        if any(message for message in (customers_message, receivables_message, movements_message, products_message, purchase_payables_message)):
            status = "partial_failure"
        else:
            status = "failed"
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
            "customers_message": customers_message,
            "receivables_message": receivables_message,
            "movements_message": movements_message,
            "products_message": products_message,
            "purchase_payables_message": purchase_payables_message,
            "summary": {
                "customers_changed_count": summary.customers_changed_count,
                "receivables_changed_count": summary.receivables_changed_count,
                "movements_changed_count": summary.movements_changed_count,
                "products_changed_count": summary.products_changed_count,
                "purchase_payables_changed_count": summary.purchase_payables_changed_count,
            },
            "error_message": error_message,
        },
    )
    db.commit()

    if error_message:
        try:
            subject, body = _build_error_email(
                company,
                attempted_at=local_now,
                status=status,
                summary=summary,
                customers_message=customers_message,
                receivables_message=receivables_message,
                movements_message=movements_message,
                products_message=products_message,
                purchase_payables_message=purchase_payables_message,
                error_message=error_message,
            )
            send_email(
                subject,
                body,
                recipients=_split_recipients(company.linx_auto_sync_alert_email),
            )
        except Exception as email_error:  # pragma: no cover
            email_delivery_error = f"Resumo por email nao enviado: {email_error}"
            company.linx_auto_sync_last_error = (
                f"{error_message}\n{email_delivery_error}" if error_message else email_delivery_error
            )
            db.flush()
            db.commit()
            error_message = company.linx_auto_sync_last_error

    return LinxAutoSyncRun(
        company_id=company.id,
        company_name=company_name,
        status=status,
        attempted=True,
        customers_message=customers_message,
        receivables_message=receivables_message,
        movements_message=movements_message,
        products_message=products_message,
        purchase_payables_message=purchase_payables_message,
        summary=summary,
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

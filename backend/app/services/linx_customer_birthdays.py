from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import and_, extract, func, select
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.db.models.linx import LinxCustomer, LinxMovement
from app.db.models.security import Company
from app.services.audit import write_audit_log
from app.services.security_alerts import ensure_email_transport_configured, send_email

BIRTHDAY_ALERT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
BIRTHDAY_ALERT_START_TIME = time(hour=9, minute=0)
RECENT_PURCHASE_LOOKBACK_YEARS = 2


@dataclass(frozen=True)
class BirthdayCustomerAlertItem:
    linx_code: int
    customer_name: str
    birth_date: date
    last_purchase_at: datetime


def _now_in_sao_paulo(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(BIRTHDAY_ALERT_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=BIRTHDAY_ALERT_TIMEZONE)
    return now.astimezone(BIRTHDAY_ALERT_TIMEZONE)


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year - years)


def _split_recipients(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _should_send_alert_now(company: Company, *, now: datetime, force: bool) -> bool:
    if not force and now.time() < BIRTHDAY_ALERT_START_TIME:
        return False
    last_sent_at = company.linx_birthday_alert_last_sent_at
    if last_sent_at is None:
        return True
    if last_sent_at.tzinfo is None:
        last_sent_local = last_sent_at.replace(tzinfo=BIRTHDAY_ALERT_TIMEZONE)
    else:
        last_sent_local = last_sent_at.astimezone(BIRTHDAY_ALERT_TIMEZONE)
    return last_sent_local.date() < now.date()


def list_birthday_customers_for_date(
    db: Session,
    company: Company,
    *,
    target_date: date,
) -> list[BirthdayCustomerAlertItem]:
    purchase_datetime = func.coalesce(LinxMovement.issue_date, LinxMovement.launch_date)
    cutoff_date = _subtract_years(target_date, RECENT_PURCHASE_LOOKBACK_YEARS)
    cutoff_datetime = datetime.combine(cutoff_date, time.min)

    rows = db.execute(
        select(
            LinxCustomer.linx_code,
            LinxCustomer.legal_name,
            LinxCustomer.display_name,
            LinxCustomer.birth_date,
            func.max(purchase_datetime).label("last_purchase_at"),
        )
        .join(
            LinxMovement,
            and_(
                LinxMovement.company_id == LinxCustomer.company_id,
                LinxMovement.customer_code == LinxCustomer.linx_code,
            ),
        )
        .where(
            LinxCustomer.company_id == company.id,
            LinxCustomer.birth_date.is_not(None),
            LinxCustomer.is_active.is_(True),
            LinxCustomer.anonymous_customer.is_(False),
            LinxCustomer.registration_type.in_(("C", "A")),
            extract("month", LinxCustomer.birth_date) == target_date.month,
            extract("day", LinxCustomer.birth_date) == target_date.day,
            LinxMovement.movement_type == "sale",
            purchase_datetime >= cutoff_datetime,
        )
        .group_by(
            LinxCustomer.linx_code,
            LinxCustomer.legal_name,
            LinxCustomer.display_name,
            LinxCustomer.birth_date,
        )
        .order_by(func.lower(LinxCustomer.legal_name).asc(), LinxCustomer.linx_code.asc())
    ).all()

    items: list[BirthdayCustomerAlertItem] = []
    for linx_code, legal_name, display_name, birth_date, last_purchase_at in rows:
        if birth_date is None or last_purchase_at is None:
            continue
        items.append(
            BirthdayCustomerAlertItem(
                linx_code=int(linx_code),
                customer_name=(display_name or legal_name).strip(),
                birth_date=birth_date,
                last_purchase_at=last_purchase_at,
            )
        )
    return items


def send_linx_customer_birthday_alert(
    db: Session,
    company: Company,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> str | None:
    local_now = _now_in_sao_paulo(now)
    if not _should_send_alert_now(company, now=local_now, force=force):
        return None

    customers = list_birthday_customers_for_date(db, company, target_date=local_now.date())
    if not customers:
        return None

    settings = get_settings()
    recipients = _split_recipients(company.linx_auto_sync_alert_email) or settings.security_alert_recipients
    ensure_email_transport_configured()

    company_name = company.trade_name or company.legal_name or company.id
    subject = f"[Linx] Aniversariantes do dia - {company_name}"
    customer_lines = [
        (
            f"- {item.customer_name} (codigo Linx {item.linx_code}, "
            f"nascimento {item.birth_date.strftime('%d/%m')}, "
            f"ultima compra {item.last_purchase_at.strftime('%d/%m/%Y')})"
        )
        for item in customers
    ]
    body = "\n".join(
        [
            f"Empresa: {company_name}",
            f"Data: {local_now.strftime('%d/%m/%Y')}",
            "",
            f"Clientes aniversariantes com compra nos ultimos {RECENT_PURCHASE_LOOKBACK_YEARS} anos:",
            *customer_lines,
        ]
    )
    send_email(subject, body, recipients=recipients)

    company.linx_birthday_alert_last_sent_at = local_now
    db.flush()
    write_audit_log(
        db,
        action="linx_customer_birthday_alert_sent",
        entity_name="company",
        entity_id=company.id,
        company_id=company.id,
        after_state={
            "alert_date": local_now.date().isoformat(),
            "customer_count": len(customers),
            "recipients": recipients,
            "customers": [
                {
                    "linx_code": item.linx_code,
                    "customer_name": item.customer_name,
                    "birth_date": item.birth_date.isoformat(),
                    "last_purchase_at": item.last_purchase_at.isoformat(),
                }
                for item in customers
            ],
        },
    )
    return f"Alerta de aniversariantes enviado com sucesso. {len(customers)} cliente(s) elegivel(is)."

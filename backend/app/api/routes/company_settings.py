import smtplib

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, require_role
from app.schemas.company_settings import LinxSettingsRead, LinxSettingsUpdate
from app.schemas.smtp import SmtpSettingsRead, SmtpSettingsUpdate, SmtpTestRequest
from app.services.audit import write_audit_log
from app.services.company_context import get_current_company
from app.services.linx import apply_linx_settings, serialize_linx_settings
from app.services.smtp_settings import (
    configuration_from_payload,
    read_configuration,
    save_configuration,
    send_test_email,
    serialize_configuration,
    smtp_error_message,
)

router = APIRouter()


@router.get("/smtp", response_model=SmtpSettingsRead)
def get_smtp_settings(db: DbSession, current_user: CurrentUser) -> SmtpSettingsRead:
    require_role(current_user, {"admin"})
    return serialize_configuration(read_configuration(db))


@router.put("/smtp", response_model=SmtpSettingsRead)
def update_smtp_settings(
    payload: SmtpSettingsUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> SmtpSettingsRead:
    require_role(current_user, {"admin"})
    before = serialize_configuration(read_configuration(db))
    try:
        config = configuration_from_payload(db, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    save_configuration(db, config)
    after = serialize_configuration(config)
    write_audit_log(
        db,
        action="update_system_smtp_settings",
        entity_name="system_email_settings",
        entity_id="1",
        company_id=current_user.company_id,
        actor_user=current_user,
        before_state=before.model_dump(),
        after_state=after.model_dump(),
    )
    db.commit()
    return after


@router.post("/smtp/test")
def test_smtp_settings(
    payload: SmtpTestRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, str]:
    require_role(current_user, {"admin"})
    try:
        config = configuration_from_payload(db, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        send_test_email(config, payload.recipient)
    except (smtplib.SMTPException, OSError) as error:
        raise HTTPException(status_code=400, detail=smtp_error_message(error)) from error
    return {"message": "E-mail de teste aceito pelo servidor SMTP. Confira a caixa de entrada."}


@router.get("/linx", response_model=LinxSettingsRead)
def get_linx_settings(
    db: DbSession,
    current_user: CurrentUser,
) -> LinxSettingsRead:
    require_role(current_user, {"admin"})
    company = get_current_company(db)
    return serialize_linx_settings(company)


@router.put("/linx", response_model=LinxSettingsRead)
def update_linx_settings(
    payload: LinxSettingsUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> LinxSettingsRead:
    require_role(current_user, {"admin"})
    company = get_current_company(db)
    before_state = serialize_linx_settings(company)
    apply_linx_settings(company, payload)
    db.flush()
    after_state = serialize_linx_settings(company)
    write_audit_log(
        db,
        action="update_company_linx_settings",
        entity_name="company",
        entity_id=company.id,
        company_id=company.id,
        actor_user=current_user,
        before_state=before_state.model_dump(),
        after_state=after_state.model_dump(),
    )
    db.commit()
    return after_state

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, require_role
from app.schemas.company_settings import LinxSettingsRead, LinxSettingsUpdate
from app.services.audit import write_audit_log
from app.services.company_context import get_current_company
from app.services.linx import apply_linx_settings, serialize_linx_settings

router = APIRouter()


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

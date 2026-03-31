from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.recurrence import (
    RecurrenceGenerationRequest,
    RecurrenceRuleCreate,
    RecurrenceRuleRead,
    RecurrenceRuleUpdate,
)
from app.services.company_context import get_current_company
from app.services.finance_ops import (
    create_recurrence_rule,
    generate_recurrence_entries,
    list_recurrence_rules,
    update_recurrence_rule,
)

router = APIRouter()


@router.get("", response_model=list[RecurrenceRuleRead])
def get_recurrences(db: DbSession) -> list[RecurrenceRuleRead]:
    company = get_current_company(db)
    return [RecurrenceRuleRead.model_validate(item) for item in list_recurrence_rules(db, company)]


@router.post("", response_model=RecurrenceRuleRead, status_code=status.HTTP_201_CREATED)
def post_recurrence(
    payload: RecurrenceRuleCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> RecurrenceRuleRead:
    company = get_current_company(db)
    rule = create_recurrence_rule(db, company, payload, current_user)
    db.commit()
    db.refresh(rule)
    return RecurrenceRuleRead.model_validate(rule)


@router.put("/{rule_id}", response_model=RecurrenceRuleRead)
def put_recurrence(
    rule_id: str,
    payload: RecurrenceRuleUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> RecurrenceRuleRead:
    company = get_current_company(db)
    rule = update_recurrence_rule(db, company, rule_id, payload, current_user)
    db.commit()
    db.refresh(rule)
    return RecurrenceRuleRead.model_validate(rule)


@router.post("/generate", response_model=dict[str, int])
def post_recurrence_generation(
    payload: RecurrenceGenerationRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, int]:
    company = get_current_company(db)
    generated = generate_recurrence_entries(db, company, payload, current_user)
    db.commit()
    return {"generated": generated}

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.db.models.finance import Category, FinancialEntry
from app.schemas.category import (
    CategoryCreate,
    CategoryGroupOption,
    CategoryLookups,
    CategoryRead,
    CategorySubgroupOption,
)
from app.services.audit import write_audit_log
from app.services.company_context import get_current_company

router = APIRouter()


def _normalize_payload(payload: CategoryCreate) -> CategoryCreate:
    report_group = payload.report_group.strip() if payload.report_group else None
    report_subgroup = payload.report_subgroup.strip() if payload.report_subgroup else None
    if not report_group and report_subgroup:
        report_group = report_subgroup
    if report_subgroup == report_group:
        report_subgroup = None
    return payload.model_copy(update={"report_group": report_group, "report_subgroup": report_subgroup})


@router.get("/lookups", response_model=CategoryLookups)
def get_category_lookups(db: DbSession) -> CategoryLookups:
    company = get_current_company(db)
    group_options: dict[tuple[str, str], CategoryGroupOption] = {}
    subgroup_options: dict[tuple[str, str, str], CategorySubgroupOption] = {}
    for category in db.scalars(
        select(Category).where(
            Category.company_id == company.id,
            Category.is_active.is_(True),
            Category.report_group.is_not(None),
        )
    ):
        group_name = category.report_group or "Sem Grupo"
        group_options[(group_name, category.entry_kind)] = CategoryGroupOption(
            name=group_name,
            entry_kind=category.entry_kind,
        )
        subgroup_name = (category.report_subgroup or "").strip()
        if subgroup_name:
            subgroup_options[(group_name, subgroup_name, category.entry_kind)] = CategorySubgroupOption(
                name=subgroup_name,
                entry_kind=category.entry_kind,
                report_group=group_name,
            )
    return CategoryLookups(
        group_options=sorted(group_options.values(), key=lambda item: (item.entry_kind, item.name)),
        subgroup_options=sorted(
            subgroup_options.values(),
            key=lambda item: (item.entry_kind, item.report_group, item.name),
        ),
    )


@router.get("", response_model=list[CategoryRead])
def list_categories(db: DbSession) -> list[CategoryRead]:
    company = get_current_company(db)
    categories = list(
        db.scalars(
            select(Category)
            .where(
                Category.company_id == company.id,
                Category.is_active.is_(True),
            )
            .order_by(
                Category.entry_kind.asc(),
                Category.report_group.asc(),
                Category.report_subgroup.asc(),
                Category.code.asc(),
                Category.name.asc(),
            )
        )
    )
    category_ids = [category.id for category in categories]
    entry_counts = (
        {
            category_id: entry_count
            for category_id, entry_count in db.execute(
                select(
                    FinancialEntry.category_id,
                    func.count(FinancialEntry.id),
                )
                .where(
                    FinancialEntry.company_id == company.id,
                    FinancialEntry.is_deleted.is_(False),
                    FinancialEntry.category_id.is_not(None),
                    FinancialEntry.category_id.in_(category_ids),
                )
                .group_by(FinancialEntry.category_id)
            )
        }
        if category_ids
        else {}
    )
    return [
        CategoryRead.model_validate(category, from_attributes=True).model_copy(
            update={"entry_count": int(entry_counts.get(category.id, 0))}
        )
        for category in categories
    ]


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DbSession, current_user: CurrentUser) -> Category:
    company = get_current_company(db)
    normalized_payload = _normalize_payload(payload)
    category = Category(
        company_id=company.id,
        **normalized_payload.model_dump(),
    )
    db.add(category)
    db.flush()
    write_audit_log(
        db,
        action="create_category",
        entity_name="category",
        entity_id=category.id,
        company_id=company.id,
        actor_user=current_user,
        after_state={
            "name": category.name,
            "report_group": category.report_group,
            "report_subgroup": category.report_subgroup,
        },
    )
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: str,
    payload: CategoryCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Category:
    company = get_current_company(db)
    category = db.get(Category, category_id)
    if not category or category.company_id != company.id:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    normalized_payload = _normalize_payload(payload)
    before_state = {
        "name": category.name,
        "report_group": category.report_group,
        "report_subgroup": category.report_subgroup,
        "is_active": category.is_active,
    }
    for field_name, value in normalized_payload.model_dump().items():
        setattr(category, field_name, value)
    db.flush()
    write_audit_log(
        db,
        action="update_category",
        entity_name="category",
        entity_id=category.id,
        company_id=company.id,
        actor_user=current_user,
        before_state=before_state,
        after_state={
            "name": category.name,
            "report_group": category.report_group,
            "report_subgroup": category.report_subgroup,
            "is_active": category.is_active,
        },
    )
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: str, db: DbSession, current_user: CurrentUser) -> None:
    company = get_current_company(db)
    category = db.get(Category, category_id)
    if not category or category.company_id != company.id:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    if not category.is_active:
        db.commit()
        return

    before_state = {
        "name": category.name,
        "report_group": category.report_group,
        "report_subgroup": category.report_subgroup,
        "is_active": category.is_active,
    }
    category.is_active = False
    db.flush()
    write_audit_log(
        db,
        action="delete_category",
        entity_name="category",
        entity_id=category.id,
        company_id=company.id,
        actor_user=current_user,
        before_state=before_state,
        after_state={
            "name": category.name,
            "report_group": category.report_group,
            "report_subgroup": category.report_subgroup,
            "is_active": category.is_active,
        },
    )
    db.commit()

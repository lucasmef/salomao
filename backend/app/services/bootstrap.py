from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.auth import ensure_default_admin
from app.services.category_catalog import (
    deactivate_legacy_categories,
    ensure_category_catalog,
    ensure_default_financial_category,
)
from app.services.imports import cleanup_open_linx_sales_entries, deactivate_electronic_receivables_account
from app.services.purchase_planning import assign_historical_purchase_collections, ensure_historical_purchase_collections

DEFAULT_COMPANY_NAME = "Empresa Principal"


def ensure_default_company(db: Session) -> Company:
    company = db.scalar(select(Company).order_by(Company.created_at.asc()))
    if company:
        return company

    company = Company(
        legal_name=DEFAULT_COMPANY_NAME,
        trade_name=DEFAULT_COMPANY_NAME,
        default_currency="BRL",
    )
    db.add(company)
    db.flush()
    ensure_category_catalog(db, company.id)
    ensure_default_financial_category(db, company.id)
    ensure_default_admin(db, company)
    db.commit()
    db.refresh(company)
    return company


def ensure_company_catalog(db: Session, company_id: str) -> None:
    # Startup must not mutate business data automatically. Baseline catalog
    # creation happens only when the company is first created.
    _ = (db, company_id)


def run_company_data_maintenance(db: Session, company_id: str) -> None:
    company = db.get(Company, company_id)
    if company is not None:
        ensure_historical_purchase_collections(db, company)
        assign_historical_purchase_collections(db, company)
    ensure_category_catalog(db, company_id)
    ensure_default_financial_category(db, company_id)
    deactivate_legacy_categories(db, company_id)
    cleanup_open_linx_sales_entries(db, company_id)
    deactivate_electronic_receivables_account(db, company_id)
    db.flush()


def ensure_company_security(db: Session, company: Company) -> None:
    ensure_default_admin(db, company)
    db.flush()

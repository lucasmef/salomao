from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.banking import BankTransaction
from app.db.models.finance import Account, FinancialEntry
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxOpenReceivable, SalesSnapshot
from app.db.models.security import Company
from app.services.category_catalog import ensure_category_catalog
from app.services.local_demo_seed import LOCAL_DEMO_SOURCE, seed_local_demo_data


def _build_session() -> tuple[Session, Company]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    company = Company(legal_name="Empresa Demo Ltda", trade_name="Empresa Demo")
    session.add(company)
    session.flush()
    ensure_category_catalog(session, company.id)
    session.flush()
    return session, company


def test_seed_local_demo_data_creates_useful_fake_records() -> None:
    session, company = _build_session()

    summary = seed_local_demo_data(session, company)
    session.commit()

    assert summary["financial_entries"] == 10
    assert session.scalar(select(Account).where(Account.name == "Conta Corrente Demo")) is not None
    assert session.scalar(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.source_system == LOCAL_DEMO_SOURCE,
        )
    ) is not None
    assert session.scalar(select(SalesSnapshot)) is not None
    assert session.scalar(select(LinxOpenReceivable)) is not None
    assert session.scalar(select(BankTransaction)) is not None
    assert session.scalar(
        select(ImportBatch).where(ImportBatch.source_type == "linx_receivables")
    ) is not None


def test_seed_local_demo_data_is_idempotent_with_reset() -> None:
    session, company = _build_session()

    seed_local_demo_data(session, company)
    seed_local_demo_data(session, company)
    session.commit()

    financial_entries_count = session.query(FinancialEntry).filter(
        FinancialEntry.company_id == company.id,
        FinancialEntry.source_system == LOCAL_DEMO_SOURCE,
    ).count()
    batch_count = session.query(ImportBatch).filter(
        ImportBatch.company_id == company.id,
        ImportBatch.fingerprint.like("local-demo-seed:%"),
    ).count()

    assert financial_entries_count == 10
    assert batch_count == 5

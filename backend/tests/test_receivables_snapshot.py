from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxOpenReceivable, ReceivableTitle
from app.db.models.security import Company
from app.services.boletos import build_boleto_dashboard
from app.services.cashflow import build_cashflow_overview
from app.services.imports import import_linx_receivables
from app.services.import_parsers import ParsedReceivableRow


def _build_session() -> tuple[Session, Company]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste")
    session.add(company)
    session.commit()
    session.refresh(company)
    return session, company


def test_receivables_snapshot_overwrites_dashboard_and_cashflow(monkeypatch) -> None:
    session, company = _build_session()

    first_snapshot = [
        ParsedReceivableRow(
            issue_date=date(2026, 4, 1),
            due_date=date(2026, 4, 6),
            invoice_number="56707",
            company_code="1",
            installment_label="1",
            original_amount=Decimal("1000.00"),
            amount_with_interest=Decimal("1000.00"),
            customer_name="SORAIA PETERS FORMENTIN",
            document_reference=None,
            status="Em aberto",
            seller_name=None,
        )
    ]
    empty_snapshot: list[ParsedReceivableRow] = []
    parse_queue = [first_snapshot, empty_snapshot]

    monkeypatch.setattr(
        "app.services.imports.prepare_linx_receivables_payload",
        lambda filename, content: (filename, content),
    )
    monkeypatch.setattr(
        "app.services.imports.parse_receivable_rows",
        lambda content: parse_queue.pop(0),
    )

    try:
        first_result = import_linx_receivables(session, company, "receber-1.xls", b"snapshot-1")
        assert "sucesso" in first_result.message.lower()
        first_batch_id = first_result.batch.id

        second_result = import_linx_receivables(session, company, "receber-2.xls", b"snapshot-2")
        assert "sucesso" in second_result.message.lower()
        second_batch_id = second_result.batch.id
        assert second_batch_id != first_batch_id

        # Simulate a stale historical row left behind by an inconsistent environment.
        session.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=first_batch_id,
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 6),
                invoice_number="56707",
                company_code="1",
                installment_label="1",
                original_amount=Decimal("1000.00"),
                amount_with_interest=Decimal("1000.00"),
                customer_name="SORAIA PETERS FORMENTIN",
                document_reference=None,
                status="Em aberto",
                seller_name=None,
            )
        )
        session.commit()

        latest_batch = session.scalar(
            select(ImportBatch)
            .where(
                ImportBatch.company_id == company.id,
                ImportBatch.source_type == "linx_receivables",
                ImportBatch.status == "processed",
            )
            .order_by(desc(ImportBatch.created_at))
            .limit(1)
        )
        assert latest_batch is not None
        assert latest_batch.id == second_batch_id

        dashboard = build_boleto_dashboard(session, company)
        assert dashboard.receivables == []

        overview = build_cashflow_overview(
            session,
            company,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )
        assert sum((point.crediario_inflows for point in overview.daily_projection), Decimal("0.00")) == Decimal(
            "0.00"
        )
    finally:
        session.close()


def test_cashflow_prefers_linx_open_receivables_over_legacy_receivable_titles() -> None:
    session, company = _build_session()
    try:
        batch = ImportBatch(
            company_id=company.id,
            source_type="linx_receivables",
            filename="receber-legado.xls",
            status="processed",
            records_total=1,
            records_valid=1,
            records_invalid=0,
        )
        session.add(batch)
        session.flush()

        session.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=batch.id,
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 10),
                invoice_number="LEG-1",
                company_code="1",
                installment_label="1",
                original_amount=Decimal("40344.19"),
                amount_with_interest=Decimal("40344.19"),
                customer_name="CLIENTE LEGADO",
                document_reference=None,
                status="Em aberto",
                seller_name=None,
            )
        )
        session.add(
            LinxOpenReceivable(
                company_id=company.id,
                linx_code=9001,
                customer_name="CLIENTE API",
                due_date=datetime(2026, 4, 10),
                amount=Decimal("24457.97"),
                interest_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                document_number="API-1",
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)
        assert sum((Decimal(item.amount) for item in dashboard.receivables), Decimal("0.00")) == Decimal("24457.9700")

        overview = build_cashflow_overview(
            session,
            company,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )
        assert sum((point.crediario_inflows for point in overview.daily_projection), Decimal("0.00")) == Decimal(
            "24457.9700"
        )
    finally:
        session.close()

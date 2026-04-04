from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.api.router import api_router
from app.db.base import Base
from app.db.models import audit as audit_models  # noqa: F401
from app.db.models import finance as finance_models  # noqa: F401
from app.db.models import linx as linx_models  # noqa: F401
from app.db.models import purchasing as purchasing_models  # noqa: F401
from app.db.models.imports import ImportBatch
from app.db.models.security import Company, User
from app.schemas.imports import ImportResult
from app.services.import_parsers import parse_purchase_payable_rows
from app.services.purchase_planning import import_linx_purchase_payables


def _build_session() -> tuple[Session, Company, User]:
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
    session.flush()
    user = User(
        company_id=company.id,
        full_name="Admin Teste",
        email="admin-payables@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return session, company, user


def _build_purchase_payables_report(*rows: dict[str, str]) -> bytes:
    body_rows = []
    for row in rows:
        body_rows.append(
            """
            <tr>
              <td>{issue_date}</td>
              <td>{payable_pair}</td>
              <td>{due_date}</td>
              <td>{installment_label}</td>
              <td>{original_amount}</td>
              <td>{amount_with_charges}</td>
              <td>{supplier_display}</td>
              <td>{document_pair}</td>
              <td>{status}</td>
              <td></td>
            </tr>
            """.format(**row).strip()
        )
    html = f"""
    <html>
      <body>
        <table>
          <tr><td></td><td>Periodo: 01/01/2000 a 31/12/2050</td><td></td></tr>
          <tr>
            <th>Emissao</th>
            <th>Fatura/ Empresa</th>
            <th>Venc.</th>
            <th>Parc.</th>
            <th>Valor Fatura</th>
            <th>Valor c/ Desconto e Tx. Financ.</th>
            <th>Cliente/Fornecedor</th>
            <th>Doc./ Serie/ Nosso Numero</th>
            <th>Status</th>
            <th></th>
          </tr>
          <tr><td>Grupo: 0-Sem grupo</td></tr>
          {"".join(body_rows)}
          <tr><td>Legenda</td><td></td></tr>
        </table>
      </body>
    </html>
    """
    return html.encode("utf-8")


def test_parse_purchase_payable_rows_extracts_supplier_and_document_fields() -> None:
    content = _build_purchase_payables_report(
        {
            "issue_date": "29/10/25",
            "payable_pair": "54951|1",
            "due_date": "29/04/2026",
            "installment_label": "4|5",
            "original_amount": "R$ 685,00",
            "amount_with_charges": "R$ 685,00",
            "supplier_display": "BIAMAR MALHAS E CONFECCOES LTDA (12)",
            "document_pair": "422137|6",
            "status": "Em aberto",
        }
    )

    rows = parse_purchase_payable_rows(content)

    assert len(rows) == 1
    row = rows[0]
    assert row.payable_code == "54951"
    assert row.company_code == "1"
    assert row.installment_number == 4
    assert row.installments_total == 5
    assert row.supplier_name == "BIAMAR MALHAS E CONFECCOES LTDA"
    assert row.supplier_code == "12"
    assert row.document_number == "422137"
    assert row.document_series == "6"


def test_import_linx_purchase_payables_creates_invoice_entry_and_incremental_registry() -> None:
    session, company, user = _build_session()

    first_content = _build_purchase_payables_report(
        {
            "issue_date": "29/10/25",
            "payable_pair": "54951|1",
            "due_date": "29/04/2026",
            "installment_label": "1|2",
            "original_amount": "R$ 685,00",
            "amount_with_charges": "R$ 685,00",
            "supplier_display": "BIAMAR MALHAS E CONFECCOES LTDA (12)",
            "document_pair": "422137|6",
            "status": "Em aberto",
        }
    )
    second_content = _build_purchase_payables_report(
        {
            "issue_date": "29/10/25",
            "payable_pair": "54951|1",
            "due_date": "29/04/2026",
            "installment_label": "1|2",
            "original_amount": "R$ 685,00",
            "amount_with_charges": "R$ 685,00",
            "supplier_display": "BIAMAR MALHAS E CONFECCOES LTDA (12)",
            "document_pair": "422137|6",
            "status": "Em aberto",
        },
        {
            "issue_date": "29/10/25",
            "payable_pair": "54952|1",
            "due_date": "29/05/2026",
            "installment_label": "2|2",
            "original_amount": "R$ 685,00",
            "amount_with_charges": "R$ 700,00",
            "supplier_display": "BIAMAR MALHAS E CONFECCOES LTDA (12)",
            "document_pair": "422137|6",
            "status": "Em aberto",
        },
    )
    third_content = _build_purchase_payables_report(
        {
            "issue_date": "29/10/25",
            "payable_pair": "54952|1",
            "due_date": "29/05/2026",
            "installment_label": "2|2",
            "original_amount": "R$ 685,00",
            "amount_with_charges": "R$ 700,00",
            "supplier_display": "BIAMAR MALHAS E CONFECCOES LTDA (12)",
            "document_pair": "422137|6",
            "status": "Em aberto",
        }
    )

    try:
        first_result = import_linx_purchase_payables(
            session,
            company,
            "payables-1.xls",
            first_content,
            user,
        )
        assert "1 fornecedor(es) criado(s)." in first_result.message
        assert "1 lancamento(s) aberto(s) criado(s)." in first_result.message

        supplier = session.scalar(select(purchasing_models.Supplier))
        assert supplier is not None
        assert supplier.name == "BIAMAR MALHAS E CONFECCOES LTDA"
        assert supplier.has_purchase_invoices is True

        invoice = session.scalar(select(purchasing_models.PurchaseInvoice))
        assert invoice is not None
        assert invoice.invoice_number == "422137"
        assert invoice.series == "6"
        assert invoice.source_type == "linx_payables"

        installments = list(
            session.scalars(
                select(purchasing_models.PurchaseInstallment).where(
                    purchasing_models.PurchaseInstallment.purchase_invoice_id == invoice.id
                )
            )
        )
        assert len(installments) == 1
        assert installments[0].amount == Decimal("685.00")

        entry = session.scalar(
            select(finance_models.FinancialEntry).where(
                finance_models.FinancialEntry.purchase_installment_id == installments[0].id
            )
        )
        assert entry is not None
        assert entry.status == "open"
        assert entry.competence_date == date(2026, 4, 29)
        assert entry.issue_date == date(2025, 10, 29)
        assert entry.due_date == date(2026, 4, 29)
        assert entry.category is not None
        assert entry.category.name == "Compras"
        assert entry.notes is not None
        assert "Incluido via raspagem de dados do Linx." in entry.notes
        assert "Codigo da fatura: 54951." in entry.notes

        first_registry = list(session.scalars(select(linx_models.PurchasePayableTitle)))
        assert len(first_registry) == 1

        second_result = import_linx_purchase_payables(
            session,
            company,
            "payables-2.xls",
            second_content,
            user,
        )
        assert "1 fatura(s) nova(s) incluida(s)." in second_result.message

        invoices = list(session.scalars(select(purchasing_models.PurchaseInvoice)))
        assert len(invoices) == 1
        installments = list(
            session.scalars(
                select(purchasing_models.PurchaseInstallment)
                .where(purchasing_models.PurchaseInstallment.purchase_invoice_id == invoice.id)
                .order_by(purchasing_models.PurchaseInstallment.installment_number.asc())
            )
        )
        assert len(installments) == 2
        assert installments[1].amount == Decimal("700.00")

        entries = list(
            session.scalars(
                select(finance_models.FinancialEntry)
                .where(finance_models.FinancialEntry.purchase_invoice_id == invoice.id)
                .order_by(finance_models.FinancialEntry.due_date.asc())
            )
        )
        assert len(entries) == 2
        assert entries[1].status == "open"
        assert entries[1].competence_date == date(2026, 5, 29)
        assert entries[1].total_amount == Decimal("700.00")

        registry_rows = list(
            session.scalars(
                select(linx_models.PurchasePayableTitle).order_by(
                    linx_models.PurchasePayableTitle.due_date.asc()
                )
            )
        )
        assert len(registry_rows) == 2
        assert registry_rows[0].purchase_invoice_id == registry_rows[1].purchase_invoice_id

        third_result = import_linx_purchase_payables(
            session,
            company,
            "payables-3.xls",
            third_content,
            user,
        )
        assert "0 fatura(s) nova(s) incluida(s)." in third_result.message
        entries_after_third = list(session.scalars(select(finance_models.FinancialEntry)))
        registry_after_third = list(session.scalars(select(linx_models.PurchasePayableTitle)))
        assert len(entries_after_third) == 2
        assert len(registry_after_third) == 2
    finally:
        session.close()


def test_purchase_invoice_linx_sync_endpoint_smoke(monkeypatch) -> None:
    session, company, user = _build_session()
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    try:
        def fake_sync(db, current_company, actor_user):
            assert db is session
            assert current_company.id == company.id
            assert actor_user.id == user.id
            batch = ImportBatch(
                company_id=company.id,
                source_type="linx_purchase_payables",
                filename="FaturasaPagarporPeriodo.xls",
                status="processed",
                records_total=1,
                records_valid=1,
                records_invalid=0,
            )
            session.add(batch)
            session.commit()
            session.refresh(batch)
            return ImportResult(batch=batch, message="ok")

        monkeypatch.setattr(
            "app.api.routes.purchase_planning.sync_linx_purchase_payables",
            fake_sync,
        )

        response = client.post("/api/v1/purchase-invoices/linx-sync")
        assert response.status_code == 201
        assert response.json()["message"] == "ok"
    finally:
        client.close()
        session.close()

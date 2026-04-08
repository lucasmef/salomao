import io
import zipfile
from datetime import date, datetime
from decimal import Decimal
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer, LinxOpenReceivable, ReceivableTitle
from app.db.models.security import Company
from app.services.boletos import (
    ResolvedCustomerData,
    _validate_export_client_config,
    build_boleto_dashboard,
    build_missing_boletos_export,
    import_boleto_report,
    import_boleto_customer_data,
    normalize_text,
)


def _build_inter_workbook_bytes() -> bytes:
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Relatorio" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>CLIENTE</t></is></c>
      <c r="B1" t="inlineStr"><is><t>COD COBRANCA</t></is></c>
      <c r="C1" t="inlineStr"><is><t>EMISSAO</t></is></c>
      <c r="D1" t="inlineStr"><is><t>VENCIMENTO</t></is></c>
      <c r="E1" t="inlineStr"><is><t>VALOR</t></is></c>
      <c r="F1" t="inlineStr"><is><t>VALOR RECEBIDO</t></is></c>
      <c r="G1" t="inlineStr"><is><t>STATUS</t></is></c>
      <c r="H1" t="inlineStr"><is><t>IDENTIFICADOR</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Cliente Exemplo</t></is></c>
      <c r="B2" t="inlineStr"><is><t>ABC123</t></is></c>
      <c r="C2" t="inlineStr"><is><t>01/03/2026</t></is></c>
      <c r="D2" t="inlineStr"><is><t>12/03/2026</t></is></c>
      <c r="E2" t="inlineStr"><is><t>250,00</t></is></c>
      <c r="F2" t="inlineStr"><is><t>0,00</t></is></c>
      <c r="G2" t="inlineStr"><is><t>A receber</t></is></c>
      <c r="H2" t="inlineStr"><is><t>34191</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return content.getvalue()


def _wrap_zip(entry_name: str, entry_content: bytes) -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, entry_content)
    return content.getvalue()


def _create_receivable_batch(session: Session, company: Company, *, filename: str = "receivaveis.xlsx") -> ImportBatch:
    batch = ImportBatch(
        company_id=company.id,
        source_type="linx_receivables",
        filename=filename,
        status="processed",
        records_total=1,
        records_valid=1,
        records_invalid=0,
    )
    session.add(batch)
    session.flush()
    return batch


def test_import_boleto_customer_data_updates_customer_registry_without_touching_boleto_settings() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente Exemplo"),
            client_name="Cliente Exemplo",
            client_code=None,
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=12,
            include_interest=True,
            notes="Nao alterar",
        )
        session.add(customer)
        session.commit()

        content = """
<!DOCTYPE html>
<html>
<body>
Código;Nome;Endereco;Número;Complemento;Bairro;Cidade;Estado;Cep;Telefone1;Telefone2;Fax;Nascimento;Cpf/Cnpj;IE;Celular
1001;Cliente Exemplo;Rua Exemplo;330;;Centro;Cidade Exemplo;SC;99999999;;;;01/01/1990 00:00:00;12345678901;ISENTO;(48)99999-0000
9999;Cliente Sem Match;Rua X;10;;Centro;Cidade Modelo;SC;99999998;;;;;12345678901;;
</body>
</html>
""".strip().encode("cp1252")

        result = import_boleto_customer_data(
            session,
            company,
            filename="etiquetas.txt",
            content=content,
        )

        updated_customer = session.get(BoletoCustomerConfig, customer.id)
        assert updated_customer is not None
        assert updated_customer.client_code == "1001"
        assert updated_customer.address_street == "Rua Exemplo"
        assert updated_customer.address_number == "330"
        assert updated_customer.neighborhood == "Centro"
        assert updated_customer.city == "Cidade Exemplo"
        assert updated_customer.state == "SC"
        assert updated_customer.zip_code == "99999999"
        assert updated_customer.tax_id == "12345678901"
        assert updated_customer.state_registration == "ISENTO"
        assert updated_customer.mobile == "(48)99999-0000"

        assert updated_customer.uses_boleto is True
        assert updated_customer.mode == "mensal"
        assert updated_customer.boleto_due_day == 12
        assert updated_customer.include_interest is True
        assert updated_customer.notes == "Nao alterar"

        batch = session.get(ImportBatch, result.batch.id)
        assert batch is not None
        assert batch.source_type == "boletos:etiquetas"
        assert batch.records_total == 2
        assert batch.records_valid == 1
        assert batch.records_invalid == 1
    finally:
        session.close()
        engine.dispose()


def test_import_boleto_inter_report_accepts_outer_zip_with_excel_inside() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        workbook_bytes = _build_inter_workbook_bytes()
        zip_bytes = _wrap_zip("COMPLETO-2025-02-01_2026-03-21.xlsx", workbook_bytes)

        result = import_boleto_report(
            session,
            company,
            bank="INTER",
            filename="Relatorio.zip",
            content=zip_bytes,
        )

        imported_record = session.query(BoletoRecord).one()
        assert imported_record.client_name == "Cliente Exemplo"
        assert imported_record.document_id == "ABC123"
        assert imported_record.status == "A receber"
        assert imported_record.amount == Decimal("250.00")
        assert result.message == "Relatorio de boletos INTER importado com sucesso."
    finally:
        session.close()
        engine.dispose()


def test_build_missing_boletos_export_generates_excel_with_interest_and_fixed_template_values(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        monkeypatch.setattr("app.services.boletos._candidate_template_paths", lambda: [])

        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente Exemplo"),
            client_name="Cliente Exemplo",
            client_code="1001",
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=12,
            include_interest=True,
            address_street="Rua Exemplo",
            address_number="330",
            neighborhood="Centro",
            city="Cidade Exemplo",
            state="SC",
            zip_code="99999999",
            tax_id="12345678901",
            mobile="48999990000",
        )
        batch = _create_receivable_batch(session, company)
        receivable = ReceivableTitle(
            company_id=company.id,
            source_batch_id=batch.id,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 12),
            invoice_number="12345",
            company_code="1001",
            installment_label="001",
            original_amount=Decimal("250.00"),
            amount_with_interest=Decimal("250.00"),
            customer_name="Cliente Exemplo",
            document_reference="DOC-1",
            status="Em aberto",
        )
        session.add_all([customer, receivable])
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        assert len(dashboard.missing_boletos) == 1

        content, filename = build_missing_boletos_export(
            session,
            company,
            [dashboard.missing_boletos[0].selection_key],
        )

        assert filename.endswith(".xlsx")

        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row = next(item for item in sheet_root.findall("a:sheetData/a:row", namespace) if item.attrib.get("r") == "4")
        cells: dict[str, str] = {}
        for cell in row.findall("a:c", namespace):
            reference = cell.attrib["r"]
            inline_text = "".join(node.text or "" for node in cell.findall(".//a:t", namespace))
            raw_value = cell.findtext("a:v", default="", namespaces=namespace)
            cells[reference] = inline_text or raw_value

        assert cells["A4"] == "Cliente Exemplo"
        assert cells["C4"] == ""
        assert cells["D4"] == ""
        assert cells["O4"] == "Não"
        assert cells["R4"] == "12345"
        assert cells["S4"] == ""
        assert cells["V4"] == "30"
        assert cells["W4"] == "Porcentagem (%)"
        assert cells["X4"] == "2"
        assert cells["Y4"] == "Taxa (% a.m.)"
        assert cells["Z4"] == "1"
        assert cells["AA4"] == "Não aplicar desconto"
    finally:
        session.close()
        engine.dispose()


def test_validate_export_client_config_allows_missing_address_number() -> None:
    customer_data = ResolvedCustomerData(
        config=None,
        linx_customer=None,
        client_name="Cliente Exemplo",
        client_code="1001",
        uses_boleto=True,
        mode="individual",
        boleto_due_day=20,
        include_interest=False,
        notes=None,
        address_street="Rua Exemplo",
        address_number=None,
        address_complement=None,
        neighborhood="Centro",
        city="Cidade Exemplo",
        state="SC",
        zip_code="99999999",
        tax_id="12345678901",
        state_registration=None,
        phone_primary=None,
        phone_secondary=None,
        mobile=None,
    )

    missing = _validate_export_client_config(customer_data, "Cliente Exemplo")

    assert "numero" not in missing
    assert missing == []


def test_build_missing_boletos_export_defaults_monthly_due_day_to_20_when_empty(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        class FrozenDate(date):
            @classmethod
            def today(cls) -> "FrozenDate":
                return cls(2026, 3, 6)

        monkeypatch.setattr("app.services.boletos._candidate_template_paths", lambda: [])
        monkeypatch.setattr("app.services.boletos.date", FrozenDate)

        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente Exemplo"),
            client_name="Cliente Exemplo",
            client_code="1001",
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=None,
            include_interest=True,
            address_street="Rua Exemplo",
            address_number="330",
            neighborhood="Centro",
            city="Cidade Exemplo",
            state="SC",
            zip_code="99999999",
            tax_id="12345678901",
            mobile="48999990000",
        )
        batch = _create_receivable_batch(session, company)
        receivable = ReceivableTitle(
            company_id=company.id,
            source_batch_id=batch.id,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 12),
            invoice_number="12345",
            company_code="1001",
            installment_label="001",
            original_amount=Decimal("250.00"),
            amount_with_interest=Decimal("250.00"),
            customer_name="Cliente Exemplo",
            document_reference="DOC-1",
            status="Em aberto",
        )
        session.add_all([customer, receivable])
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        content, _filename = build_missing_boletos_export(
            session,
            company,
            [dashboard.missing_boletos[0].selection_key],
        )

        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row = next(item for item in sheet_root.findall("a:sheetData/a:row", namespace) if item.attrib.get("r") == "4")
        due_date_value = next(
            cell.findtext("a:v", default="", namespaces=namespace)
            for cell in row.findall("a:c", namespace)
            if cell.attrib["r"] == "T4"
        )

        assert due_date_value == "20032026"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_prefers_linx_api_receivables_and_customers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente API")
        legacy_batch = _create_receivable_batch(session, company, filename="legacy.xlsx")
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente API",
                client_code="1001",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=12,
                include_interest=True,
            )
        )
        session.add(
            LinxCustomer(
                company_id=company.id,
                linx_code=1001,
                legal_name="Cliente API",
                registration_type="C",
                address_street="Rua API",
                address_number="55",
                neighborhood="Centro",
                city="Cidade API",
                state="SC",
                zip_code="88000000",
                document_number="12345678901",
                phone_primary="4833334444",
                mobile="48999998888",
                state_registration="ISENTO",
            )
        )
        session.add(
            LinxOpenReceivable(
                company_id=company.id,
                linx_code=9001,
                customer_code=1001,
                customer_name="Cliente API",
                issue_date=datetime(2026, 4, 1),
                due_date=datetime(2026, 4, 12),
                amount=Decimal("250.00"),
                interest_amount=Decimal("5.00"),
                discount_amount=Decimal("0.00"),
                document_number="FAT-API",
                document_series="A",
                installment_number=1,
                installment_count=1,
            )
        )
        session.add(
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=legacy_batch.id,
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 12),
                invoice_number="LEGACY",
                company_code="1001",
                installment_label="001",
                original_amount=Decimal("999.00"),
                amount_with_interest=Decimal("999.00"),
                customer_name="Cliente Legado",
                document_reference="DOC-OLD",
                status="Em aberto",
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.receivable_count == 1
        assert dashboard.summary.receivable_total == Decimal("250.00")
        assert dashboard.receivables[0].invoice_number == "9001"
        assert dashboard.receivables[0].document == "FAT-API/A"
        assert dashboard.receivables[0].corrected_amount == Decimal("255.00")
        assert dashboard.clients[0].address_street == "Rua API"
        assert dashboard.clients[0].tax_id == "12345678901"
        assert dashboard.clients[0].phone_primary == "4833334444"
    finally:
        session.close()
        engine.dispose()


def test_build_missing_boletos_export_uses_linx_customer_data_when_available(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        monkeypatch.setattr("app.services.boletos._candidate_template_paths", lambda: [])

        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente API"),
            client_name="Cliente API",
            client_code="1001",
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=12,
            include_interest=True,
        )
        session.add(customer)
        session.add(
            LinxCustomer(
                company_id=company.id,
                linx_code=1001,
                legal_name="Cliente API",
                registration_type="C",
                address_street="Rua API",
                address_number="55",
                neighborhood="Centro",
                city="Cidade API",
                state="SC",
                zip_code="88000000",
                document_number="12345678901",
                mobile="48999998888",
            )
        )
        session.add(
            LinxOpenReceivable(
                company_id=company.id,
                linx_code=9001,
                customer_code=1001,
                customer_name="Cliente API",
                issue_date=datetime(2026, 4, 1),
                due_date=datetime(2026, 4, 12),
                amount=Decimal("250.00"),
                interest_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                document_number="FAT-API",
                installment_number=1,
                installment_count=1,
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        assert len(dashboard.missing_boletos) == 1

        content, filename = build_missing_boletos_export(
            session,
            company,
            [dashboard.missing_boletos[0].selection_key],
        )

        assert filename.endswith(".xlsx")
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row = next(item for item in sheet_root.findall("a:sheetData/a:row", namespace) if item.attrib.get("r") == "4")
        cells: dict[str, str] = {}
        for cell in row.findall("a:c", namespace):
            reference = cell.attrib["r"]
            inline_text = "".join(node.text or "" for node in cell.findall(".//a:t", namespace))
            raw_value = cell.findtext("a:v", default="", namespaces=namespace)
            cells[reference] = inline_text or raw_value

        assert cells["A4"] == "Cliente API"
        assert cells["E4"] == "Rua API"
        assert cells["F4"] == "55"
        assert cells["H4"] == "Centro"
        assert cells["I4"] == "Cidade API"
        assert cells["J4"] == "SC"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_matches_monthly_by_exact_month_total_ignoring_due_day() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="mensal",
                boleto_due_day=12,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 5),
                    invoice_number="1001",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("100.00"),
                    amount_with_interest=Decimal("100.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1001",
                    status="Em aberto",
                ),
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 10),
                    due_date=date(2026, 3, 20),
                    invoice_number="1002",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("150.00"),
                    amount_with_interest=Decimal("150.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1002",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-MAR-1",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 28),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="123",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.missing_boleto_count == 0
        assert dashboard.summary.excess_boleto_count == 0
        assert dashboard.missing_boletos == []
        assert dashboard.excess_boletos == []
    finally:
        session.close()
        engine.dispose()


def test_build_missing_boletos_export_forces_monthly_due_day_to_20_even_when_customer_has_custom_day(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        class FrozenDate(date):
            @classmethod
            def today(cls) -> "FrozenDate":
                return cls(2026, 3, 6)

        monkeypatch.setattr("app.services.boletos._candidate_template_paths", lambda: [])
        monkeypatch.setattr("app.services.boletos.date", FrozenDate)

        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente Exemplo"),
            client_name="Cliente Exemplo",
            client_code="1001",
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=12,
            include_interest=True,
            address_street="Rua Exemplo",
            address_number="330",
            neighborhood="Centro",
            city="Cidade Exemplo",
            state="SC",
            zip_code="99999999",
            tax_id="12345678901",
            mobile="48999990000",
        )
        batch = _create_receivable_batch(session, company)
        receivable = ReceivableTitle(
            company_id=company.id,
            source_batch_id=batch.id,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 12),
            invoice_number="12345",
            company_code="1001",
            installment_label="001",
            original_amount=Decimal("250.00"),
            amount_with_interest=Decimal("250.00"),
            customer_name="Cliente Exemplo",
            document_reference="DOC-1",
            status="Em aberto",
        )
        session.add_all([customer, receivable])
        session.commit()

        dashboard = build_boleto_dashboard(session, company, include_all_monthly_missing=True)
        content, _filename = build_missing_boletos_export(
            session,
            company,
            [dashboard.missing_boletos[0].selection_key],
        )

        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))

        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row = next(item for item in sheet_root.findall("a:sheetData/a:row", namespace) if item.attrib.get("r") == "4")
        due_date_value = next(
            cell.findtext("a:v", default="", namespaces=namespace)
            for cell in row.findall("a:c", namespace)
            if cell.attrib["r"] == "T4"
        )

        assert due_date_value == "20032026"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_matches_monthly_inter_boletos_by_document_competence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        customer = BoletoCustomerConfig(
            company_id=company.id,
            client_key=normalize_text("Cliente Mensal"),
            client_name="Cliente Mensal",
            client_code="1001",
            uses_boleto=True,
            mode="mensal",
            boleto_due_day=6,
            include_interest=False,
        )
        batch = _create_receivable_batch(session, company)
        receivables = [
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=batch.id,
                issue_date=date(2026, 3, 1),
                due_date=date(2026, 3, 1),
                invoice_number="257",
                company_code="1001",
                installment_label="003/004",
                original_amount=Decimal("503.87"),
                amount_with_interest=Decimal("503.87"),
                customer_name="Cliente Mensal",
                document_reference="DOC-202603",
                status="Em aberto",
            ),
            ReceivableTitle(
                company_id=company.id,
                source_batch_id=batch.id,
                issue_date=date(2026, 4, 1),
                due_date=date(2026, 4, 1),
                invoice_number="257",
                company_code="1001",
                installment_label="004/004",
                original_amount=Decimal("1967.64"),
                amount_with_interest=Decimal("1967.64"),
                customer_name="Cliente Mensal",
                document_reference="DOC-202604",
                status="Em aberto",
            ),
        ]
        boletos = [
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Mensal"),
                client_name="Cliente Mensal",
                document_id="202603",
                issue_date=date(2026, 4, 6),
                due_date=date(2026, 4, 6),
                amount=Decimal("503.87"),
                paid_amount=Decimal("503.87"),
                status="Recebido por boleto",
            ),
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=normalize_text("Cliente Mensal"),
                client_name="Cliente Mensal",
                document_id="202604",
                issue_date=date(2026, 4, 6),
                due_date=date(2026, 4, 6),
                amount=Decimal("1967.64"),
                paid_amount=Decimal("1967.64"),
                status="Recebido por boleto",
            ),
        ]
        session.add(customer)
        session.add_all(receivables)
        session.add_all(boletos)
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.missing_boletos == []
        assert dashboard.overdue_boletos == []
        assert len(dashboard.paid_pending) == 2
        paid_pending_amounts = sorted(item.amount for item in dashboard.paid_pending)
        assert paid_pending_amounts == [Decimal("503.87"), Decimal("1967.64")]
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_flags_monthly_total_mismatch_as_missing_and_excess() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="mensal",
                boleto_due_day=12,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 5),
                    invoice_number="1001",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("100.00"),
                    amount_with_interest=Decimal("100.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1001",
                    status="Em aberto",
                ),
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 10),
                    due_date=date(2026, 3, 20),
                    invoice_number="1002",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("150.00"),
                    amount_with_interest=Decimal("150.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1002",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-MAR-EXTRA",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 28),
                    amount=Decimal("260.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="456",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.missing_boleto_count == 1
        assert dashboard.summary.excess_boleto_count == 1
        assert dashboard.missing_boletos[0].amount == Decimal("250.00")
        assert dashboard.excess_boletos[0].amount == Decimal("260.00")
        assert dashboard.excess_boletos[0].boletos[0].document_id == "BOL-MAR-EXTRA"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_marks_unmatched_individual_boleto_as_excess() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=12,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 12),
                    invoice_number="12345",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("250.00"),
                    amount_with_interest=Decimal("250.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-OK",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 15),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="111",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-EXCESSO",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 25),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="222",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.missing_boleto_count == 0
        assert dashboard.summary.excess_boleto_count == 1
        assert dashboard.excess_boletos[0].boletos[0].document_id == "BOL-EXCESSO"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_matches_individual_boleto_by_configured_due_day() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=12,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 5),
                    invoice_number="12345",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("250.00"),
                    amount_with_interest=Decimal("250.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-DIA",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 12),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="111",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.missing_boleto_count == 0
        assert dashboard.summary.excess_boleto_count == 0
        assert dashboard.open_boletos[0].document_id == "BOL-DIA"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_matches_individual_boleto_by_day_20_when_customer_has_no_due_day() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=None,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 5),
                    invoice_number="12345",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("250.00"),
                    amount_with_interest=Decimal("250.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-DIA-20",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 20),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="111",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.missing_boleto_count == 0
        assert dashboard.summary.excess_boleto_count == 0
        assert dashboard.open_boletos[0].document_id == "BOL-DIA-20"
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_marks_active_boleto_for_client_that_no_longer_uses_boleto_as_excess() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=False,
                mode="individual",
                boleto_due_day=12,
            )
        )
        session.add(
            BoletoRecord(
                company_id=company.id,
                bank="INTER",
                client_key=client_key,
                client_name="Cliente Exemplo",
                document_id="BOL-ABERTO",
                issue_date=date(2026, 3, 2),
                due_date=date(2026, 3, 25),
                amount=Decimal("250.00"),
                paid_amount=Decimal("0.00"),
                status="A receber",
                barcode="222",
            )
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.excess_boleto_count == 1
        assert dashboard.excess_boletos[0].boletos[0].document_id == "BOL-ABERTO"
        assert "nao usa boleto" in dashboard.excess_boletos[0].reason.lower()
    finally:
        session.close()
        engine.dispose()


def test_build_boleto_dashboard_does_not_mark_paid_unmatched_boleto_as_excess() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)

    try:
        company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
        session.add(company)
        session.flush()

        client_key = normalize_text("Cliente Exemplo")
        batch = _create_receivable_batch(session, company)
        session.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name="Cliente Exemplo",
                uses_boleto=True,
                mode="individual",
                boleto_due_day=12,
            )
        )
        session.add_all(
            [
                ReceivableTitle(
                    company_id=company.id,
                    source_batch_id=batch.id,
                    issue_date=date(2026, 3, 1),
                    due_date=date(2026, 3, 12),
                    invoice_number="12345",
                    company_code="1001",
                    installment_label="001",
                    original_amount=Decimal("250.00"),
                    amount_with_interest=Decimal("250.00"),
                    customer_name="Cliente Exemplo",
                    document_reference="DOC-1",
                    status="Em aberto",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-OK",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 15),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("0.00"),
                    status="A receber",
                    barcode="111",
                ),
                BoletoRecord(
                    company_id=company.id,
                    bank="INTER",
                    client_key=client_key,
                    client_name="Cliente Exemplo",
                    document_id="BOL-PAGO",
                    issue_date=date(2026, 3, 2),
                    due_date=date(2026, 3, 25),
                    amount=Decimal("250.00"),
                    paid_amount=Decimal("250.00"),
                    status="Recebido por boleto",
                    barcode="333",
                ),
            ]
        )
        session.commit()

        dashboard = build_boleto_dashboard(session, company)

        assert dashboard.summary.excess_boleto_count == 0
        assert dashboard.excess_boletos == []
    finally:
        session.close()
        engine.dispose()

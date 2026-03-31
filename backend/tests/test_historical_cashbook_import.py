from __future__ import annotations

import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.sax.saxutils import escape

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models.finance import Category, FinancialEntry
from app.db.models.purchasing import CollectionSeason, Supplier
from app.db.models.security import Company, User
from app.services.import_parsers import parse_historical_cashbook_rows
from app.services.imports import HISTORICAL_CASHBOOK_SOURCE, import_historical_cashbook


def _excel_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_inline_string(value: str) -> str:
    return f"<is><t>{escape(value)}</t></is>"


def build_xlsx_bytes(sheet_name: str, rows: list[list[str | None]]) -> bytes:
    return build_multi_sheet_xlsx_bytes([(sheet_name, rows)])


def build_multi_sheet_xlsx_bytes(sheets: list[tuple[str, list[list[str | None]]]]) -> bytes:
    workbook_sheets: list[str] = []
    workbook_rels: list[str] = []
    worksheet_payloads: list[tuple[str, str]] = []

    for sheet_index, (sheet_name, rows) in enumerate(sheets, start=1):
        sheet_rows: list[str] = []
        for row_index, values in enumerate(rows, start=1):
            cells: list[str] = []
            for column_index, raw_value in enumerate(values, start=1):
                if raw_value is None:
                    continue
                cell_ref = f"{_excel_column_name(column_index)}{row_index}"
                cells.append(f'<c r="{cell_ref}" t="inlineStr">{_xlsx_inline_string(str(raw_value))}</c>')
            sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        workbook_sheets.append(
            f'<sheet name="{escape(sheet_name)}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{sheet_index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{sheet_index}.xml"/>'
        )
        worksheet_payloads.append(
            (
                f"xl/worksheets/sheet{sheet_index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(sheet_rows)}</sheetData>'
                "</worksheet>",
            )
        )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(workbook_rels)}'
        "</Relationships>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        "</styleSheet>"
    )
    temp_file = NamedTemporaryFile(suffix=".xlsx", delete=False)
    temp_file.close()
    try:
        with zipfile.ZipFile(temp_file.name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            archive.writestr("xl/styles.xml", styles_xml)
            for worksheet_path, worksheet_xml in worksheet_payloads:
                archive.writestr(worksheet_path, worksheet_xml)
        return Path(temp_file.name).read_bytes()
    finally:
        if Path(temp_file.name).exists():
            os.remove(temp_file.name)


class HistoricalCashbookImportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_db = NamedTemporaryFile(
            prefix="historical_cashbook_import_",
            suffix=".db",
            delete=False,
            dir=Path.cwd(),
        )
        temp_db.close()
        self.db_path = Path(temp_db.name)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.db: Session = self.SessionLocal()

        self.company = Company(
            legal_name="Empresa Teste Ltda",
            trade_name="Empresa Teste",
            document="12345678000199",
        )
        self.user = User(
            company=self.company,
            full_name="Teste",
            email=f"historico-{self.db_path.stem}@example.com",
            password_hash="hash",
            role="admin",
        )
        self.db.add_all([self.company, self.user])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        if self.db_path.exists():
            os.remove(self.db_path)

    def _add_category(
        self,
        *,
        name: str,
        code: str,
        entry_kind: str = "expense",
    ) -> Category:
        category = Category(
            company_id=self.company.id,
            code=code,
            name=name,
            entry_kind=entry_kind,
            report_group="Grupo Teste",
            report_subgroup="Subgrupo Teste",
            is_active=True,
        )
        self.db.add(category)
        self.db.commit()
        return category

    def _add_supplier(self, *, name: str, document_number: str) -> Supplier:
        supplier = Supplier(
            company_id=self.company.id,
            name=name,
            document_number=document_number,
            is_active=True,
        )
        self.db.add(supplier)
        self.db.commit()
        return supplier

    def _add_collection(self, *, name: str) -> CollectionSeason:
        collection = CollectionSeason(
            company_id=self.company.id,
            name=name,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True,
        )
        self.db.add(collection)
        self.db.commit()
        return collection

    def test_parser_supports_single_sheet_structured_template(self) -> None:
        workbook = build_xlsx_bytes(
            "LancamentosAntigos",
            [
                [
                    "source_reference",
                    "entry_type",
                    "status",
                    "title",
                    "due_date",
                    "category_code",
                    "principal_amount",
                    "total_amount",
                ],
                [
                    "hist-001",
                    "expense",
                    "settled",
                    "Conta de agua",
                    "2025-01-10",
                    "4.1.2.2.2",
                    "100.00",
                    "100.00",
                ],
            ],
        )

        rows = parse_historical_cashbook_rows(workbook)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].format_version, "structured")
        self.assertEqual(rows[0].source_reference, "hist-001")
        self.assertEqual(rows[0].title, "Conta de agua")
        self.assertEqual(rows[0].due_date, date(2025, 1, 10))
        self.assertEqual(rows[0].category_code, "4.1.2.2.2")
        self.assertEqual(rows[0].principal_amount, Decimal("100.00"))

    def test_parser_keeps_legacy_year_sheet_compatibility(self) -> None:
        workbook = build_xlsx_bytes(
            "2025",
            [
                ["Conta: Banco Historico"],
                ["Data", "Lancamento", "Documento", "Referencia", "Historico", "Debito", "Credito"],
                ["2025-01-15", "12", "DOC-15", "REF-15", "Compra antiga", "", "150.00"],
            ],
        )

        rows = parse_historical_cashbook_rows(workbook)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].format_version, "legacy")
        self.assertEqual(rows[0].source_account, "Banco Historico")
        self.assertEqual(rows[0].document_number, "DOC-15")
        self.assertEqual(rows[0].due_date, date(2025, 1, 15))
        self.assertEqual(rows[0].credit_amount, Decimal("150.00"))

    def test_import_historical_cashbook_structured_template_persists_full_entry_data(self) -> None:
        category = self._add_category(name="Agua e Saneamento", code="4.1.2.2.2", entry_kind="expense")
        interest_category = self._add_category(name="Juros Bancarios", code="6.1.1.1", entry_kind="expense")
        supplier = self._add_supplier(name="SAAE Municipal", document_number="12345678000155")
        collection = self._add_collection(name="Inverno 2024")

        workbook = build_xlsx_bytes(
            "LancamentosAntigos",
            [
                [
                    "source_reference",
                    "entry_type",
                    "status",
                    "title",
                    "description",
                    "notes",
                    "counterparty_name",
                    "document_number",
                    "issue_date",
                    "competence_date",
                    "due_date",
                    "category_code",
                    "interest_category_code",
                    "supplier_name",
                    "supplier_document_number",
                    "collection_name",
                    "principal_amount",
                    "interest_amount",
                    "discount_amount",
                    "penalty_amount",
                    "total_amount",
                    "expected_amount",
                ],
                [
                    "hist-agua-001",
                    "",
                    "",
                    "Conta de agua janeiro",
                    "Reprocessamento do historico antigo",
                    "Importado em lote unico",
                    "SAAE Municipal",
                    "FAT-2025-01",
                    "2025-01-05",
                    "2025-01-05",
                    "2025-01-10",
                    category.code,
                    interest_category.code,
                    supplier.name,
                    supplier.document_number,
                    collection.name,
                    "100.00",
                    "5.00",
                    "0.00",
                    "0.00",
                    "105.00",
                    "105.00",
                ],
            ],
        )

        result = import_historical_cashbook(self.db, self.company, "historico-novo.xlsx", workbook)

        entry = self.db.query(FinancialEntry).one()
        self.assertEqual(result.batch.records_valid, 1)
        self.assertEqual(entry.external_source, HISTORICAL_CASHBOOK_SOURCE)
        self.assertEqual(entry.source_system, HISTORICAL_CASHBOOK_SOURCE)
        self.assertEqual(entry.source_reference, "hist-agua-001")
        self.assertEqual(entry.title, "Conta de agua janeiro")
        self.assertEqual(entry.description, "Reprocessamento do historico antigo")
        self.assertEqual(entry.notes, "Importado em lote unico")
        self.assertEqual(entry.counterparty_name, "SAAE Municipal")
        self.assertEqual(entry.document_number, "FAT-2025-01")
        self.assertEqual(entry.issue_date, date(2025, 1, 5))
        self.assertEqual(entry.competence_date, date(2025, 1, 5))
        self.assertEqual(entry.due_date, date(2025, 1, 10))
        self.assertEqual(entry.entry_type, "expense")
        self.assertEqual(entry.status, "settled")
        self.assertEqual(entry.category_id, category.id)
        self.assertEqual(entry.interest_category_id, interest_category.id)
        self.assertEqual(entry.supplier_id, supplier.id)
        self.assertEqual(entry.collection_id, collection.id)
        self.assertEqual(entry.principal_amount, Decimal("100.00"))
        self.assertEqual(entry.interest_amount, Decimal("5.00"))
        self.assertEqual(entry.total_amount, Decimal("105.00"))
        self.assertEqual(entry.paid_amount, Decimal("105.00"))
        self.assertEqual(entry.expected_amount, Decimal("105.00"))
        self.assertIsNotNone(entry.settled_at)
        self.assertEqual(entry.account.name, "Movimentacoes Antigas")
        self.assertFalse(entry.account.is_active)

    def test_import_historical_cashbook_creates_missing_categories_and_suppliers_from_support_sheets(self) -> None:
        workbook = build_multi_sheet_xlsx_bytes(
            [
                (
                    "LancamentosAntigos",
                    [
                        [
                            "source_reference",
                            "entry_type",
                            "status",
                            "title",
                            "due_date",
                            "category_name",
                            "supplier_name",
                            "principal_amount",
                            "total_amount",
                            "expected_amount",
                        ],
                        [
                            "hist-simples-001",
                            "expense",
                            "settled",
                            "Fornecedor Historico",
                            "2025-02-10",
                            "Simples Nacional",
                            "Fornecedor Historico",
                            "100.00",
                            "100.00",
                            "100.00",
                        ],
                    ],
                ),
                (
                    "CategoriasCriar",
                    [
                        [
                            "categoria_importacao",
                            "entry_type_importacao",
                            "entry_kind_sistema",
                            "grupo_sugerido",
                            "subgrupo_sugerido",
                            "quantidade_categorias_origem",
                            "categorias_origem",
                            "observacoes",
                        ],
                        [
                            "Simples Nacional",
                            "expense",
                            "expense",
                            "Outras Despesas Operacionais",
                            "Outras Despesas Operacionais",
                            "1",
                            "SIMPLES FEDERAL A RECOLHER",
                            "Criacao automatica para teste",
                        ],
                    ],
                ),
                (
                    "FornecedoresCriar",
                    [
                        [
                            "supplier_name",
                            "quantidade_lancamentos",
                            "acao_fornecedor",
                            "supplier_document_number",
                        ],
                        [
                            "Fornecedor Historico",
                            "1",
                            "Criar fornecedor",
                            "",
                        ],
                    ],
                ),
            ]
        )

        result = import_historical_cashbook(self.db, self.company, "historico-apoio.xlsx", workbook)

        entry = self.db.query(FinancialEntry).one()
        category = self.db.query(Category).filter(Category.name == "Simples Nacional").one()
        supplier = self.db.query(Supplier).filter(Supplier.name == "Fornecedor Historico").one()

        self.assertEqual(result.batch.records_valid, 1)
        self.assertEqual(entry.category_id, category.id)
        self.assertEqual(entry.supplier_id, supplier.id)
        self.assertEqual(category.entry_kind, "expense")
        self.assertEqual(category.report_group, "Outras Despesas Operacionais")
        self.assertEqual(category.report_subgroup, "Outras Despesas Operacionais")
        self.assertTrue(category.is_active)
        self.assertTrue(supplier.is_active)

    def test_import_historical_cashbook_creates_missing_category_and_supplier_from_row_data(self) -> None:
        workbook = build_xlsx_bytes(
            "LancamentosAntigos",
            [
                [
                    "source_reference",
                    "entry_type",
                    "status",
                    "title",
                    "counterparty_name",
                    "due_date",
                    "category_name",
                    "supplier_name",
                    "principal_amount",
                    "total_amount",
                    "expected_amount",
                ],
                [
                    "hist-row-create-001",
                    "expense",
                    "settled",
                    "Fornecedor Livre",
                    "Fornecedor Livre",
                    "2025-03-15",
                    "Categoria Livre",
                    "Fornecedor Livre",
                    "80.00",
                    "80.00",
                    "80.00",
                ],
            ],
        )

        result = import_historical_cashbook(self.db, self.company, "historico-row-create.xlsx", workbook)

        entry = self.db.query(FinancialEntry).one()
        category = self.db.query(Category).filter(Category.name == "Categoria Livre").one()
        supplier = self.db.query(Supplier).filter(Supplier.name == "Fornecedor Livre").one()

        self.assertEqual(result.batch.records_valid, 1)
        self.assertEqual(entry.category_id, category.id)
        self.assertEqual(entry.supplier_id, supplier.id)
        self.assertEqual(category.entry_kind, "expense")
        self.assertIsNone(category.report_group)
        self.assertTrue(supplier.is_active)


if __name__ == "__main__":
    unittest.main()

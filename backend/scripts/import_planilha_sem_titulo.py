from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from sqlalchemy import func, select

from app.db.models.finance import Category, FinancialEntry
from app.db.models.purchasing import Supplier
from app.db.models.security import User
from app.db.session import SessionLocal
from app.schemas.financial_entry import FinancialEntryCreate
from app.services.bootstrap import ensure_company_catalog
from app.services.category_catalog import match_historical_category_name
from app.services.company_context import get_current_company
from app.services.finance_ops import create_entry, update_entry


WORKBOOK_PATH = Path(__file__).resolve().parents[2] / "planilha_sem_titulo.xlsx"
SOURCE_SYSTEM = "spreadsheet_payables"
SOURCE_REFERENCE_PREFIX = "planilha-sem-titulo:sheet1:"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EXCEL_EPOCH = date(1899, 12, 30)
PURCHASE_CATEGORY_NAMES = {"compra a prazo paga", "compra a vista"}


@dataclass(slots=True)
class SpreadsheetRow:
    excel_row: int
    issue_date: date | None
    due_date: date | None
    amount: Decimal
    counterparty_name: str
    history: str


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


def clean_label(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+\(\d+\)\s*$", "", value).strip()
    return re.sub(r"\s+", " ", text)


def parse_brl_amount(raw_value: str) -> Decimal:
    cleaned = (raw_value or "").replace("R$", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned or "0").quantize(Decimal("0.01"))


def parse_excel_date(raw_value: str) -> date | None:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return None
    try:
        serial = int(float(cleaned))
    except ValueError:
        return None
    return EXCEL_EPOCH + timedelta(days=serial)


def workbook_rows(path: Path) -> Iterable[SpreadsheetRow]:
    with ZipFile(path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for string_item in root.findall("a:si", NS):
                shared_strings.append("".join(node.text or "" for node in string_item.findall(".//a:t", NS)))

        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}

        first_sheet = workbook_root.find("a:sheets/a:sheet", NS)
        if first_sheet is None:
            return
        target = rel_map[first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
        if not target.startswith("xl/"):
            target = f"xl/{target}"

        sheet_root = ET.fromstring(workbook.read(target))
        for row in sheet_root.findall("a:sheetData/a:row", NS):
            row_index = int(row.attrib.get("r", "0"))
            if row_index <= 1:
                continue
            values: dict[str, str] = {}
            for cell in row.findall("a:c", NS):
                ref = cell.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                cell_type = cell.attrib.get("t")
                raw = cell.find("a:v", NS)
                if raw is None:
                    values[col] = ""
                elif cell_type == "s":
                    values[col] = shared_strings[int(raw.text or "0")]
                else:
                    values[col] = raw.text or ""
            amount = parse_brl_amount(values.get("C", ""))
            yield SpreadsheetRow(
                excel_row=row_index,
                issue_date=parse_excel_date(values.get("A", "")),
                due_date=parse_excel_date(values.get("B", "")),
                amount=amount,
                counterparty_name=clean_label(values.get("D", "")),
                history=clean_label(values.get("E", "")),
            )


def find_category(category_map: dict[str, Category], history: str) -> Category:
    normalized_history = normalize_text(history)
    if "compra a prazo" in normalized_history:
        category_name = "Compra a Prazo Paga"
    elif "compra a vista" in normalized_history:
        category_name = "Compra a Vista"
    elif "divisao de lucros" in normalized_history:
        category_name = "Divisao de Lucros"
    else:
        category_name = match_historical_category_name(history=history, entry_type="expense", inflow=False)
    category = category_map.get(normalize_text(category_name))
    if category is None:
        raise RuntimeError(f"Categoria nao encontrada para historico '{history}' => '{category_name}'")
    return category


def find_or_create_supplier(db, company_id: str, supplier_name: str) -> tuple[Supplier | None, bool]:
    clean_name = clean_label(supplier_name)
    if not clean_name:
        return None, False
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.company_id == company_id,
            func.lower(Supplier.name) == clean_name.lower(),
        )
    )
    if supplier is not None:
        if not supplier.is_active:
            supplier.is_active = True
        return supplier, False

    supplier = Supplier(
        company_id=company_id,
        name=clean_name,
        payment_basis="delivery",
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier, True


def is_purchase_category(category: Category) -> bool:
    return normalize_text(category.name) in PURCHASE_CATEGORY_NAMES or "compr" in normalize_text(category.report_group)


def main() -> None:
    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(f"Planilha nao encontrada: {WORKBOOK_PATH}")

    created = 0
    updated = 0
    errors = 0
    suppliers_created = 0
    category_counter: dict[str, int] = {}

    with SessionLocal() as db:
        company = get_current_company(db)
        ensure_company_catalog(db, company.id)
        actor_user = db.scalar(
            select(User)
            .where(User.company_id == company.id, User.is_active.is_(True))
            .order_by(User.created_at.asc())
        )
        if actor_user is None:
            raise RuntimeError("Nenhum usuario ativo encontrado para registrar a importacao")

        categories = list(
            db.scalars(
                select(Category)
                .where(Category.company_id == company.id, Category.is_active.is_(True))
                .order_by(Category.name.asc())
            )
        )
        category_map = {normalize_text(category.name): category for category in categories}

        try:
            for row in workbook_rows(WORKBOOK_PATH):
                source_reference = f"{SOURCE_REFERENCE_PREFIX}{row.excel_row}"
                existing_entry = db.scalar(
                    select(FinancialEntry).where(
                        FinancialEntry.company_id == company.id,
                        FinancialEntry.source_reference == source_reference,
                        FinancialEntry.is_deleted.is_(False),
                    )
                )

                try:
                    category = find_category(category_map, row.history)
                    supplier_id = None
                    if is_purchase_category(category):
                        supplier, was_created = find_or_create_supplier(db, company.id, row.counterparty_name)
                        if supplier is None:
                            raise RuntimeError("Compra de mercadoria sem fornecedor identificado")
                        supplier_id = supplier.id
                        if was_created:
                            suppliers_created += 1

                    title = clean_label(row.counterparty_name) or clean_label(row.history) or f"Lancamento {row.excel_row}"
                    payload = FinancialEntryCreate(
                        account_id=None,
                        category_id=category.id,
                        interest_category_id=None,
                        supplier_id=supplier_id,
                        collection_id=None,
                        purchase_invoice_id=None,
                        purchase_installment_id=None,
                        entry_type="expense",
                        status="planned",
                        title=title[:160],
                        description=row.history or None,
                        notes=f"Importado da planilha sem titulo, linha {row.excel_row}",
                        counterparty_name=row.counterparty_name[:180] or None,
                        document_number=None,
                        issue_date=row.issue_date,
                        competence_date=row.issue_date,
                        due_date=row.due_date,
                        settled_at=None,
                        principal_amount=row.amount,
                        interest_amount=Decimal("0.00"),
                        discount_amount=Decimal("0.00"),
                        penalty_amount=Decimal("0.00"),
                        total_amount=row.amount,
                        paid_amount=Decimal("0.00"),
                        expected_amount=row.amount,
                        external_source=SOURCE_SYSTEM,
                        source_system=SOURCE_SYSTEM,
                        source_reference=source_reference,
                    )
                    if existing_entry is None:
                        create_entry(db, company, payload, actor_user)
                        created += 1
                    else:
                        update_entry(db, company, existing_entry.id, payload, actor_user)
                        updated += 1
                    category_counter[category.name] = category_counter.get(category.name, 0) + 1
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    print(f"[erro] linha {row.excel_row}: {exc}")

            db.commit()
        except Exception:
            db.rollback()
            raise

    print(f"arquivo={WORKBOOK_PATH}")
    print(f"criados={created}")
    print(f"atualizados={updated}")
    print(f"fornecedores_criados={suppliers_created}")
    print(f"erros={errors}")
    print("categorias=")
    for name, count in sorted(category_counter.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer, LinxOpenReceivable, ReceivableTitle
from app.db.models.security import Company
from app.schemas.boletos import (
    BoletoClientConfigBulkUpdate,
    BoletoClientRead,
    BoletoDashboardRead,
    BoletoFileRead,
    BoletoMatchItem,
    BoletoOverdueInvoiceSummaryRead,
    BoletoReceivableRead,
    BoletoRecordRead,
    BoletoSummaryRead,
)
from app.schemas.imports import ImportResult
from app.services.import_parsers import fingerprint_bytes


ACTIVE_STATUSES = {
    "C6": {"A vencer", "Vencido"},
    "INTER": {"A receber"},
}

PAID_STATUSES = {
    "C6": {"Pago"},
    "INTER": {"Recebido por boleto"},
}

CANCELLED_STATUSES = {
    "C6": {"Cancelado"},
    "INTER": {"Cancelado"},
}

OPEN_RECEIVABLE_STATUS_KEYWORDS = ("aberto", "a receber", "vencido", "em aberto", "pendente")
PAID_RECEIVABLE_STATUS_KEYWORDS = ("recebido", "pago", "quitado", "baixado")
CANCELLED_RECEIVABLE_STATUS_KEYWORDS = ("cancelado",)
INDIVIDUAL_DUE_DATE_TOLERANCE_DAYS = 5
EXCEL_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
XML_NS = "http://www.w3.org/XML/1998/namespace"
TEMPLATE_SHEET_NAME = "Cobrança Simples"
TEMPLATE_DATA_START_ROW = 4
TEMPLATE_FILL_ROW = 5
TEMPLATE_LAST_COLUMN = "AQ"
INTER_ZIP_PASSWORD_CANDIDATES = ("130921",)


@dataclass
class MissingBoletoExportRow:
    client_name: str
    tax_id: str
    email: str | None
    phone: str | None
    address_street: str
    address_number: str
    address_complement: str | None
    neighborhood: str
    city: str
    state: str
    zip_code: str
    amount: Decimal
    include_interest: bool
    charge_code: str
    description: str
    due_date: date


@dataclass
class ReceivableItem:
    client_name: str
    client_code: str
    client_key: str
    issue_date: date | None
    due_date: date | None
    invoice_number: str
    installment: str
    amount: Decimal
    corrected_amount: Decimal
    document: str
    status: str


@dataclass
class ParsedBoleto:
    bank: str
    client_name: str
    client_key: str
    document_id: str
    issue_date: date | None
    due_date: date | None
    amount: Decimal
    paid_amount: Decimal
    status: str
    barcode: str


@dataclass
class CustomerLabelRow:
    code: str
    client_name: str
    client_key: str
    address_street: str | None
    address_number: str | None
    address_complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    tax_id: str | None
    state_registration: str | None
    phone_primary: str | None
    phone_secondary: str | None
    mobile: str | None


@dataclass
class LinxCustomerLookup:
    by_code: dict[str, LinxCustomer]
    by_name: dict[str, LinxCustomer]


@dataclass
class ResolvedCustomerData:
    config: BoletoCustomerConfig | None
    linx_customer: LinxCustomer | None
    client_name: str
    client_code: str | None
    uses_boleto: bool
    mode: str
    boleto_due_day: int | None
    include_interest: bool
    notes: str | None
    address_street: str | None
    address_number: str | None
    address_complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    tax_id: str | None
    state_registration: str | None
    phone_primary: str | None
    phone_secondary: str | None
    mobile: str | None


class LinxHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []
        elif tag == "br" and self.in_cell:
            self.current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if any(cell.strip() for cell in self.current_row):
                self.rows.append(self.current_row)
            self.in_row = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.upper()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _normalize_header(value: str) -> str:
    return normalize_text(value).lower()


def parse_brl(value: str | None) -> Decimal:
    raw = (value or "").replace("R$", "").replace("\xa0", " ").strip()
    raw = raw.replace(".", "").replace(",", ".")
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal("0")


def parse_br_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text or text.upper() == "N/A":
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_excel_date(value: date) -> str:
    return value.strftime("%d%m%Y")


def split_client_name(raw_name: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", raw_name.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return raw_name.strip(), ""


def column_to_index(reference: str) -> int:
    letters = re.match(r"([A-Z]+)", reference)
    if not letters:
        return 0
    result = 0
    for char in letters.group(1):
        result = result * 26 + (ord(char) - 64)
    return result - 1


def _pick_header(item: dict[str, str], *keys: str) -> str:
    normalized_map = {_normalize_header(key): value for key, value in item.items()}
    for key in keys:
        value = normalized_map.get(_normalize_header(key))
        if value is not None:
            return value
    return ""


def _strip_or_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _digits_or_none(value: str | None) -> str | None:
    digits = re.sub(r"\D+", "", value or "")
    return digits or None


def _normalize_client_code(value: str | None) -> str:
    raw = (value or "").strip()
    digits = re.sub(r"\D+", "", raw)
    if digits:
        return digits.lstrip("0") or "0"
    return normalize_text(raw)


def _digits_only(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _truncate_text(value: str | None, maximum: int) -> str:
    return (value or "").strip()[:maximum]


def _excel_number(value: str | int | Decimal | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), "f")
    text = str(value).strip()
    return text or None


def _format_competence_label(value: str | None) -> str:
    if not value or len(value) != 7 or value[4] != "-":
        return ""
    return f"{value[5:7]}/{value[:4]}"


def _decode_customer_data_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _month_key(target_date: date | None) -> str:
    if not target_date:
        return ""
    return f"{target_date.year:04d}-{target_date.month:02d}"


def _create_batch(
    db: Session,
    company_id: str,
    source_type: str,
    filename: str,
    content: bytes,
) -> tuple[ImportBatch, bool]:
    fingerprint = fingerprint_bytes(content)
    existing = db.scalar(
        select(ImportBatch).where(
            ImportBatch.company_id == company_id,
            ImportBatch.source_type == source_type,
            ImportBatch.fingerprint == fingerprint,
            ImportBatch.status == "processed",
        )
    )
    if existing:
        return existing, True

    batch = ImportBatch(
        company_id=company_id,
        source_type=source_type,
        filename=filename,
        fingerprint=fingerprint,
        status="processing",
    )
    db.add(batch)
    db.flush()
    return batch, False


def _is_excel_workbook_archive(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "xl/workbook.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _extract_excel_workbook_bytes(content: bytes, *, password_candidates: list[str] | None = None) -> bytes:
    if _is_excel_workbook_archive(content):
        return content

    normalized_passwords = [candidate.encode("utf-8") for candidate in (password_candidates or []) if candidate]

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            excel_entries = [
                info
                for info in archive.infolist()
                if not info.is_dir() and Path(info.filename).suffix.lower() in {".xlsx", ".xlsm", ".xltx", ".xltm"}
            ]
            for entry in sorted(excel_entries, key=lambda item: item.filename):
                try:
                    nested_content = archive.read(entry.filename)
                except RuntimeError:
                    nested_content = None
                    for password in normalized_passwords:
                        try:
                            nested_content = archive.read(entry.filename, pwd=password)
                            break
                        except RuntimeError:
                            continue
                    if nested_content is None:
                        raise ValueError(
                            "Nao consegui extrair automaticamente a planilha dentro do ZIP do Inter. "
                            "O arquivo parece criptografado ou corrompido. Se ele usar uma senha fixa, me diga a regra "
                            "para eu automatizar; se nao usar senha, baixe o ZIP novamente e tente importar de novo."
                        ) from None
                if _is_excel_workbook_archive(nested_content):
                    return nested_content
    except zipfile.BadZipFile as error:
        raise ValueError("Arquivo do Inter invalido. Envie o .xlsx ou o .zip original com a planilha dentro.") from error

    raise ValueError("Nao encontrei uma planilha Excel valida dentro do arquivo do Inter.")


def _sheet_path_from_workbook(workbook: zipfile.ZipFile, sheet_name: str | None = None) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    relations_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    relation_map = {
        item.attrib["Id"]: item.attrib["Target"].lstrip("/")
        for item in relations_root
    }
    normalized_sheet_name = normalize_text(sheet_name) if sheet_name is not None else None

    for sheet in workbook_root.findall("a:sheets/a:sheet", EXCEL_NS):
        if sheet_name is not None:
            current_name = sheet.attrib.get("name", "")
            if current_name != sheet_name and normalize_text(current_name) != normalized_sheet_name:
                continue
        relation_id = sheet.attrib.get(f"{{{EXCEL_NS['r']}}}id")
        if not relation_id or relation_id not in relation_map:
            continue
        target = relation_map[relation_id]
        return target if target.startswith("xl/") else f"xl/{target}"

    if sheet_name is not None:
        raise ValueError(f"Nao encontrei a aba '{sheet_name}' na planilha.")
    raise ValueError("Nao encontrei nenhuma aba valida na planilha.")


def _load_inter_report(content: bytes, *, password_candidates: list[str] | None = None) -> list[ParsedBoleto]:
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared_strings: list[str] = []
    rows: list[list[str]] = []

    workbook_bytes = _extract_excel_workbook_bytes(content, password_candidates=password_candidates)
    try:
        with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
            if "xl/sharedStrings.xml" in workbook.namelist():
                root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
                for item in root.findall("a:si", namespace):
                    parts = [node.text or "" for node in item.findall(".//a:t", namespace)]
                    shared_strings.append("".join(parts))

            sheet_name = _sheet_path_from_workbook(workbook)
            sheet = ET.fromstring(workbook.read(sheet_name))
            for row in sheet.findall(".//a:sheetData/a:row", namespace):
                values_by_index: dict[int, str] = {}
                highest_index = -1
                for cell in row.findall("a:c", namespace):
                    index = column_to_index(cell.attrib.get("r", "A1"))
                    highest_index = max(highest_index, index)
                    cell_type = cell.attrib.get("t")
                    value = ""
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//a:t", namespace))
                    else:
                        raw_value = cell.find("a:v", namespace)
                        if raw_value is not None and raw_value.text:
                            value = raw_value.text
                            if cell_type == "s":
                                value = shared_strings[int(value)]
                    values_by_index[index] = value
                if highest_index >= 0:
                    row_values = [values_by_index.get(idx, "") for idx in range(highest_index + 1)]
                    if any(value.strip() for value in row_values):
                        rows.append(row_values)
    except zipfile.BadZipFile as error:
        raise ValueError("Arquivo do Inter invalido. Envie o .xlsx ou o .zip original com a planilha dentro.") from error

    if not rows:
        return []

    headers = rows[0]
    boletos: list[ParsedBoleto] = []
    for row in rows[1:]:
        item = dict(zip(headers, row))
        display_name, _ = split_client_name(_pick_header(item, "CLIENTE"))
        if not display_name:
            continue
        boletos.append(
            ParsedBoleto(
                bank="INTER",
                client_name=display_name,
                client_key=normalize_text(display_name),
                document_id=_pick_header(item, "COD COBRANCA", "CÓD. COBRANCA", "COD. COBRANCA").strip(),
                issue_date=parse_br_date(_pick_header(item, "EMISSAO", "EMISSÃO")),
                due_date=parse_br_date(_pick_header(item, "VENCIMENTO")),
                amount=parse_brl(_pick_header(item, "VALOR")),
                paid_amount=parse_brl(_pick_header(item, "VALOR RECEBIDO")),
                status=_pick_header(item, "STATUS").strip(),
                barcode=_pick_header(item, "IDENTIFICADOR").strip(),
            )
        )
    return boletos


def _load_c6_report(content: bytes) -> list[ParsedBoleto]:
    boletos: list[ParsedBoleto] = []
    text = content.decode("utf-8-sig", errors="ignore").splitlines()
    reader = csv.DictReader(text, delimiter=";")
    for row in reader:
        item = {str(key): str(value or "") for key, value in row.items()}
        display_name, _ = split_client_name(_pick_header(item, "Quem pagara o boleto"))
        if not display_name:
            continue
        boletos.append(
            ParsedBoleto(
                bank="C6",
                client_name=display_name,
                client_key=normalize_text(display_name),
                document_id=_pick_header(item, "Numero do documento").strip(),
                issue_date=parse_br_date(_pick_header(item, "Data de emissao")),
                due_date=parse_br_date(_pick_header(item, "Data de vencimento")),
                amount=parse_brl(_pick_header(item, "Valor da Emissao")),
                paid_amount=parse_brl(_pick_header(item, "Valor de Liquidacao")),
                status=_pick_header(item, "Status").strip(),
                barcode=_pick_header(item, "Codigo de barras").strip(),
            )
        )
    return boletos


def _load_customer_label_rows(content: bytes) -> list[CustomerLabelRow]:
    raw_text = _decode_customer_data_content(content)
    candidate_lines = [
        line.strip()
        for line in raw_text.splitlines()
        if ";" in line and not line.lstrip().startswith("<")
    ]
    if not candidate_lines:
        raise ValueError("Arquivo de etiquetas sem linhas validas para importacao.")

    header_index = next(
        (
            index
            for index, line in enumerate(candidate_lines)
            if _normalize_header(line).startswith("codigo nome endereco numero complemento bairro cidade estado cep")
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Nao encontrei o cabecalho esperado no arquivo de etiquetas.")

    reader = csv.DictReader(candidate_lines[header_index:], delimiter=";")
    rows: list[CustomerLabelRow] = []
    for item in reader:
        parsed_item = {str(key): str(value or "") for key, value in item.items() if key}
        code = _pick_header(parsed_item, "Codigo").strip()
        client_name = _pick_header(parsed_item, "Nome").strip()
        if not code or not client_name:
            continue

        rows.append(
            CustomerLabelRow(
                code=code,
                client_name=client_name,
                client_key=normalize_text(client_name),
                address_street=_strip_or_none(_pick_header(parsed_item, "Endereco")),
                address_number=_strip_or_none(_pick_header(parsed_item, "Numero")),
                address_complement=_strip_or_none(_pick_header(parsed_item, "Complemento")),
                neighborhood=_strip_or_none(_pick_header(parsed_item, "Bairro")),
                city=_strip_or_none(_pick_header(parsed_item, "Cidade")),
                state=_strip_or_none(_pick_header(parsed_item, "Estado")),
                zip_code=_digits_or_none(_pick_header(parsed_item, "Cep", "CEP")),
                tax_id=_digits_or_none(_pick_header(parsed_item, "Cpf/Cnpj", "CPF/CNPJ")),
                state_registration=_strip_or_none(_pick_header(parsed_item, "IE")),
                phone_primary=_strip_or_none(_pick_header(parsed_item, "Telefone1", "Telefone 1")),
                phone_secondary=_strip_or_none(_pick_header(parsed_item, "Telefone2", "Telefone 2")),
                mobile=_strip_or_none(_pick_header(parsed_item, "Celular")),
            )
        )

    if not rows:
        raise ValueError("Arquivo de etiquetas sem clientes validos para atualizar.")

    return rows


def import_boleto_report(
    db: Session,
    company: Company,
    *,
    bank: str,
    filename: str,
    content: bytes,
) -> ImportResult:
    source_type = f"boletos:{bank.lower()}"
    batch, reused = _create_batch(db, company.id, source_type, filename, content)
    if reused:
        return ImportResult(batch=batch, message=f"Arquivo de boletos {bank} ja importado anteriormente.")

    if bank == "INTER":
        password_candidates: list[str] = []
        company_document = _digits_only(company.document)
        if company_document:
            password_candidates.append(company_document)
        for candidate in INTER_ZIP_PASSWORD_CANDIDATES:
            if candidate not in password_candidates:
                password_candidates.append(candidate)
        rows = _load_inter_report(content, password_candidates=password_candidates)
    elif bank == "C6":
        rows = _load_c6_report(content)
    else:
        raise ValueError("Banco de boletos nao suportado")

    db.execute(
        delete(BoletoRecord).where(
            BoletoRecord.company_id == company.id,
            BoletoRecord.bank == bank,
        )
    )

    for row in rows:
        db.add(
            BoletoRecord(
                company_id=company.id,
                source_batch_id=batch.id,
                bank=row.bank,
                client_key=row.client_key,
                client_name=row.client_name,
                document_id=row.document_id,
                issue_date=row.issue_date,
                due_date=row.due_date,
                amount=row.amount,
                paid_amount=row.paid_amount,
                status=row.status,
                barcode=row.barcode,
            )
        )

    batch.records_total = len(rows)
    batch.records_valid = len(rows)
    batch.records_invalid = 0
    batch.status = "processed"
    db.commit()
    db.refresh(batch)
    return ImportResult(batch=batch, message=f"Relatorio de boletos {bank} importado com sucesso.")


def import_boleto_customer_data(
    db: Session,
    company: Company,
    *,
    filename: str,
    content: bytes,
) -> ImportResult:
    batch, reused = _create_batch(db, company.id, "boletos:etiquetas", filename, content)
    if reused:
        return ImportResult(batch=batch, message="Arquivo de etiquetas ja importado anteriormente.")

    rows = _load_customer_label_rows(content)
    config_map = _load_customer_configs(db, company.id)
    config_by_code = {
        _normalize_client_code(item.client_code): item
        for item in config_map.values()
        if _normalize_client_code(item.client_code)
    }
    config_by_name = {normalize_text(item.client_name): item for item in config_map.values()}

    matched_count = 0
    for row in rows:
        config = config_by_code.get(_normalize_client_code(row.code))
        if not config:
            config = config_map.get(row.client_key) or config_by_name.get(row.client_key)
        if not config:
            continue

        if not config.client_code:
            config.client_code = row.code
        config.address_street = row.address_street
        config.address_number = row.address_number
        config.address_complement = row.address_complement
        config.neighborhood = row.neighborhood
        config.city = row.city
        config.state = row.state.upper() if row.state else None
        config.zip_code = row.zip_code
        config.tax_id = row.tax_id
        config.state_registration = row.state_registration
        config.phone_primary = row.phone_primary
        config.phone_secondary = row.phone_secondary
        config.mobile = row.mobile
        matched_count += 1

    batch.records_total = len(rows)
    batch.records_valid = matched_count
    batch.records_invalid = max(len(rows) - matched_count, 0)
    batch.status = "processed"
    db.commit()
    db.refresh(batch)

    if matched_count == 0:
        return ImportResult(
            batch=batch,
            message="Arquivo importado, mas nenhum cliente da cobranca foi localizado para atualizar.",
        )
    return ImportResult(
        batch=batch,
        message=f"Dados cadastrais atualizados para {matched_count} cliente(s) da cobranca.",
    )


def _receivable_is_open(status: str) -> bool:
    normalized = normalize_text(status).lower()
    if any(keyword in normalized for keyword in CANCELLED_RECEIVABLE_STATUS_KEYWORDS):
        return False
    if any(keyword in normalized for keyword in PAID_RECEIVABLE_STATUS_KEYWORDS):
        return False
    if any(keyword in normalized for keyword in OPEN_RECEIVABLE_STATUS_KEYWORDS):
        return True
    return True


def _build_linx_customer_lookup(db: Session, company_id: str) -> LinxCustomerLookup:
    customers = list(
        db.scalars(
            select(LinxCustomer).where(
                LinxCustomer.company_id == company_id,
                LinxCustomer.registration_type.in_(("C", "A")),
            )
        )
    )

    by_code: dict[str, LinxCustomer] = {}
    by_name: dict[str, LinxCustomer] = {}
    for customer in customers:
        normalized_code = _normalize_client_code(str(customer.linx_code))
        if normalized_code and normalized_code not in by_code:
            by_code[normalized_code] = customer

        candidate_names = [customer.legal_name, customer.display_name]
        for candidate_name in candidate_names:
            normalized_name = normalize_text(candidate_name or "")
            if normalized_name and normalized_name not in by_name:
                by_name[normalized_name] = customer

    return LinxCustomerLookup(by_code=by_code, by_name=by_name)


def _match_linx_customer(
    lookup: LinxCustomerLookup,
    *,
    client_code: str | None,
    client_name: str | None,
    client_key: str | None,
) -> LinxCustomer | None:
    normalized_code = _normalize_client_code(client_code)
    if normalized_code:
        matched_by_code = lookup.by_code.get(normalized_code)
        if matched_by_code is not None:
            return matched_by_code

    normalized_name = normalize_text(client_name or "")
    if normalized_name:
        matched_by_name = lookup.by_name.get(normalized_name)
        if matched_by_name is not None:
            return matched_by_name

    normalized_key = normalize_text(client_key or "")
    if normalized_key:
        return lookup.by_name.get(normalized_key)
    return None


def _load_receivable_items(db: Session, company_id: str) -> list[ReceivableItem]:
    linx_open_receivables = list(
        db.scalars(
            select(LinxOpenReceivable)
            .where(LinxOpenReceivable.company_id == company_id)
            .order_by(LinxOpenReceivable.due_date.asc(), LinxOpenReceivable.customer_name.asc())
        )
    )
    if linx_open_receivables:
        items: list[ReceivableItem] = []
        for receivable in linx_open_receivables:
            issue_date = receivable.issue_date.date() if receivable.issue_date else None
            due_date = receivable.due_date.date() if receivable.due_date else None
            amount = Decimal(receivable.amount or 0)
            interest_amount = Decimal(receivable.interest_amount or 0)
            discount_amount = Decimal(receivable.discount_amount or 0)
            installment_label = ""
            if receivable.installment_number and receivable.installment_count:
                installment_label = f"{receivable.installment_number:03d}/{receivable.installment_count:03d}"
            elif receivable.installment_number:
                installment_label = f"{receivable.installment_number:03d}"

            document_parts = [part for part in [receivable.document_number, receivable.document_series] if part]
            items.append(
                ReceivableItem(
                    client_name=(receivable.customer_name or "").strip() or f"Cliente {receivable.linx_code}",
                    client_code=str(receivable.customer_code or ""),
                    client_key=normalize_text(receivable.customer_name or f"Cliente {receivable.linx_code}"),
                    issue_date=issue_date,
                    due_date=due_date,
                    invoice_number=receivable.document_number or str(receivable.linx_code),
                    installment=installment_label,
                    amount=amount,
                    corrected_amount=max(amount + interest_amount - discount_amount, Decimal("0")),
                    document="/".join(document_parts),
                    status="Em aberto",
                )
            )
        return items

    latest_batch = db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.company_id == company_id,
            ImportBatch.source_type == "linx_receivables",
            ImportBatch.status == "processed",
        )
        .order_by(desc(ImportBatch.created_at))
        .limit(1)
    )
    if not latest_batch:
        return []

    items: list[ReceivableItem] = []
    for title in db.scalars(
        select(ReceivableTitle).where(
            ReceivableTitle.company_id == company_id,
            ReceivableTitle.source_batch_id == latest_batch.id,
        )
    ):
        if not _receivable_is_open(title.status):
            continue
        client_name, inline_code = split_client_name(title.customer_name.strip())
        items.append(
            ReceivableItem(
                client_name=client_name,
                client_code=title.company_code or inline_code or "",
                client_key=normalize_text(client_name),
                issue_date=title.issue_date,
                due_date=title.due_date,
                invoice_number=title.invoice_number or "",
                installment=title.installment_label or "",
                amount=Decimal(title.original_amount or 0),
                corrected_amount=Decimal(title.amount_with_interest or title.original_amount or 0),
                document=title.document_reference or "",
                status=title.status,
            )
        )
    return items


def _load_customer_configs(db: Session, company_id: str) -> dict[str, BoletoCustomerConfig]:
    return {
        item.client_key: item
        for item in db.scalars(select(BoletoCustomerConfig).where(BoletoCustomerConfig.company_id == company_id))
    }


def _sync_customer_configs_from_reports(
    db: Session,
    company: Company,
    receivables_by_client: dict[str, list[ReceivableItem]],
    boletos_by_client: dict[str, list[BoletoRecord]],
    config_map: dict[str, BoletoCustomerConfig],
    customer_lookup: LinxCustomerLookup,
) -> dict[str, BoletoCustomerConfig]:
    all_client_keys = sorted(set(receivables_by_client) | set(boletos_by_client) | set(config_map))
    changed = False

    for client_key in all_client_keys:
        client_receivables = receivables_by_client.get(client_key, [])
        client_boletos = boletos_by_client.get(client_key, [])
        client_name = (
            (client_receivables[0].client_name if client_receivables else None)
            or (client_boletos[0].client_name if client_boletos else None)
            or client_key.title()
        )
        client_code = client_receivables[0].client_code if client_receivables else None
        matched_customer = _match_linx_customer(
            customer_lookup,
            client_code=client_code,
            client_name=client_name,
            client_key=client_key,
        )
        if matched_customer is not None:
            client_name = matched_customer.legal_name or client_name
            client_code = client_code or str(matched_customer.linx_code)
        config = config_map.get(client_key)

        if not config:
            config = BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_name=client_name,
                client_code=client_code,
                uses_boleto=bool(client_boletos),
                mode="individual",
                boleto_due_day=None,
                include_interest=False,
                notes=None,
            )
            db.add(config)
            config_map[client_key] = config
            changed = True
            continue

        if client_name and config.client_name != client_name:
            config.client_name = client_name
            changed = True
        if client_code and config.client_code != client_code:
            config.client_code = client_code
            changed = True

    if changed:
        db.commit()
        return _load_customer_configs(db, company.id)
    return config_map


def _resolve_customer_data(
    *,
    client_key: str,
    client_name: str,
    client_code: str | None,
    config: BoletoCustomerConfig | None,
    customer_lookup: LinxCustomerLookup,
    auto_uses_boleto: bool,
) -> ResolvedCustomerData:
    matched_customer = _match_linx_customer(
        customer_lookup,
        client_code=client_code or (config.client_code if config else None),
        client_name=client_name or (config.client_name if config else None),
        client_key=client_key,
    )
    resolved_name = (
        client_name
        or (matched_customer.legal_name if matched_customer else None)
        or (config.client_name if config else None)
        or client_key.title()
    )
    resolved_code = (
        client_code
        or (str(matched_customer.linx_code) if matched_customer else None)
        or (config.client_code if config else None)
    )

    return ResolvedCustomerData(
        config=config,
        linx_customer=matched_customer,
        client_name=resolved_name,
        client_code=resolved_code,
        uses_boleto=config.uses_boleto if config else auto_uses_boleto,
        mode=config.mode if config else "individual",
        boleto_due_day=config.boleto_due_day if config else None,
        include_interest=bool(config.include_interest) if config else False,
        notes=config.notes if config else None,
        address_street=(matched_customer.address_street if matched_customer else None) or (config.address_street if config else None),
        address_number=(matched_customer.address_number if matched_customer else None) or (config.address_number if config else None),
        address_complement=(matched_customer.address_complement if matched_customer else None) or (config.address_complement if config else None),
        neighborhood=(matched_customer.neighborhood if matched_customer else None) or (config.neighborhood if config else None),
        city=(matched_customer.city if matched_customer else None) or (config.city if config else None),
        state=(matched_customer.state if matched_customer else None) or (config.state if config else None),
        zip_code=(matched_customer.zip_code if matched_customer else None) or (config.zip_code if config else None),
        tax_id=(matched_customer.document_number if matched_customer else None) or (config.tax_id if config else None),
        state_registration=(matched_customer.state_registration if matched_customer else None) or (config.state_registration if config else None),
        phone_primary=(matched_customer.phone_primary if matched_customer else None) or (config.phone_primary if config else None),
        phone_secondary=config.phone_secondary if config else None,
        mobile=(matched_customer.mobile if matched_customer else None) or (config.mobile if config else None),
    )


def _latest_file_info(db: Session, company_id: str, source_type: str) -> BoletoFileRead | None:
    batch = db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.company_id == company_id,
            ImportBatch.source_type == source_type,
            ImportBatch.status == "processed",
        )
        .order_by(desc(ImportBatch.created_at))
        .limit(1)
    )
    if not batch:
        return None
    return BoletoFileRead(
        source_type=source_type,
        name=batch.filename,
        updated_at=batch.created_at.isoformat(),
    )


def _boleto_status_bucket(boleto: BoletoRecord) -> str:
    if boleto.status in PAID_STATUSES.get(boleto.bank, set()):
        return "paid"
    if boleto.status in CANCELLED_STATUSES.get(boleto.bank, set()):
        return "cancelled"
    if boleto.status in ACTIVE_STATUSES.get(boleto.bank, set()):
        return "active"
    return "other"


def _within_cent(value_a: Decimal, value_b: Decimal) -> bool:
    return abs(value_a - value_b) <= Decimal("0.01")


def _due_dates_within_tolerance(first_date: date | None, second_date: date | None) -> bool:
    if not first_date or not second_date:
        return False
    return abs((first_date - second_date).days) <= INDIVIDUAL_DUE_DATE_TOLERANCE_DAYS


def _find_individual_matches(
    receivable: ReceivableItem,
    boletos: list[BoletoRecord],
    *,
    status_bucket: str | None = None,
    used_boleto_ids: set[str] | None = None,
) -> list[BoletoRecord]:
    matches: list[BoletoRecord] = []
    for boleto in boletos:
        if used_boleto_ids and boleto.id in used_boleto_ids:
            continue
        if boleto.client_key != receivable.client_key:
            continue
        if boleto.status in CANCELLED_STATUSES.get(boleto.bank, set()):
            continue
        if not _within_cent(receivable.amount, Decimal(boleto.amount or 0)):
            continue
        if not _due_dates_within_tolerance(receivable.due_date, boleto.due_date):
            continue
        if status_bucket and _boleto_status_bucket(boleto) != status_bucket:
            continue
        matches.append(boleto)

    return sorted(
        matches,
        key=lambda boleto: (
            0
            if _boleto_status_bucket(boleto) == "paid"
            else 1
            if _boleto_status_bucket(boleto) == "active"
            else 2,
            abs(((boleto.due_date or date.max) - (receivable.due_date or date.max)).days),
            boleto.due_date or date.max,
            boleto.bank,
            boleto.document_id,
        ),
    )


def _find_best_individual_match(
    receivable: ReceivableItem,
    boletos: list[BoletoRecord],
    *,
    used_boleto_ids: set[str] | None = None,
) -> BoletoRecord | None:
    matches = _find_individual_matches(receivable, boletos, used_boleto_ids=used_boleto_ids)
    return matches[0] if matches else None


def _month_is_visible(competence: str, today: date) -> bool:
    if not competence or len(competence) != 7 or competence[4] != "-":
        return True
    year = int(competence[:4])
    month = int(competence[5:7])
    return (year, month) <= (today.year, today.month)


def _match_grouped_receivables(
    receivables: list[ReceivableItem],
    boletos: list[BoletoRecord],
    *,
    mode: str,
    due_day: int | None,
    today: date,
    include_all_monthly: bool = False,
) -> list[dict[str, Any]]:
    del due_day
    receivables_by_month: dict[str, list[ReceivableItem]] = {}
    boletos_by_month: dict[str, list[BoletoRecord]] = {}

    for receivable in receivables:
        receivables_by_month.setdefault(_month_key(receivable.due_date), []).append(receivable)
    for boleto in boletos:
        boletos_by_month.setdefault(_month_key(boleto.due_date), []).append(boleto)

    all_competences = sorted(set(receivables_by_month) | set(boletos_by_month))
    allocations: list[dict[str, Any]] = []
    for competence in all_competences:
        receivable_group = sorted(
            receivables_by_month.get(competence, []),
            key=lambda item: (item.due_date or date.max, item.invoice_number, item.installment),
        )
        boleto_group = sorted(
            boletos_by_month.get(competence, []),
            key=lambda item: (item.due_date or date.max, item.bank, item.document_id),
        )
        receivable_total = sum((item.amount for item in receivable_group), Decimal("0"))
        boleto_total = sum((Decimal(item.amount or 0) for item in boleto_group), Decimal("0"))
        allocations.append(
            {
                "receivables": receivable_group,
                "boletos": boleto_group,
                "competence": competence,
                "total_amount": receivable_total if receivable_group else boleto_total,
                "matched": bool(receivable_group and boleto_group and _within_cent(receivable_total, boleto_total)),
                "visible_for_missing": include_all_monthly or mode != "mensal" or _month_is_visible(competence, today),
            }
        )

    return allocations


def _allocation_signature(allocation: dict[str, Any]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                item.invoice_number,
                item.installment,
                item.due_date.isoformat() if item.due_date else "",
                format(item.amount.quantize(Decimal("0.01")), "f"),
            )
            for item in allocation["receivables"]
        )
    )


def _build_match_selection_key(
    *,
    client_key: str,
    match_type: str,
    mode: str,
    due_date: date | None,
    competence: str | None,
    receivables: list[ReceivableItem],
    boletos: list[BoletoRecord],
) -> str:
    payload = "|".join(
        [
            client_key,
            match_type,
            mode,
            due_date.isoformat() if due_date else "",
            competence or "",
            ";".join(
                f"{item.invoice_number}:{item.installment}:{item.due_date.isoformat() if item.due_date else ''}:{format(item.amount.quantize(Decimal('0.01')), 'f')}"
                for item in receivables
            ),
            ";".join(
                f"{item.bank}:{item.document_id}:{item.due_date.isoformat() if item.due_date else ''}:{format(Decimal(item.amount or 0).quantize(Decimal('0.01')), 'f')}"
                for item in boletos
            ),
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:16]


def _serialize_receivable(receivable: ReceivableItem) -> BoletoReceivableRead:
    return BoletoReceivableRead(
        client_name=receivable.client_name,
        client_code=receivable.client_code or None,
        invoice_number=receivable.invoice_number,
        installment=receivable.installment,
        issue_date=receivable.issue_date,
        due_date=receivable.due_date,
        amount=receivable.amount,
        corrected_amount=receivable.corrected_amount,
        document=receivable.document,
        status=receivable.status,
    )


def _serialize_boleto(boleto: BoletoRecord) -> BoletoRecordRead:
    return BoletoRecordRead(
        id=boleto.id,
        bank=boleto.bank,
        client_name=boleto.client_name,
        document_id=boleto.document_id,
        issue_date=boleto.issue_date,
        due_date=boleto.due_date,
        amount=Decimal(boleto.amount or 0),
        paid_amount=Decimal(boleto.paid_amount or 0),
        status=boleto.status,
        barcode=boleto.barcode,
        linha_digitavel=boleto.linha_digitavel,
        pix_copia_e_cola=boleto.pix_copia_e_cola,
        inter_codigo_solicitacao=boleto.inter_codigo_solicitacao,
        inter_account_id=boleto.inter_account_id,
        pdf_available=bool(boleto.bank == "INTER" and boleto.inter_codigo_solicitacao),
    )


def _serialize_receivable(receivable: ReceivableItem) -> BoletoReceivableRead:
    return BoletoReceivableRead(
        client_name=receivable.client_name,
        client_code=receivable.client_code or None,
        invoice_number=receivable.invoice_number,
        installment=receivable.installment,
        issue_date=receivable.issue_date,
        due_date=receivable.due_date,
        amount=receivable.amount,
        corrected_amount=receivable.corrected_amount,
        document=receivable.document,
        status=receivable.status,
    )


def _build_overdue_boleto_item(
    *,
    client_key: str,
    client_name: str,
    mode: str,
    today: date,
    reason: str,
    receivables: list[ReceivableItem],
    boleto: BoletoRecord | None,
) -> BoletoMatchItem:
    due_date = boleto.due_date if boleto and boleto.due_date else min((item.due_date for item in receivables if item.due_date), default=None)
    amount = Decimal(boleto.amount or 0) if boleto else sum((item.amount for item in receivables), Decimal("0"))
    days_overdue = (today - due_date).days if due_date else 0
    competence = _month_key(receivables[0].due_date if receivables else due_date)
    return BoletoMatchItem(
        selection_key=_build_match_selection_key(
            client_key=client_key,
            match_type="overdue",
            mode=mode,
            due_date=due_date,
            competence=competence,
            receivables=receivables,
            boletos=[boleto] if boleto else [],
        ),
        client_key=client_key,
        type="agrupado" if len(receivables) > 1 else "individual",
        client_name=client_name,
        mode=mode,
        due_date=due_date,
        days_overdue=days_overdue,
        status=boleto.status if boleto else "Sem boleto emitido",
        amount=amount,
        reason=reason,
        receivable_count=len(receivables),
        bank=boleto.bank if boleto else None,
        competence=competence,
        receivables=[_serialize_receivable(item) for item in receivables],
        boletos=[_serialize_boleto(boleto)] if boleto else [],
    )


def _build_paid_pending_item(
    *,
    client_key: str,
    client_name: str,
    mode: str,
    receivables: list[ReceivableItem],
    boletos: list[BoletoRecord],
) -> BoletoMatchItem:
    due_date = min((item.due_date for item in receivables if item.due_date), default=None)
    amount = sum((item.amount for item in receivables), Decimal("0"))
    competence = _month_key(due_date)
    return BoletoMatchItem(
        selection_key=_build_match_selection_key(
            client_key=client_key,
            match_type="paid-pending",
            mode=mode,
            due_date=due_date,
            competence=competence,
            receivables=receivables,
            boletos=boletos,
        ),
        client_key=client_key,
        type="agrupado" if len(receivables) > 1 else "individual",
        client_name=client_name,
        mode=mode,
        due_date=due_date,
        days_overdue=0,
        status="Pago sem baixa",
        amount=amount,
        reason="O banco indica pagamento, mas a fatura ainda aparece em aberto no LINX.",
        receivable_count=len(receivables),
        bank=boletos[0].bank if boletos else None,
        competence=competence,
        receivables=[_serialize_receivable(item) for item in receivables],
        boletos=[_serialize_boleto(item) for item in boletos],
    )


def _build_missing_boleto_item(
    *,
    client_key: str,
    client_name: str,
    mode: str,
    reason: str,
    receivables: list[ReceivableItem],
) -> BoletoMatchItem:
    due_date = min((item.due_date for item in receivables if item.due_date), default=None)
    amount = sum((item.amount for item in receivables), Decimal("0"))
    competence = _month_key(due_date)
    return BoletoMatchItem(
        selection_key=_build_match_selection_key(
            client_key=client_key,
            match_type="missing",
            mode=mode,
            due_date=due_date,
            competence=competence,
            receivables=receivables,
            boletos=[],
        ),
        client_key=client_key,
        type="agrupado" if len(receivables) > 1 else "individual",
        client_name=client_name,
        mode=mode,
        due_date=due_date,
        days_overdue=0,
        status="Sem boleto",
        amount=amount,
        reason=reason,
        receivable_count=len(receivables),
        bank=None,
        competence=competence,
        receivables=[_serialize_receivable(item) for item in receivables],
        boletos=[],
    )


def _build_excess_boleto_item(
    *,
    client_key: str,
    client_name: str,
    mode: str,
    reason: str,
    boletos: list[BoletoRecord],
) -> BoletoMatchItem:
    due_date = min((item.due_date for item in boletos if item.due_date), default=None)
    amount = sum((Decimal(item.amount or 0) for item in boletos), Decimal("0"))
    competence = _month_key(due_date)
    statuses = sorted({item.status for item in boletos if item.status})
    status = statuses[0] if len(statuses) == 1 else ", ".join(statuses) if statuses else "Sem fatura"
    return BoletoMatchItem(
        selection_key=_build_match_selection_key(
            client_key=client_key,
            match_type="excess",
            mode=mode,
            due_date=due_date,
            competence=competence,
            receivables=[],
            boletos=boletos,
        ),
        client_key=client_key,
        type="agrupado" if mode != "individual" or len(boletos) > 1 else "individual",
        client_name=client_name,
        mode=mode,
        due_date=due_date,
        days_overdue=0,
        status=status,
        amount=amount,
        reason=reason,
        receivable_count=0,
        bank=boletos[0].bank if boletos else None,
        competence=competence,
        receivables=[],
        boletos=[_serialize_boleto(item) for item in boletos],
    )


def update_boleto_configs(
    db: Session,
    company: Company,
    payload: BoletoClientConfigBulkUpdate,
) -> None:
    existing = _load_customer_configs(db, company.id)
    for item in payload.clients:
        config = existing.get(item.client_key)
        if not config:
            config = BoletoCustomerConfig(
                company_id=company.id,
                client_key=item.client_key,
                client_name=item.client_key,
            )
            db.add(config)
            db.flush()
        config.uses_boleto = item.uses_boleto
        config.mode = item.mode
        config.boleto_due_day = item.boleto_due_day
        config.include_interest = item.include_interest
        config.notes = (item.notes or "").strip() or None
    db.commit()


def build_boleto_dashboard(
    db: Session,
    company: Company,
    *,
    include_all_monthly_missing: bool = False,
) -> BoletoDashboardRead:
    today = date.today()
    receivables = _load_receivable_items(db, company.id)
    boleto_records = list(db.scalars(select(BoletoRecord).where(BoletoRecord.company_id == company.id)))
    config_map = _load_customer_configs(db, company.id)
    customer_lookup = _build_linx_customer_lookup(db, company.id)

    receivables_by_client: dict[str, list[ReceivableItem]] = {}
    boletos_by_client: dict[str, list[BoletoRecord]] = {}
    for item in receivables:
        receivables_by_client.setdefault(item.client_key, []).append(item)
    for boleto in boleto_records:
        boletos_by_client.setdefault(boleto.client_key, []).append(boleto)

    config_map = _sync_customer_configs_from_reports(
        db,
        company,
        receivables_by_client,
        boletos_by_client,
        config_map,
        customer_lookup,
    )

    files = [
        item
        for item in [
            _latest_file_info(db, company.id, "linx_open_receivables"),
            _latest_file_info(db, company.id, "linx_customers"),
            _latest_file_info(db, company.id, "boletos:inter"),
            _latest_file_info(db, company.id, "boletos:c6"),
            _latest_file_info(db, company.id, "boletos:etiquetas"),
        ]
        if item
    ]

    all_client_keys = sorted(set(receivables_by_client) | set(boletos_by_client) | set(config_map))

    clients: list[BoletoClientRead] = []
    open_boletos = sorted(
        [_serialize_boleto(item) for item in boleto_records if _boleto_status_bucket(item) == "active"],
        key=lambda item: (item.due_date or date.max, item.client_name, item.document_id),
    )
    overdue_boletos: list[BoletoMatchItem] = []
    overdue_invoices: list[BoletoOverdueInvoiceSummaryRead] = []
    paid_pending: list[BoletoMatchItem] = []
    missing_boletos: list[BoletoMatchItem] = []
    excess_boletos: list[BoletoMatchItem] = []
    boleto_clients_count = 0

    for client_key in all_client_keys:
        client_receivables = sorted(
            receivables_by_client.get(client_key, []),
            key=lambda item: (item.due_date or date.max, item.invoice_number, item.installment),
        )
        client_boletos = [
            boleto
            for boleto in boletos_by_client.get(client_key, [])
            if boleto.status not in CANCELLED_STATUSES.get(boleto.bank, set())
        ]
        config = config_map.get(client_key)
        client_name = (
            (client_receivables[0].client_name if client_receivables else None)
            or (client_boletos[0].client_name if client_boletos else None)
            or (config.client_name if config else client_key.title())
        )
        auto_uses_boleto = bool(client_boletos)
        resolved_customer = _resolve_customer_data(
            client_key=client_key,
            client_name=client_name,
            client_code=(client_receivables[0].client_code if client_receivables else None) or (config.client_code if config else None),
            config=config,
            customer_lookup=customer_lookup,
            auto_uses_boleto=auto_uses_boleto,
        )
        client_name = resolved_customer.client_name
        client_code = resolved_customer.client_code
        uses_boleto = resolved_customer.uses_boleto
        mode = resolved_customer.mode
        due_day = resolved_customer.boleto_due_day
        notes = resolved_customer.notes
        active_client_boletos = [boleto for boleto in client_boletos if _boleto_status_bucket(boleto) == "active"]

        overdue_receivables = [item for item in client_receivables if item.due_date and item.due_date < today]
        if overdue_receivables:
            oldest_due = min(item.due_date for item in overdue_receivables if item.due_date)
            overdue_invoices.append(
                BoletoOverdueInvoiceSummaryRead(
                    client_name=client_name,
                    invoice_count=len(overdue_receivables),
                    days_overdue=(today - oldest_due).days if oldest_due else 0,
                    overdue_amount=sum((item.amount for item in overdue_receivables), Decimal("0")),
                    oldest_due_date=oldest_due,
                )
            )

        if uses_boleto:
            boleto_clients_count += 1

        matched_paid_count = 0
        overdue_boleto_count = 0

        if not uses_boleto:
            if mode == "individual":
                for boleto in active_client_boletos:
                    excess_boletos.append(
                        _build_excess_boleto_item(
                            client_key=client_key,
                            client_name=client_name,
                            mode=mode,
                            reason="Cliente marcado como nao usa boleto, mas existe boleto em aberto emitido.",
                            boletos=[boleto],
                        )
                    )
            else:
                allocations = _match_grouped_receivables(
                    [],
                    active_client_boletos,
                    mode=mode,
                    due_day=due_day,
                    today=today,
                    include_all_monthly=include_all_monthly_missing,
                )
                for allocation in allocations:
                    boleto_group = allocation["boletos"]
                    if not boleto_group:
                        continue
                    excess_boletos.append(
                        _build_excess_boleto_item(
                            client_key=client_key,
                            client_name=client_name,
                            mode=mode,
                            reason="Cliente marcado como nao usa boleto, mas existem boletos em aberto emitidos.",
                            boletos=boleto_group,
                        )
                    )
        elif uses_boleto:
            if mode == "individual":
                used_boleto_ids: set[str] = set()
                for receivable in client_receivables:
                    matched_boleto = _find_best_individual_match(
                        receivable,
                        client_boletos,
                        used_boleto_ids=used_boleto_ids,
                    )
                    if not matched_boleto:
                        missing_boletos.append(
                            _build_missing_boleto_item(
                                client_key=client_key,
                                client_name=client_name,
                                mode=mode,
                                reason="Nenhum boleto com valor exato e vencimento em ate 5 dias foi encontrado.",
                                receivables=[receivable],
                            )
                        )
                        if receivable.due_date and receivable.due_date < today:
                            overdue_boletos.append(
                                _build_overdue_boleto_item(
                                    client_key=client_key,
                                    client_name=client_name,
                                    mode=mode,
                                    today=today,
                                    reason="A fatura venceu e nao encontrei boleto emitido para ela.",
                                    receivables=[receivable],
                                    boleto=None,
                                )
                            )
                            overdue_boleto_count += 1
                        continue

                    used_boleto_ids.add(matched_boleto.id)
                    bucket = _boleto_status_bucket(matched_boleto)
                    if bucket == "paid":
                        matched_paid_count += 1
                        paid_pending.append(
                            _build_paid_pending_item(
                                client_key=client_key,
                                client_name=client_name,
                                mode=mode,
                                receivables=[receivable],
                                boletos=[matched_boleto],
                            )
                        )
                    elif bucket == "active" and matched_boleto.due_date and matched_boleto.due_date < today:
                        overdue_boletos.append(
                            _build_overdue_boleto_item(
                                client_key=client_key,
                                client_name=client_name,
                                mode=mode,
                                today=today,
                                reason="Boleto emitido e ainda nao pago.",
                                receivables=[receivable],
                                boleto=matched_boleto,
                            )
                        )
                        overdue_boleto_count += 1
                for boleto in client_boletos:
                    if boleto.id in used_boleto_ids:
                        continue
                    if _boleto_status_bucket(boleto) != "active":
                        continue
                    excess_boletos.append(
                        _build_excess_boleto_item(
                            client_key=client_key,
                            client_name=client_name,
                            mode=mode,
                            reason="Nao encontrei fatura em aberto no Linx com valor exato e vencimento compativel para este boleto em aberto.",
                            boletos=[boleto],
                        )
                    )
            else:
                allocations = _match_grouped_receivables(
                    client_receivables,
                    client_boletos,
                    mode=mode,
                    due_day=due_day,
                    today=today,
                    include_all_monthly=include_all_monthly_missing,
                )
                for allocation in allocations:
                    receivable_group = allocation["receivables"]
                    boleto_group = allocation["boletos"]
                    active_boleto_group = [item for item in boleto_group if _boleto_status_bucket(item) == "active"]
                    has_overdue_receivable = any(item.due_date and item.due_date < today for item in receivable_group)
                    if not allocation["matched"]:
                        if receivable_group and allocation["visible_for_missing"]:
                            reason = (
                                "O valor total dos boletos do mes nao fecha com as faturas em aberto."
                                if boleto_group
                                else "Nao encontrei boleto compativel para cobrir o valor exato do mes."
                            )
                            missing_boletos.append(
                                _build_missing_boleto_item(
                                    client_key=client_key,
                                    client_name=client_name,
                                    mode=mode,
                                    reason=reason,
                                    receivables=receivable_group,
                                )
                            )
                        if active_boleto_group:
                            reason = (
                                "Os boletos em aberto do mes nao batem com as faturas em aberto no Linx."
                                if receivable_group
                                else "Nao encontrei faturas em aberto no Linx correspondentes a este agrupamento de boletos em aberto."
                            )
                            excess_boletos.append(
                                _build_excess_boleto_item(
                                    client_key=client_key,
                                    client_name=client_name,
                                    mode=mode,
                                    reason=reason,
                                    boletos=active_boleto_group,
                                )
                            )
                        if receivable_group and has_overdue_receivable and allocation["visible_for_missing"]:
                            overdue_boletos.append(
                                _build_overdue_boleto_item(
                                    client_key=client_key,
                                    client_name=client_name,
                                    mode=mode,
                                    today=today,
                                    reason="Existem faturas vencidas sem boleto correspondente.",
                                    receivables=receivable_group,
                                    boleto=None,
                                )
                            )
                            overdue_boleto_count += 1
                        continue

                    paid_boletos = [item for item in boleto_group if _boleto_status_bucket(item) == "paid"]
                    if paid_boletos:
                        matched_paid_count += len(receivable_group)
                        paid_pending.append(
                            _build_paid_pending_item(
                                client_key=client_key,
                                client_name=client_name,
                                mode=mode,
                                receivables=receivable_group,
                                boletos=paid_boletos,
                            )
                        )

                    overdue_candidates = [
                        item
                        for item in boleto_group
                        if _boleto_status_bucket(item) == "active" and item.due_date and item.due_date < today
                    ]
                    for boleto in overdue_candidates:
                        overdue_boletos.append(
                            _build_overdue_boleto_item(
                                client_key=client_key,
                                client_name=client_name,
                                mode=mode,
                                today=today,
                                reason="Boleto agrupado vencido e ainda em aberto.",
                                receivables=receivable_group,
                                boleto=boleto,
                            )
                        )
                        overdue_boleto_count += 1

        clients.append(
            BoletoClientRead(
                client_key=client_key,
                client_name=client_name,
                client_code=client_code,
                uses_boleto=uses_boleto,
                mode=mode,
                boleto_due_day=due_day,
                include_interest=resolved_customer.include_interest,
                notes=notes,
                auto_uses_boleto=auto_uses_boleto,
                receivable_count=len(client_receivables),
                overdue_boleto_count=overdue_boleto_count,
                total_amount=sum((item.amount for item in client_receivables), Decimal("0")),
                matched_paid_count=matched_paid_count,
                address_street=resolved_customer.address_street,
                address_number=resolved_customer.address_number,
                address_complement=resolved_customer.address_complement,
                neighborhood=resolved_customer.neighborhood,
                city=resolved_customer.city,
                state=resolved_customer.state,
                zip_code=resolved_customer.zip_code,
                tax_id=resolved_customer.tax_id,
                state_registration=resolved_customer.state_registration,
                phone_primary=resolved_customer.phone_primary,
                phone_secondary=resolved_customer.phone_secondary,
                mobile=resolved_customer.mobile,
            )
        )

    return BoletoDashboardRead(
        generated_at=datetime.now().isoformat(),
        files=files,
        summary=BoletoSummaryRead(
            receivable_count=len(receivables),
            receivable_total=sum((item.amount for item in receivables), Decimal("0")),
            boleto_count=len(boleto_records),
            overdue_boleto_count=len(overdue_boletos),
            overdue_invoice_client_count=len(overdue_invoices),
            paid_pending_count=len(paid_pending),
            missing_boleto_count=len(missing_boletos),
            excess_boleto_count=len(excess_boletos),
            boleto_clients_count=boleto_clients_count,
        ),
        clients=sorted(clients, key=lambda item: item.client_name),
        receivables=sorted(
            [_serialize_receivable(item) for item in receivables],
            key=lambda item: (item.due_date or date.max, item.client_name, item.invoice_number, item.installment),
        ),
        open_boletos=open_boletos,
        overdue_boletos=sorted(overdue_boletos, key=lambda item: (item.due_date or date.max, item.client_name)),
        overdue_invoices=sorted(overdue_invoices, key=lambda item: (-item.days_overdue, -item.overdue_amount, item.client_name)),
        paid_pending=sorted(paid_pending, key=lambda item: (item.client_name, item.due_date or date.max, item.amount)),
        missing_boletos=sorted(missing_boletos, key=lambda item: (item.client_name, item.due_date or date.max, item.amount)),
        excess_boletos=sorted(excess_boletos, key=lambda item: (item.client_name, item.due_date or date.max, item.amount)),
    )


def _candidate_template_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    home = Path.home()
    candidates: list[Path] = []
    search_roots = [
        repo_root,
        repo_root / "docs",
        repo_root / "arquivos base",
        home / "OneDrive",
        home,
    ]
    patterns = [
        "Template*Cobr*Arquivo*Excel.xlsx",
        "Template*Cobr*Arquivo*Excel*.xlsx",
    ]
    required_name_parts = ("TEMPLATE", "COBR", "ARQUIVO", "EXCEL")

    def is_candidate(path: Path) -> bool:
        normalized_name = normalize_text(path.stem)
        return all(part in normalized_name for part in required_name_parts)

    for root in search_roots:
        if not root.exists():
            continue
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if path.is_file() and is_candidate(path) and path not in candidates:
                    candidates.append(path)

    if candidates:
        return candidates

    recursive_roots = [
        repo_root,
        repo_root / "docs",
        repo_root / "arquivos base",
        home / "OneDrive",
    ]
    for root in recursive_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.xlsx"):
            if path.is_file() and is_candidate(path) and path not in candidates:
                candidates.append(path)

    return candidates


def _locate_boleto_template_path() -> Path:
    candidates = _candidate_template_paths()
    if not candidates:
        raise ValueError("Nao encontrei o template de cobrancas em Excel para gerar os boletos.")
    return candidates[0]


def _build_default_boleto_template_bytes() -> bytes:
    sheet_template_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{TEMPLATE_LAST_COLUMN}{TEMPLATE_FILL_ROW}"/>
  <sheetViews>
    <sheetView workbookViewId="0"/>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Arquivo gerado automaticamente pelo sistema.</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Preencha ou importe este arquivo no portal do banco.</t></is></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>Os dados de cobranca comecam na linha 4.</t></is></c>
    </row>
    <row r="4"/>
    <row r="5"/>
  </sheetData>
</worksheet>
"""
    workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews>
    <workbookView activeTab="1"/>
  </bookViews>
  <sheets>
    <sheet name="Resumo" sheetId="1" r:id="rId1"/>
    <sheet name="{TEMPLATE_SHEET_NAME}" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""
    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1">
    <font>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border>
      <left/>
      <right/>
      <top/>
      <bottom/>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Gestor Financeiro</Application>
</Properties>
"""
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Gestor Financeiro</dc:creator>
  <cp:lastModifiedBy>Gestor Financeiro</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</dcterms:modified>
</cp:coreProperties>
"""
    summary_sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:A1"/>
  <sheetViews>
    <sheetView workbookViewId="0"/>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Use a aba de cobranca para enviar os boletos ao banco.</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_rels_xml)
        workbook.writestr("docProps/app.xml", app_xml)
        workbook.writestr("docProps/core.xml", core_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/styles.xml", styles_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", summary_sheet_xml)
        workbook.writestr("xl/worksheets/sheet2.xml", sheet_template_xml)
    return content.getvalue()


def _load_boleto_template_bytes() -> bytes:
    try:
        return _locate_boleto_template_path().read_bytes()
    except ValueError:
        return _build_default_boleto_template_bytes()


def _column_letters(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _column_sequence(last_column: str) -> list[str]:
    total = column_to_index(last_column) + 1
    return [_column_letters(index) for index in range(1, total + 1)]


def _sheet_path_from_template(workbook: zipfile.ZipFile, sheet_name: str) -> str:
    return _sheet_path_from_workbook(workbook, sheet_name)


def _style_map_from_template_row(row: ET.Element) -> dict[str, str]:
    styles: dict[str, str] = {}
    for cell in row.findall("a:c", EXCEL_NS):
        reference = cell.attrib.get("r", "")
        column = re.match(r"([A-Z]+)", reference)
        if not column:
            continue
        styles[column.group(1)] = cell.attrib.get("s", "0")
    return styles


def _make_sheet_row(
    row_number: int,
    row_attrs: dict[str, str],
    style_map: dict[str, str],
    values: dict[str, str | Decimal | int | None],
) -> ET.Element:
    row = ET.Element(f"{{{EXCEL_NS['a']}}}row", {**row_attrs, "r": str(row_number)})

    for column in _column_sequence(TEMPLATE_LAST_COLUMN):
        cell_attrs = {"r": f"{column}{row_number}"}
        style = style_map.get(column)
        if style is not None:
            cell_attrs["s"] = style

        raw_value = values.get(column)
        if raw_value in (None, ""):
            row.append(ET.Element(f"{{{EXCEL_NS['a']}}}c", cell_attrs))
            continue

        if isinstance(raw_value, Decimal):
            numeric_value = format(raw_value.quantize(Decimal("0.01")), "f")
            cell = ET.Element(f"{{{EXCEL_NS['a']}}}c", cell_attrs)
            value_node = ET.SubElement(cell, f"{{{EXCEL_NS['a']}}}v")
            value_node.text = numeric_value
            row.append(cell)
            continue

        if isinstance(raw_value, int):
            cell = ET.Element(f"{{{EXCEL_NS['a']}}}c", cell_attrs)
            value_node = ET.SubElement(cell, f"{{{EXCEL_NS['a']}}}v")
            value_node.text = str(raw_value)
            row.append(cell)
            continue

        text_value = str(raw_value)
        stripped_numeric = re.fullmatch(r"-?\d+(?:\.\d+)?", text_value)
        if stripped_numeric and column not in {"A", "C", "E", "F", "G", "H", "I", "J", "L", "M", "N", "O", "P", "R", "S", "U", "W", "Y", "AA", "AD", "AE", "AF"}:
            cell = ET.Element(f"{{{EXCEL_NS['a']}}}c", cell_attrs)
            value_node = ET.SubElement(cell, f"{{{EXCEL_NS['a']}}}v")
            value_node.text = text_value
            row.append(cell)
            continue

        cell_attrs["t"] = "inlineStr"
        cell = ET.Element(f"{{{EXCEL_NS['a']}}}c", cell_attrs)
        inline = ET.SubElement(cell, f"{{{EXCEL_NS['a']}}}is")
        text_node = ET.SubElement(inline, f"{{{EXCEL_NS['a']}}}t")
        if text_value != text_value.strip():
            text_node.set(f"{{{XML_NS}}}space", "preserve")
        text_node.text = text_value
        row.append(cell)

    return row


def _render_boleto_workbook(rows: list[MissingBoletoExportRow]) -> bytes:
    template_bytes = _load_boleto_template_bytes()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as template_file:
        sheet_path = _sheet_path_from_template(template_file, TEMPLATE_SHEET_NAME)
        sheet_root = ET.fromstring(template_file.read(sheet_path))
        sheet_data = sheet_root.find("a:sheetData", EXCEL_NS)
        if sheet_data is None:
            raise ValueError("Nao consegui localizar a estrutura da aba de cobranca no template.")

        template_fill_row = next(
            (row for row in sheet_data.findall("a:row", EXCEL_NS) if row.attrib.get("r") == str(TEMPLATE_FILL_ROW)),
            None,
        )
        if template_fill_row is None:
            raise ValueError("Nao encontrei a linha base de preenchimento no template de cobrancas.")

        template_row_attrs = {
            key: value
            for key, value in template_fill_row.attrib.items()
            if key != "r"
        }
        style_map = _style_map_from_template_row(template_fill_row)

        for row in list(sheet_data):
            row_number = int(row.attrib.get("r", "0"))
            if row_number >= TEMPLATE_DATA_START_ROW:
                sheet_data.remove(row)

        for offset, item in enumerate(rows):
            row_number = TEMPLATE_DATA_START_ROW + offset
            sheet_data.append(
                _make_sheet_row(
                    row_number,
                    template_row_attrs,
                    style_map,
                    {
                        "A": item.client_name,
                        "B": _excel_number(item.tax_id),
                        "C": None,
                        "D": None,
                        "E": item.address_street,
                        "F": item.address_number,
                        "G": item.address_complement,
                        "H": item.neighborhood,
                        "I": item.city,
                        "J": item.state,
                        "K": _excel_number(item.zip_code),
                        "L": "Não",
                        "M": None,
                        "N": None,
                        "O": "Não",
                        "P": "Boleto",
                        "Q": item.amount,
                        "R": item.charge_code,
                        "S": item.description,
                        "T": _excel_number(format_excel_date(item.due_date)),
                        "U": "Sim",
                        "V": 30,
                        "W": "Porcentagem (%)" if item.include_interest else "Não aplicar multa",
                        "X": 2 if item.include_interest else 0,
                        "Y": "Taxa (% a.m.)" if item.include_interest else "Não aplicar juros",
                        "Z": 1 if item.include_interest else 0,
                        "AA": "Não aplicar desconto",
                        "AB": 0,
                        "AC": 0,
                        "AD": "Não",
                        "AE": None,
                        "AF": None,
                        "AG": None,
                        "AH": None,
                        "AI": None,
                        "AJ": None,
                    },
                )
            )

        dimension = sheet_root.find("a:dimension", EXCEL_NS)
        if dimension is not None:
            last_row = TEMPLATE_DATA_START_ROW + max(len(rows) - 1, 0)
            dimension.set("ref", f"A1:{TEMPLATE_LAST_COLUMN}{last_row}")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as generated_file:
            for info in template_file.infolist():
                content = template_file.read(info.filename)
                if info.filename == sheet_path:
                    content = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)
                generated_file.writestr(info, content)

    return output.getvalue()


def _validate_export_client_config(customer_data: ResolvedCustomerData | None, client_name: str) -> list[str]:
    if customer_data is None:
        return ["cadastro do cliente nao localizado"]

    missing: list[str] = []
    tax_id = _digits_only(customer_data.tax_id)
    if len(tax_id) not in {11, 14}:
        missing.append("CPF/CNPJ")
    if not _truncate_text(customer_data.address_street, 200):
        missing.append("endereco")
    if not _truncate_text(customer_data.address_number, 40):
        missing.append("numero")
    if not _truncate_text(customer_data.neighborhood, 120):
        missing.append("bairro")
    if not _truncate_text(customer_data.city, 120):
        missing.append("cidade")
    if len(_truncate_text(customer_data.state, 10)) != 2:
        missing.append("estado")
    if len(_digits_only(customer_data.zip_code)) != 8:
        missing.append("CEP")
    return missing


def _resolve_export_due_date(item: BoletoMatchItem, customer_data: ResolvedCustomerData | None, today: date) -> date:
    reference_due_date = item.due_date or today
    resolved_due_day: int | None = None
    if customer_data and customer_data.mode != "individual":
        if customer_data.boleto_due_day:
            resolved_due_day = customer_data.boleto_due_day
        elif customer_data.mode == "mensal":
            resolved_due_day = 20

    if resolved_due_day:
        last_day = calendar.monthrange(reference_due_date.year, reference_due_date.month)[1]
        resolved_due_date = date(
            reference_due_date.year,
            reference_due_date.month,
            min(resolved_due_day, last_day),
        )
    else:
        resolved_due_date = reference_due_date

    if resolved_due_date < today:
        return today
    return resolved_due_date


def _build_export_charge_code(item: BoletoMatchItem, client_code: str | None, include_interest: bool) -> str:
    del client_code, include_interest
    if item.type == "agrupado":
        competence = (item.competence or "").replace("-", "")
        if competence:
            return competence[:15]
    if item.receivables:
        invoice_number = (item.receivables[0].invoice_number or "").strip()
        if invoice_number:
            return invoice_number[:15]
    return item.selection_key[:15].upper()


def _build_export_description(item: BoletoMatchItem) -> str:
    del item
    return ""


def build_missing_boletos_export(
    db: Session,
    company: Company,
    selection_keys: list[str],
) -> tuple[bytes, str]:
    normalized_selection_keys = [item.strip() for item in selection_keys if item and item.strip()]
    if not normalized_selection_keys:
        raise ValueError("Selecione ao menos um boleto faltando para gerar o arquivo.")

    dashboard = build_boleto_dashboard(db, company, include_all_monthly_missing=True)
    selected_items = [item for item in dashboard.missing_boletos if item.selection_key in normalized_selection_keys]
    if len(selected_items) != len(set(normalized_selection_keys)):
        raise ValueError("Alguns boletos selecionados nao foram encontrados. Atualize a tela e tente novamente.")

    config_map = _load_customer_configs(db, company.id)
    customer_lookup = _build_linx_customer_lookup(db, company.id)
    validation_errors: list[str] = []
    export_rows: list[MissingBoletoExportRow] = []
    today = date.today()

    for item in selected_items:
        config = config_map.get(item.client_key)
        receivable_client_code = item.receivables[0].client_code if item.receivables else None
        customer_data = _resolve_customer_data(
            client_key=item.client_key,
            client_name=item.client_name,
            client_code=receivable_client_code or (config.client_code if config else None),
            config=config,
            customer_lookup=customer_lookup,
            auto_uses_boleto=bool(config.uses_boleto) if config else False,
        )
        missing_fields = _validate_export_client_config(customer_data, item.client_name)
        if missing_fields:
            validation_errors.append(f"{item.client_name}: {', '.join(missing_fields)}")
            continue

        tax_id = _digits_only(customer_data.tax_id)
        zip_code = _digits_only(customer_data.zip_code)
        phone = _digits_only(customer_data.mobile or customer_data.phone_primary or customer_data.phone_secondary)
        due_date = _resolve_export_due_date(item, customer_data, today)
        include_interest = bool(customer_data.include_interest)

        export_rows.append(
            MissingBoletoExportRow(
                client_name=_truncate_text(item.client_name, 100),
                tax_id=tax_id,
                email=None,
                phone=phone[:11] or None,
                address_street=_truncate_text(customer_data.address_street, 54),
                address_number=_truncate_text(customer_data.address_number, 32),
                address_complement=_truncate_text(customer_data.address_complement, 30) or None,
                neighborhood=_truncate_text(customer_data.neighborhood, 60),
                city=_truncate_text(customer_data.city, 60),
                state=_truncate_text(customer_data.state, 2).upper(),
                zip_code=zip_code[:8],
                amount=Decimal(item.amount),
                include_interest=include_interest,
                charge_code=_build_export_charge_code(item, customer_data.client_code, include_interest),
                description=_build_export_description(item),
                due_date=due_date,
            )
        )

    if validation_errors:
        raise ValueError(
            "Complete os dados obrigatorios dos clientes antes de gerar os boletos: "
            + "; ".join(sorted(validation_errors))
        )

    content = _render_boleto_workbook(export_rows)
    filename = f"boletos-emissao-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    return content, filename

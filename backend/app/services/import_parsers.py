import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from xml.etree import ElementTree


def fingerprint_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", ascii_only.lower())


def parse_decimal_pt_br(raw: str) -> Decimal:
    value = raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
    if not value or value == "-":
        return Decimal("0.00")
    return Decimal(value)


def parse_decimal_mixed(raw: str) -> Decimal:
    value = (raw or "").replace("R$", "").strip()
    if not value or value == "-":
        return Decimal("0.00")
    if "," in value:
        return parse_decimal_pt_br(value)
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0.00")


def parse_date_br(raw: str):
    value = raw.strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_date_flexible(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    parsed_br = parse_date_br(value)
    if parsed_br:
        return parsed_br
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._current: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"td", "th"}:
            self._in_cell = True
            self._current = []
        elif tag == "tr":
            self._row = []
        elif tag == "br" and self._in_cell:
            self._current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            text = re.sub(r"\s+", " ", "".join(self._current)).strip()
            self._row.append(text)
            self._in_cell = False
            self._current = []
        elif tag == "tr":
            if any(cell for cell in self._row):
                self.rows.append(self._row)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current.append(data)


def parse_html_rows(content: bytes) -> list[list[str]]:
    parser = HtmlTableParser()
    parser.feed(content.decode("utf-8", errors="ignore"))
    return parser.rows


@dataclass(slots=True)
class ParsedSalesRow:
    snapshot_date: date
    gross_revenue: Decimal
    cash_revenue: Decimal
    check_sight_revenue: Decimal
    check_term_revenue: Decimal
    inhouse_credit_revenue: Decimal
    card_revenue: Decimal
    convenio_revenue: Decimal
    pix_revenue: Decimal
    financing_revenue: Decimal
    markup: Decimal
    discount_or_surcharge: Decimal


def parse_sales_rows(content: bytes) -> list[ParsedSalesRow]:
    rows = parse_html_rows(content)
    header_index = next(
        (
            idx
            for idx, row in enumerate(rows)
            if [normalize_label(cell) for cell in row[:3]]
            == ["emissao", "valordosdocumentos", "dinheiro"]
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Cabecalho de faturamento Linx nao encontrado")

    parsed: list[ParsedSalesRow] = []
    for row in rows[header_index + 1 :]:
        if not row or normalize_label(row[0]).startswith("totais"):
            break
        snapshot_date = parse_date_br(row[0])
        if not snapshot_date:
            continue
        values = row + [""] * (12 - len(row))
        parsed.append(
            ParsedSalesRow(
                snapshot_date=snapshot_date,
                gross_revenue=parse_decimal_pt_br(values[1]),
                cash_revenue=parse_decimal_pt_br(values[2]),
                check_sight_revenue=parse_decimal_pt_br(values[3]),
                check_term_revenue=parse_decimal_pt_br(values[4]),
                inhouse_credit_revenue=parse_decimal_pt_br(values[5]),
                card_revenue=parse_decimal_pt_br(values[6]),
                convenio_revenue=parse_decimal_pt_br(values[7]),
                pix_revenue=parse_decimal_pt_br(values[8]),
                financing_revenue=parse_decimal_pt_br(values[9]),
                markup=parse_decimal_pt_br(values[10]),
                discount_or_surcharge=parse_decimal_pt_br(values[11]),
            )
        )
    return parsed


@dataclass(slots=True)
class ParsedReceivableRow:
    issue_date: date | None
    due_date: date | None
    invoice_number: str | None
    company_code: str | None
    installment_label: str | None
    original_amount: Decimal
    amount_with_interest: Decimal
    customer_name: str
    document_reference: str | None
    status: str
    seller_name: str | None


LINX_RECEIVABLE_ZIP_PASSWORD = b"130921"
LINX_RECEIVABLE_SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".html", ".htm")


def prepare_linx_receivables_payload(filename: str, content: bytes) -> tuple[str, bytes]:
    normalized_filename = (filename or "").lower()
    if not normalized_filename.endswith(".zip"):
        return filename, content

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            candidate_names = [
                item.filename
                for item in archive.infolist()
                if not item.is_dir()
                and item.filename
                and item.filename.lower().endswith(LINX_RECEIVABLE_SUPPORTED_EXTENSIONS)
            ]
            if not candidate_names:
                raise ValueError("Nenhuma planilha valida foi encontrada dentro do ZIP do LINX.")

            candidate_names.sort(
                key=lambda item: (
                    0 if item.lower().endswith(".xlsx") else 1,
                    0 if "completo" in item.lower() else 1,
                    item.lower(),
                )
            )
            selected_name = candidate_names[0]
            try:
                extracted = archive.read(selected_name, pwd=LINX_RECEIVABLE_ZIP_PASSWORD)
            except RuntimeError:
                extracted = archive.read(selected_name)
            display_name = selected_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            return display_name, extracted
    except zipfile.BadZipFile as error:
        raise ValueError("Arquivo ZIP do LINX invalido ou corrompido.") from error


def _parse_receivable_rows_xlsx(content: bytes) -> list[ParsedReceivableRow]:
    workbook = _read_xlsx_workbook(content)
    if not workbook:
        raise ValueError("Planilha XLSX de faturas a receber vazia.")

    for _sheet_name, rows in workbook:
        if not rows:
            continue

        header_row = rows[0]
        header_map = {
            normalize_label(value): column
            for column, value in header_row.items()
            if (value or "").strip()
        }
        if "cliente" not in header_map or "vencimento" not in header_map or "valor" not in header_map:
            continue

        def cell_value(row: dict[str, str], *labels: str) -> str:
            for label in labels:
                column = header_map.get(normalize_label(label))
                if column and row.get(column):
                    return row[column].strip()
            return ""

        parsed: list[ParsedReceivableRow] = []
        for row in rows[1:]:
            customer_name = cell_value(row, "CLIENTE")
            if not customer_name:
                continue

            issue_date = parse_date_flexible(cell_value(row, "EMISSÃO", "EMISSAO"))
            due_date = parse_date_flexible(cell_value(row, "VENCIMENTO"))
            original_amount = parse_decimal_mixed(cell_value(row, "VALOR"))
            received_amount = parse_decimal_mixed(cell_value(row, "VALOR RECEBIDO"))
            amount_with_interest = received_amount if received_amount > Decimal("0.00") else original_amount

            parsed.append(
                ParsedReceivableRow(
                    issue_date=issue_date,
                    due_date=due_date,
                    invoice_number=cell_value(row, "IDENTIFICADOR") or None,
                    company_code=cell_value(row, "CÓD. COBRANCA", "COD. COBRANCA", "CÓD COBRANCA", "COD COBRANCA")
                    or None,
                    installment_label=cell_value(row, "COBRANCA") or None,
                    original_amount=original_amount,
                    amount_with_interest=amount_with_interest,
                    customer_name=customer_name,
                    document_reference=cell_value(row, "FINALIDADE") or None,
                    status=cell_value(row, "STATUS") or "Em aberto",
                    seller_name=None,
                )
            )
        if parsed:
            return parsed

    raise ValueError("Cabecalho de faturas a receber nao encontrado no XLSX.")


def parse_receivable_rows(content: bytes) -> list[ParsedReceivableRow]:
    if content[:2] == b"PK":
        return _parse_receivable_rows_xlsx(content)

    rows = parse_html_rows(content)
    header_index = next(
        (
            idx
            for idx, row in enumerate(rows)
            if normalize_label("".join(row[:4])).startswith("emissaofaturaempresavencparc")
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Cabecalho de faturas a receber nao encontrado")

    parsed: list[ParsedReceivableRow] = []
    for row in rows[header_index + 1 :]:
        first = row[0] if row else ""
        label = normalize_label(first)
        if label.startswith("grupo"):
            continue
        if label.startswith("vendedor"):
            if parsed:
                parsed[-1].seller_name = first.split(":", 1)[-1].strip()
            continue
        if len(row) < 9:
            continue
        issue_date = parse_date_br(row[0])
        if not issue_date:
            continue
        invoice_parts = row[1].split("|")
        parsed.append(
            ParsedReceivableRow(
                issue_date=issue_date,
                due_date=parse_date_br(row[2]),
                invoice_number=invoice_parts[0].strip() if invoice_parts else None,
                company_code=invoice_parts[1].strip() if len(invoice_parts) > 1 else None,
                installment_label=row[3].strip() or None,
                original_amount=parse_decimal_pt_br(row[4]),
                amount_with_interest=parse_decimal_pt_br(row[5]),
                customer_name=row[6].strip(),
                document_reference=row[7].strip() or None,
                status=row[8].strip() or "Em aberto",
                seller_name=None,
            )
        )
    return parsed


@dataclass(slots=True)
class ParsedOfxTransaction:
    bank_name: str | None
    bank_code: str | None
    posted_at: date
    trn_type: str
    amount: Decimal
    fit_id: str
    check_number: str | None
    reference_number: str | None
    memo: str | None
    name: str | None
    raw_payload: str


def parse_ofx_transactions(content: bytes) -> list[ParsedOfxTransaction]:
    text = content.decode("latin1", errors="ignore")

    def extract(section: str, tag: str) -> str | None:
        match = re.search(fr"<{tag}>([^<\r\n]+)", section)
        return match.group(1).strip() if match else None

    bank_name = extract(text, "ORG")
    bank_code = extract(text, "FID") or extract(text, "BANKID")

    parsed: list[ParsedOfxTransaction] = []
    for match in re.finditer(r"<STMTTRN>(.*?)</STMTTRN>", text, re.S):
        block = match.group(1)
        posted_at_raw = extract(block, "DTPOSTED")
        fit_id = extract(block, "FITID")
        amount_raw = extract(block, "TRNAMT")
        trn_type = extract(block, "TRNTYPE")
        if not posted_at_raw or not fit_id or not amount_raw or not trn_type:
            continue
        posted_at = datetime.strptime(posted_at_raw[:8], "%Y%m%d").date()
        parsed.append(
            ParsedOfxTransaction(
                bank_name=bank_name,
                bank_code=bank_code,
                posted_at=posted_at,
                trn_type=trn_type,
                amount=Decimal(amount_raw),
                fit_id=fit_id,
                check_number=extract(block, "CHECKNUM"),
                reference_number=extract(block, "REFNUM"),
                memo=extract(block, "MEMO"),
                name=extract(block, "NAME"),
                raw_payload=block.strip(),
            )
        )
    return parsed


EXCEL_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EXCEL_DATE_FORMAT_IDS = {14, 15, 16, 17, 22, 27, 30, 36, 45, 46, 47, 50, 57}
EXCEL_EPOCH = datetime(1899, 12, 30)


def _excel_serial_to_date(raw: str) -> date | None:
    try:
        serial = float(raw)
    except (TypeError, ValueError):
        return None
    return (EXCEL_EPOCH + timedelta(days=serial)).date()


def _read_xlsx_workbook(content: bytes) -> list[tuple[str, list[dict[str, str]]]]:
    with zipfile.ZipFile(io.BytesIO(content)) as workbook_zip:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ElementTree.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for shared_item in shared_root.findall("a:si", EXCEL_NS):
                shared_strings.append(
                    "".join(text.text or "" for text in shared_item.findall(".//a:t", EXCEL_NS))
                )

        style_root = ElementTree.fromstring(workbook_zip.read("xl/styles.xml"))
        custom_formats = {
            int(numfmt.attrib["numFmtId"]): numfmt.attrib["formatCode"]
            for numfmt in style_root.findall("a:numFmts/a:numFmt", EXCEL_NS)
        }
        cell_style_formats = [
            int(cell_style.attrib.get("numFmtId", 0))
            for cell_style in style_root.findall("a:cellXfs/a:xf", EXCEL_NS)
        ]

        workbook_root = ElementTree.fromstring(workbook_zip.read("xl/workbook.xml"))
        relationship_root = ElementTree.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationship_root
        }

        workbook_rows: list[tuple[str, list[dict[str, str]]]] = []
        for sheet in workbook_root.findall("a:sheets/a:sheet", EXCEL_NS):
            sheet_name = sheet.attrib["name"]
            relation_id = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            sheet_target = relationship_map.get(relation_id)
            if not sheet_target:
                continue

            sheet_root = ElementTree.fromstring(workbook_zip.read(f"xl/{sheet_target}"))
            parsed_rows: list[dict[str, str]] = []
            for row in sheet_root.findall(".//a:sheetData/a:row", EXCEL_NS):
                parsed_row: dict[str, str] = {}
                for cell in row.findall("a:c", EXCEL_NS):
                    cell_reference = cell.attrib.get("r", "")
                    column = re.match(r"[A-Z]+", cell_reference)
                    if not column:
                        continue
                    parsed_row[column.group(0)] = _read_xlsx_cell_value(
                        cell=cell,
                        shared_strings=shared_strings,
                        cell_style_formats=cell_style_formats,
                        custom_formats=custom_formats,
                    )
                if parsed_row:
                    parsed_rows.append(parsed_row)
            workbook_rows.append((sheet_name, parsed_rows))
    return workbook_rows


def _read_xlsx_cell_value(
    cell,
    shared_strings: list[str],
    cell_style_formats: list[int],
    custom_formats: dict[int, str],
) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", EXCEL_NS))

    value_node = cell.find("a:v", EXCEL_NS)
    if value_node is None:
        return ""

    raw_value = value_node.text or ""
    if cell_type == "s":
        return shared_strings[int(raw_value)]

    style_index = int(cell.attrib.get("s", 0))
    number_format_id = cell_style_formats[style_index] if style_index < len(cell_style_formats) else 0
    format_code = custom_formats.get(number_format_id, "")
    if (
        number_format_id in EXCEL_DATE_FORMAT_IDS
        or "yy" in format_code.lower()
        or "dd" in format_code.lower()
    ):
        parsed_date = _excel_serial_to_date(raw_value)
        if parsed_date:
            return parsed_date.isoformat()

    return raw_value


@dataclass(slots=True)
class ParsedHistoricalCashbookRow:
    format_version: str
    sheet_row_number: int
    sheet_name: str
    source_account: str | None
    source_reference: str | None
    entry_type: str | None
    status: str | None
    title: str | None
    description: str | None
    notes: str | None
    counterparty_name: str | None
    document_number: str | None
    issue_date: date | None
    competence_date: date | None
    due_date: date | None
    settled_at: datetime | date | None
    principal_amount: Decimal | None
    interest_amount: Decimal | None
    discount_amount: Decimal | None
    penalty_amount: Decimal | None
    total_amount: Decimal | None
    paid_amount: Decimal | None
    expected_amount: Decimal | None
    category_code: str | None
    category_name: str | None
    interest_category_code: str | None
    interest_category_name: str | None
    supplier_name: str | None
    supplier_document_number: str | None
    collection_name: str | None
    launch_number: str | None
    reference: str | None
    history: str | None
    debit_amount: Decimal | None
    credit_amount: Decimal | None
    balance_amount: Decimal | None
    balance_side: str | None


STRUCTURED_HISTORICAL_CASHBOOK_HEADERS = {
    "source_reference": {"sourcereference"},
    "entry_type": {"entrytype"},
    "status": {"status"},
    "title": {"title"},
    "description": {"description"},
    "notes": {"notes"},
    "counterparty_name": {"counterpartyname"},
    "document_number": {"documentnumber"},
    "issue_date": {"issuedate"},
    "competence_date": {"competencedate"},
    "due_date": {"duedate"},
    "settled_at": {"settledat"},
    "category_code": {"categorycode"},
    "category_name": {"categoryname"},
    "interest_category_code": {"interestcategorycode"},
    "interest_category_name": {"interestcategoryname"},
    "supplier_name": {"suppliername"},
    "supplier_document_number": {"supplierdocumentnumber"},
    "collection_name": {"collectionname"},
    "principal_amount": {"principalamount"},
    "interest_amount": {"interestamount"},
    "discount_amount": {"discountamount"},
    "penalty_amount": {"penaltyamount"},
    "total_amount": {"totalamount"},
    "paid_amount": {"paidamount"},
    "expected_amount": {"expectedamount"},
}
STRUCTURED_HISTORICAL_REQUIRED_HEADERS = {"title", "due_date"}


def _parse_structured_historical_header(row: dict[str, str]) -> dict[str, str] | None:
    header_map: dict[str, str] = {}
    for column, raw_value in row.items():
        normalized = normalize_label(raw_value or "")
        if not normalized:
            continue
        for field_name, aliases in STRUCTURED_HISTORICAL_CASHBOOK_HEADERS.items():
            if normalized in aliases:
                header_map[field_name] = column
                break
    if not STRUCTURED_HISTORICAL_REQUIRED_HEADERS.issubset(header_map):
        return None
    if "category_code" not in header_map and "category_name" not in header_map:
        return None
    return header_map


def _parse_structured_historical_date(
    raw_value: str,
    *,
    field_label: str,
    sheet_name: str,
    sheet_row_number: int,
) -> date | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    parsed = parse_date_flexible(value)
    if parsed is None:
        raise ValueError(
            f"Aba '{sheet_name}', linha {sheet_row_number}: {field_label} invalida ('{value}')."
        )
    return parsed


def _parse_structured_historical_datetime(
    raw_value: str,
    *,
    field_label: str,
    sheet_name: str,
    sheet_row_number: int,
) -> datetime | date | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    parsed_date = parse_date_flexible(value)
    if parsed_date is not None:
        return parsed_date
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Aba '{sheet_name}', linha {sheet_row_number}: {field_label} invalido ('{value}')."
        ) from error


def _parse_structured_historical_decimal(
    raw_value: str,
    *,
    field_label: str,
    sheet_name: str,
    sheet_row_number: int,
    default_zero: bool = False,
) -> Decimal | None:
    value = (raw_value or "").strip()
    if not value:
        return Decimal("0.00") if default_zero else None
    try:
        return parse_decimal_mixed(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(
            f"Aba '{sheet_name}', linha {sheet_row_number}: {field_label} invalido ('{value}')."
        ) from error


def _parse_structured_historical_cashbook_rows(
    workbook: list[tuple[str, list[dict[str, str]]]],
) -> list[ParsedHistoricalCashbookRow]:
    parsed: list[ParsedHistoricalCashbookRow] = []

    for sheet_name, rows in workbook:
        if not rows:
            continue
        header_map = _parse_structured_historical_header(rows[0])
        if header_map is None:
            continue

        for row_index, row in enumerate(rows[1:], start=2):
            def cell(field_name: str) -> str:
                column = header_map.get(field_name)
                return (row.get(column or "", "") or "").strip()

            if not any(cell(field_name) for field_name in header_map):
                continue

            parsed.append(
                ParsedHistoricalCashbookRow(
                    format_version="structured",
                    sheet_row_number=row_index,
                    sheet_name=sheet_name,
                    source_account=None,
                    source_reference=cell("source_reference") or None,
                    entry_type=cell("entry_type") or None,
                    status=cell("status") or None,
                    title=cell("title") or None,
                    description=cell("description") or None,
                    notes=cell("notes") or None,
                    counterparty_name=cell("counterparty_name") or None,
                    document_number=cell("document_number") or None,
                    issue_date=_parse_structured_historical_date(
                        cell("issue_date"),
                        field_label="issue_date",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    competence_date=_parse_structured_historical_date(
                        cell("competence_date"),
                        field_label="competence_date",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    due_date=_parse_structured_historical_date(
                        cell("due_date"),
                        field_label="due_date",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    settled_at=_parse_structured_historical_datetime(
                        cell("settled_at"),
                        field_label="settled_at",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    principal_amount=_parse_structured_historical_decimal(
                        cell("principal_amount"),
                        field_label="principal_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    interest_amount=_parse_structured_historical_decimal(
                        cell("interest_amount"),
                        field_label="interest_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                        default_zero=True,
                    ),
                    discount_amount=_parse_structured_historical_decimal(
                        cell("discount_amount"),
                        field_label="discount_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                        default_zero=True,
                    ),
                    penalty_amount=_parse_structured_historical_decimal(
                        cell("penalty_amount"),
                        field_label="penalty_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                        default_zero=True,
                    ),
                    total_amount=_parse_structured_historical_decimal(
                        cell("total_amount"),
                        field_label="total_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    paid_amount=_parse_structured_historical_decimal(
                        cell("paid_amount"),
                        field_label="paid_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    expected_amount=_parse_structured_historical_decimal(
                        cell("expected_amount"),
                        field_label="expected_amount",
                        sheet_name=sheet_name,
                        sheet_row_number=row_index,
                    ),
                    category_code=cell("category_code") or None,
                    category_name=cell("category_name") or None,
                    interest_category_code=cell("interest_category_code") or None,
                    interest_category_name=cell("interest_category_name") or None,
                    supplier_name=cell("supplier_name") or None,
                    supplier_document_number=cell("supplier_document_number") or None,
                    collection_name=cell("collection_name") or None,
                    launch_number=None,
                    reference=None,
                    history=None,
                    debit_amount=None,
                    credit_amount=None,
                    balance_amount=None,
                    balance_side=None,
                )
            )

        return parsed

    return []


def _parse_legacy_historical_cashbook_rows(
    workbook: list[tuple[str, list[dict[str, str]]]],
) -> list[ParsedHistoricalCashbookRow]:
    parsed: list[ParsedHistoricalCashbookRow] = []

    for sheet_name, rows in workbook:
        if not sheet_name.isdigit():
            continue
        if not 2020 <= int(sheet_name) <= 2025:
            continue

        current_account: str | None = None
        for row_index, row in enumerate(rows, start=1):
            first_cell = (row.get("A") or "").strip()
            if first_cell.startswith("Conta: "):
                current_account = first_cell.replace("Conta: ", "", 1).strip()
                continue

            history = re.sub(r"\s+", " ", (row.get("E") or "")).strip()
            if not history or normalize_label(history) == "historico":
                continue
            if (row.get("G") or "").strip() == "Sld Anterior":
                continue

            entry_date_raw = (row.get("A") or "").strip()
            entry_date = None
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry_date_raw):
                entry_date = datetime.strptime(entry_date_raw, "%Y-%m-%d").date()
            else:
                entry_date = parse_date_br(entry_date_raw)
            if not entry_date:
                continue

            debit_amount = parse_decimal_mixed(row.get("F", ""))
            credit_amount = parse_decimal_mixed(row.get("G", ""))
            amount = debit_amount if debit_amount >= credit_amount else credit_amount

            parsed.append(
                ParsedHistoricalCashbookRow(
                    format_version="legacy",
                    sheet_row_number=row_index,
                    sheet_name=sheet_name,
                    source_account=current_account or "Conta nao identificada",
                    source_reference=None,
                    entry_type=None,
                    status="settled",
                    title=history,
                    description=None,
                    notes=None,
                    counterparty_name=None,
                    document_number=(row.get("C") or "").strip() or None,
                    issue_date=entry_date,
                    competence_date=entry_date,
                    due_date=entry_date,
                    settled_at=entry_date,
                    principal_amount=amount,
                    interest_amount=Decimal("0.00"),
                    discount_amount=Decimal("0.00"),
                    penalty_amount=Decimal("0.00"),
                    total_amount=amount,
                    paid_amount=amount,
                    expected_amount=None,
                    category_code=None,
                    category_name=None,
                    interest_category_code=None,
                    interest_category_name=None,
                    supplier_name=None,
                    supplier_document_number=None,
                    collection_name=None,
                    launch_number=(row.get("B") or "").strip() or None,
                    reference=(row.get("D") or "").strip() or None,
                    history=history,
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    balance_amount=parse_decimal_mixed(row.get("H", "")) if row.get("H") else None,
                    balance_side=(row.get("I") or "").strip() or None,
                )
            )

    return parsed


def parse_historical_cashbook_rows(content: bytes) -> list[ParsedHistoricalCashbookRow]:
    workbook = _read_xlsx_workbook(content)
    structured_rows = _parse_structured_historical_cashbook_rows(workbook)
    if structured_rows:
        return structured_rows
    return _parse_legacy_historical_cashbook_rows(workbook)

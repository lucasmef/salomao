from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import text

from app.db.session import SessionLocal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exporta categorias e grupos com quantidade de lancamentos em XLSX."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Arquivo XLSX de saida. Usa um nome com timestamp por padrao.",
    )
    parser.add_argument(
        "--company-id",
        default=None,
        help="ID da empresa. Se omitido, usa a empresa mais antiga cadastrada.",
    )
    return parser


def excel_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def inline_string_cell(cell_ref: str, value: str) -> str:
    escaped = xml_escape(value)
    if value[:1].isspace() or value[-1:].isspace():
        return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def number_cell(cell_ref: str, value: int | float | Decimal) -> str:
    return f'<c r="{cell_ref}"><v>{value}</v></c>'


def worksheet_xml(rows: list[list[object]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{excel_column_name(column_index)}{row_index}"
            if value is None:
                cells.append(inline_string_cell(cell_ref, ""))
            elif isinstance(value, bool):
                cells.append(inline_string_cell(cell_ref, "Sim" if value else "Nao"))
            elif isinstance(value, (int, float, Decimal)):
                cells.append(number_cell(cell_ref, value))
            else:
                cells.append(inline_string_cell(cell_ref, str(value)))
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    )


def workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        (
            f'<sheet name="{xml_escape(name)}" sheetId="{index}" '
            f'r:id="rId{index}"/>'
        )
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def workbook_rels_xml(sheet_count: int) -> str:
    relationships = "".join(
        (
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationships}"
        "</Relationships>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def content_types_xml(sheet_count: int) -> str:
    overrides = "".join(
        (
            '<Override '
            f'PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{overrides}"
        "</Types>"
    )


def write_xlsx(output_path: Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", content_types_xml(len(sheets)))
        xlsx.writestr("_rels/.rels", root_rels_xml())
        xlsx.writestr("xl/workbook.xml", workbook_xml([sheet_name for sheet_name, _ in sheets]))
        xlsx.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheets)))
        for index, (_, rows) in enumerate(sheets, start=1):
            xlsx.writestr(f"xl/worksheets/sheet{index}.xml", worksheet_xml(rows))


def resolve_company_id(db, company_id: str | None) -> tuple[str, str]:
    if company_id:
        row = db.execute(
            text(
                """
                select id, trade_name
                from companies
                where id = :company_id
                limit 1
                """
            ),
            {"company_id": company_id},
        ).first()
        if row is None:
            raise SystemExit(f"Empresa nao encontrada: {company_id}")
        return row.id, row.trade_name

    row = db.execute(
        text(
            """
            select id, trade_name
            from companies
            order by created_at asc
            limit 1
            """
        )
    ).first()
    if row is None:
        raise SystemExit("Nenhuma empresa cadastrada.")
    return row.id, row.trade_name


def fetch_category_rows(db, company_id: str) -> list[tuple]:
    return list(
        db.execute(
            text(
                """
                select
                    c.code,
                    c.entry_kind,
                    c.report_group,
                    c.report_subgroup,
                    c.name,
                    c.is_active,
                    count(fe.id) as entry_count
                from categories c
                left join financial_entries fe
                    on fe.category_id = c.id
                    and coalesce(fe.is_deleted, false) = false
                where c.company_id = :company_id
                group by
                    c.code,
                    c.entry_kind,
                    c.report_group,
                    c.report_subgroup,
                    c.name,
                    c.is_active
                order by
                    c.report_group nulls first,
                    c.report_subgroup nulls first,
                    c.name asc
                """
            ),
            {"company_id": company_id},
        ).fetchall()
    )


def fetch_group_rows(db, company_id: str) -> list[tuple]:
    return list(
        db.execute(
            text(
                """
                select
                    c.report_group,
                    c.report_subgroup,
                    count(*) as category_count,
                    sum(case when c.is_active then 1 else 0 end) as active_category_count,
                    coalesce(count(fe.id), 0) as entry_count
                from categories c
                left join financial_entries fe
                    on fe.category_id = c.id
                    and coalesce(fe.is_deleted, false) = false
                where c.company_id = :company_id
                group by c.report_group, c.report_subgroup
                order by
                    c.report_group nulls first,
                    c.report_subgroup nulls first
                """
            ),
            {"company_id": company_id},
        ).fetchall()
    )


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"categorias-grupos-main-prod-{timestamp}.xlsx"


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output).resolve() if args.output else default_output_path()

    with SessionLocal() as db:
        company_id, company_name = resolve_company_id(db, args.company_id)
        category_rows = fetch_category_rows(db, company_id)
        group_rows = fetch_group_rows(db, company_id)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    categories_sheet: list[list[object]] = [
        [
            "codigo",
            "tipo",
            "grupo",
            "subgrupo",
            "categoria",
            "ativo",
            "quantidade_lancamentos",
        ]
    ]
    for row in category_rows:
        categories_sheet.append(
            [
                row.code or "",
                row.entry_kind or "",
                row.report_group or "",
                row.report_subgroup or "",
                row.name or "",
                bool(row.is_active),
                int(row.entry_count or 0),
            ]
        )

    groups_sheet: list[list[object]] = [
        [
            "grupo",
            "subgrupo",
            "quantidade_categorias",
            "quantidade_categorias_ativas",
            "quantidade_lancamentos",
        ]
    ]
    for row in group_rows:
        groups_sheet.append(
            [
                row.report_group or "",
                row.report_subgroup or "",
                int(row.category_count or 0),
                int(row.active_category_count or 0),
                int(row.entry_count or 0),
            ]
        )

    metadata_sheet: list[list[object]] = [
        ["campo", "valor"],
        ["empresa_id", company_id],
        ["empresa", company_name],
        ["gerado_em", generated_at],
        ["total_categorias", len(category_rows)],
        ["total_grupos_subgrupos", len(group_rows)],
        ["total_lancamentos_categorizados", sum(int(row.entry_count or 0) for row in category_rows)],
    ]

    write_xlsx(
        output_path,
        [
            ("Categorias", categories_sheet),
            ("Grupos", groups_sheet),
            ("Resumo", metadata_sheet),
        ],
    )
    print(output_path)


if __name__ == "__main__":
    main()

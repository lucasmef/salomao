from __future__ import annotations

from io import BytesIO

from app.schemas.reports import DreReport, DroReport, ReportTreeNode, ReportsOverview


def _money(value) -> str:
    return f"{value:.2f}"


def _flatten_tree(nodes: list[ReportTreeNode], prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for node in nodes:
        code = f"{node.code} " if node.code else ""
        rows.append((f"{prefix}{code}{node.label}", _money(node.amount)))
        if node.children:
            rows.extend(_flatten_tree(node.children, prefix=prefix + "  "))
    return rows


def _selected_report(report: ReportsOverview, kind: str) -> DreReport | DroReport:
    return report.dre if kind == "dre" else report.dro


def build_reports_csv(report: ReportsOverview, kind: str) -> bytes:
    selected = _selected_report(report, kind)
    lines = ["periodo;linha;valor"]
    for label, amount in _flatten_tree(selected.statement):
        lines.append(f"{selected.period_label};{label};{amount}")
    return "\n".join(lines).encode("utf-8")


def build_reports_xls(report: ReportsOverview, kind: str) -> bytes:
    selected = _selected_report(report, kind)
    rows = [
        f"<tr><td>{selected.period_label}</td><td>{label}</td><td>{amount}</td></tr>"
        for label, amount in _flatten_tree(selected.statement)
    ]
    html = (
        "<html><head><meta charset='utf-8'></head><body>"
        "<table border='1'><tr><th>Periodo</th><th>Linha</th><th>Valor</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
    return html.encode("utf-8")


def build_reports_pdf(report: ReportsOverview, kind: str) -> bytes:
    selected = _selected_report(report, kind)
    lines = ["Gestor Financeiro", "Relatorio " + kind.upper(), selected.period_label, ""]
    for label, amount in _flatten_tree(selected.statement):
        lines.append(f"{label}: {amount}")
    return _simple_pdf(lines)


def _simple_pdf(lines: list[str]) -> bytes:
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    contents = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    first = True
    for line in escaped:
        if first:
            contents.append(f"({line}) Tj")
            first = False
        else:
            contents.append(f"T* ({line}) Tj")
    contents.append("ET")
    stream = "\n".join(contents).encode("latin1", errors="replace")

    buffer = BytesIO()
    offsets: list[int] = []

    def write_object(index: int, body: bytes) -> None:
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("ascii"))
        buffer.write(body)
        buffer.write(b"\nendobj\n")

    buffer.write(b"%PDF-1.4\n")
    write_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    write_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    write_object(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    write_object(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    write_object(5, f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    xref_offset = buffer.tell()
    buffer.write(f"xref\n0 {len(offsets) + 1}\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    buffer.write(
        (
            f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return buffer.getvalue()

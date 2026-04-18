from __future__ import annotations

import argparse
import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


DATE_FROM = "2000-01-01"
DATE_TO = "2025-12-31"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2].parent / "salomao-config" / "backend.env"
LEGACY_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class MatchKey:
    document_base: str
    due_date: str
    amount_cents: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza issue_date das faturas de compra diretamente no PostgreSQL "
            "a partir de um CSV preparado da planilha externa."
        )
    )
    parser.add_argument("--input-csv", required=True, help="CSV preparado com documento, vencimento, valor e nova emissao.")
    parser.add_argument("--report-dir", required=True, help="Diretorio para salvar os CSVs de auditoria.")
    parser.add_argument("--category-name", default="Compras", help="Nome exato da categoria alvo.")
    parser.add_argument("--date-from", default=DATE_FROM, help="Data inicial de vencimento.")
    parser.add_argument("--date-to", default=DATE_TO, help="Data final de vencimento.")
    parser.add_argument("--apply", action="store_true", help="Aplica o update no banco. Sem esta flag, roda apenas em dry-run.")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE if DEFAULT_ENV_FILE.exists() else LEGACY_ENV_FILE),
        help="Arquivo .env que contem DATABASE_URL.",
    )
    return parser.parse_args()


def load_env(path: Path) -> None:
    if "DATABASE_URL" in os.environ:
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def normalize_spaces(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def extract_document_base(value: object) -> str:
    text = normalize_spaces(value)
    match = re.search(r"(\d+\s*\|\s*\d+)", text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return text


def to_cents(value: object) -> int:
    decimal_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(decimal_value * 100)


def read_source_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "source_row_number": int(row["source_row_number"]),
                    "fornecedor_planilha": row["fornecedor_planilha"],
                    "fornecedor_norm": row["fornecedor_norm"],
                    "fatura_emp": row["fatura_emp"],
                    "document_base": extract_document_base(row["document_base"]),
                    "emissao_nova": row["emissao_nova"],
                    "vencimento": row["vencimento"],
                    "valor_cents": int(row["valor_cents"]),
                    "valor_original": row["valor_original"],
                }
            )
    return rows


def fetch_db_rows(engine, category_name: str, date_from: str, date_to: str) -> list[dict[str, object]]:
    query = text(
        """
        select
            fe.id,
            fe.title,
            fe.counterparty_name,
            fe.document_number,
            fe.issue_date,
            fe.due_date,
            fe.total_amount,
            fe.status,
            fe.source_system,
            fe.source_reference,
            fe.updated_at,
            c.name as category_name,
            c.report_group,
            c.report_subgroup
        from financial_entries fe
        left join categories c on c.id = fe.category_id
        where coalesce(fe.is_deleted, false) = false
          and fe.due_date between :date_from and :date_to
          and trim(coalesce(fe.document_number, '')) <> ''
          and c.name = :category_name
        order by fe.due_date, fe.total_amount, fe.id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {"date_from": date_from, "date_to": date_to, "category_name": category_name},
        ).mappings()
        return [dict(row) for row in rows]


def build_counts(keys: list[MatchKey]) -> dict[MatchKey, int]:
    counts: dict[MatchKey, int] = defaultdict(int)
    for key in keys:
        counts[key] += 1
    return counts


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    load_env(Path(args.env_file))
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL nao encontrado.")

    engine = create_engine(database_url)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_rows = read_source_rows(Path(args.input_csv))
    db_rows = fetch_db_rows(engine, args.category_name, args.date_from, args.date_to)

    source_keys = [
        MatchKey(
            document_base=row["document_base"],
            due_date=row["vencimento"],
            amount_cents=row["valor_cents"],
        )
        for row in source_rows
    ]
    db_keys = [
        MatchKey(
            document_base=extract_document_base(row["document_number"]),
            due_date=str(row["due_date"]),
            amount_cents=to_cents(row["total_amount"]),
        )
        for row in db_rows
    ]

    source_counts = build_counts(source_keys)
    db_counts = build_counts(db_keys)

    source_lookup: dict[MatchKey, dict[str, object]] = {}
    for row, key in zip(source_rows, source_keys):
        if source_counts[key] == 1:
            source_lookup[key] = row

    matched_rows: list[dict[str, object]] = []
    unmatched_db_rows: list[dict[str, object]] = []
    matched_keys: set[MatchKey] = set()

    for row, key in zip(db_rows, db_keys):
        if source_counts[key] == 1 and db_counts[key] == 1:
            source_row = source_lookup[key]
            matched_keys.add(key)
            matched_rows.append(
                {
                    "db_id": row["id"],
                    "document_number_db": row["document_number"],
                    "document_base": key.document_base,
                    "fornecedor_banco": row["title"],
                    "fornecedor_planilha": source_row["fornecedor_planilha"],
                    "issue_date_old": str(row["issue_date"]) if row["issue_date"] else "",
                    "issue_date_new": source_row["emissao_nova"],
                    "due_date": str(row["due_date"]),
                    "total_amount": str(row["total_amount"]),
                    "source_system": row["source_system"],
                    "source_reference": row["source_reference"],
                    "status": row["status"],
                    "category_name": row["category_name"],
                    "report_group": row["report_group"],
                    "report_subgroup": row["report_subgroup"],
                    "changed": "SIM" if str(row["issue_date"]) != source_row["emissao_nova"] else "NAO",
                }
            )
        else:
            unmatched_db_rows.append(
                {
                    "db_id": row["id"],
                    "document_number_db": row["document_number"],
                    "document_base": key.document_base,
                    "fornecedor_banco": row["title"],
                    "issue_date": str(row["issue_date"]) if row["issue_date"] else "",
                    "due_date": str(row["due_date"]),
                    "total_amount": str(row["total_amount"]),
                    "source_system": row["source_system"],
                    "source_reference": row["source_reference"],
                    "status": row["status"],
                    "category_name": row["category_name"],
                    "report_group": row["report_group"],
                    "report_subgroup": row["report_subgroup"],
                    "reason": "sem_match_1a1_ou_duplicado",
                }
            )

    unmatched_source_rows = []
    for row, key in zip(source_rows, source_keys):
        if key not in matched_keys:
            unmatched_source_rows.append(
                {
                    "source_row_number": row["source_row_number"],
                    "fornecedor_planilha": row["fornecedor_planilha"],
                    "fatura_emp": row["fatura_emp"],
                    "document_base": row["document_base"],
                    "emissao_nova": row["emissao_nova"],
                    "vencimento": row["vencimento"],
                    "valor_original": row["valor_original"],
                    "valor_cents": row["valor_cents"],
                    "reason": "sem_match_1a1_ou_duplicado",
                }
            )

    changed_rows = [row for row in matched_rows if row["changed"] == "SIM"]

    if args.apply and changed_rows:
        update_stmt = text(
            """
            update financial_entries
            set issue_date = :issue_date_new,
                updated_at = now()
            where id = :db_id
            """
        )
        with engine.begin() as conn:
            conn.execute(
                update_stmt,
                [{"issue_date_new": row["issue_date_new"], "db_id": row["db_id"]} for row in changed_rows],
            )

    summary_rows = [
        {"campo": "date_from", "valor": args.date_from},
        {"campo": "date_to", "valor": args.date_to},
        {"campo": "category_name", "valor": args.category_name},
        {"campo": "source_rows", "valor": len(source_rows)},
        {"campo": "db_rows", "valor": len(db_rows)},
        {"campo": "matched_1to1", "valor": len(matched_rows)},
        {"campo": "changed_rows", "valor": len(changed_rows)},
        {"campo": "already_same", "valor": len(matched_rows) - len(changed_rows)},
        {"campo": "unmatched_source_rows", "valor": len(unmatched_source_rows)},
        {"campo": "unmatched_db_rows", "valor": len(unmatched_db_rows)},
        {"campo": "applied", "valor": "SIM" if args.apply else "NAO"},
    ]

    write_csv(
        report_dir / "resumo.csv",
        ["campo", "valor"],
        summary_rows,
    )
    write_csv(
        report_dir / "atualizadas.csv",
        [
            "db_id",
            "document_number_db",
            "document_base",
            "fornecedor_banco",
            "fornecedor_planilha",
            "issue_date_old",
            "issue_date_new",
            "due_date",
            "total_amount",
            "source_system",
            "source_reference",
            "status",
            "category_name",
            "report_group",
            "report_subgroup",
            "changed",
        ],
        matched_rows,
    )
    write_csv(
        report_dir / "planilha_sem_match.csv",
        [
            "source_row_number",
            "fornecedor_planilha",
            "fatura_emp",
            "document_base",
            "emissao_nova",
            "vencimento",
            "valor_original",
            "valor_cents",
            "reason",
        ],
        unmatched_source_rows,
    )
    write_csv(
        report_dir / "banco_nao_alteradas.csv",
        [
            "db_id",
            "document_number_db",
            "document_base",
            "fornecedor_banco",
            "issue_date",
            "due_date",
            "total_amount",
            "source_system",
            "source_reference",
            "status",
            "category_name",
            "report_group",
            "report_subgroup",
            "reason",
        ],
        unmatched_db_rows,
    )


if __name__ == "__main__":
    main()

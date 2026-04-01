from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


DATE_FROM = "2000-01-01"
DATE_TO = "2025-12-31"


@dataclass(frozen=True)
class MatchKey:
    supplier: str
    due_date: str
    amount_cents: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza issue_date de faturas de compra no SQLite a partir de uma "
            "planilha externa e gera um relatório xlsx."
        )
    )
    parser.add_argument(
        "--db",
        default="backend/gestor_financeiro.db",
        help="Caminho para o banco SQLite do sistema.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Caminho para a planilha FaturasLancadasPagarPorPeriodo.xlsx.",
    )
    parser.add_argument(
        "--output",
        default="ajuste_emissao_faturas_compra_resultado.xlsx",
        help="Caminho do arquivo xlsx de saída.",
    )
    parser.add_argument(
        "--backup-dir",
        default="backend/backups",
        help="Diretório para salvar o backup do banco antes das alterações.",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Nome da aba da planilha. Se omitido, usa a primeira aba.",
    )
    return parser.parse_args()


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.strip().upper().split())


def normalize_supplier(value: object) -> str:
    text = normalize_text(value)
    if text.endswith(")") and "(" in text:
        base, suffix = text.rsplit("(", 1)
        if suffix[:-1].isdigit():
            text = base.strip()
    return text


def to_amount_cents(value: object) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Valor monetário ausente.")
    if isinstance(value, (int, float, Decimal)):
        decimal_value = Decimal(str(value))
    else:
        text = str(value).strip()
        text = text.replace("R$", "").replace(".", "").replace(" ", "").replace(",", ".")
        if not text:
            raise ValueError("Valor monetário vazio.")
        decimal_value = Decimal(text)
    cents = (decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100).to_integral_value()
    return int(cents)


def to_iso_date(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def load_source_rows(path: Path, sheet_name: str | None) -> pd.DataFrame:
    effective_sheet = 0 if sheet_name is None else sheet_name
    df = pd.read_excel(path, sheet_name=effective_sheet)
    rename_map: dict[str, str] = {}
    for column in df.columns:
        normalized = normalize_text(column)
        if "EMISS" in normalized:
            rename_map[column] = "emissao"
        elif "FATURA/EMP" in normalized:
            rename_map[column] = "fatura_emp"
        elif "VENC" in normalized:
            rename_map[column] = "vencimento"
        elif "VALOR" in normalized:
            rename_map[column] = "valor_fatura"
        elif "CLIENTE" in normalized or "FORNECEDOR" in normalized:
            rename_map[column] = "cliente_fornecedor"
    df = df.rename(columns=rename_map)

    required_columns = {"emissao", "fatura_emp", "vencimento", "valor_fatura", "cliente_fornecedor"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise RuntimeError(f"Planilha sem as colunas esperadas: {sorted(missing_columns)}")

    df = df.copy()
    df["emissao_iso"] = df["emissao"].map(to_iso_date)
    df["vencimento_iso"] = df["vencimento"].map(to_iso_date)
    df["fornecedor_norm"] = df["cliente_fornecedor"].map(normalize_supplier)
    df["amount_cents"] = df["valor_fatura"].map(to_amount_cents)
    df["source_row_number"] = df.index + 2
    df = df[(df["vencimento_iso"] >= DATE_FROM) & (df["vencimento_iso"] <= DATE_TO)]
    return df.reset_index(drop=True)


def load_db_targets(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            fe.id,
            fe.title,
            fe.counterparty_name,
            fe.issue_date,
            fe.due_date,
            fe.total_amount,
            fe.document_number,
            fe.status,
            fe.source_system,
            fe.source_reference,
            fe.updated_at,
            c.name AS category_name,
            c.report_group,
            c.report_subgroup
        FROM financial_entries fe
        LEFT JOIN categories c ON c.id = fe.category_id
        WHERE fe.entry_type = 'expense'
          AND COALESCE(fe.is_deleted, 0) = 0
          AND fe.due_date BETWEEN ? AND ?
          AND (
            lower(COALESCE(c.name, '')) LIKE '%compra%'
            OR lower(COALESCE(c.report_group, '')) LIKE '%compra%'
            OR lower(COALESCE(c.report_subgroup, '')) LIKE '%compra%'
          )
        ORDER BY fe.due_date, fe.total_amount, fe.id
    """
    df = pd.read_sql_query(query, conn, params=(DATE_FROM, DATE_TO))
    df["supplier_norm"] = (
        df["counterparty_name"].where(df["counterparty_name"].notna(), df["title"]).map(normalize_supplier)
    )
    df["amount_cents"] = df["total_amount"].map(to_amount_cents)
    return df


def group_indices_by_key(keys: list[MatchKey]) -> dict[MatchKey, list[int]]:
    grouped: dict[MatchKey, list[int]] = {}
    for index, key in enumerate(keys):
        grouped.setdefault(key, []).append(index)
    return grouped


def build_match_sets(source_df: pd.DataFrame, db_df: pd.DataFrame) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    source_keys = [
        MatchKey(
            supplier=row.fornecedor_norm,
            due_date=row.vencimento_iso,
            amount_cents=int(row.amount_cents),
        )
        for row in source_df.itertuples(index=False)
    ]
    db_keys = [
        MatchKey(
            supplier=row.supplier_norm,
            due_date=row.due_date,
            amount_cents=int(row.amount_cents),
        )
        for row in db_df.itertuples(index=False)
    ]

    source_by_key = group_indices_by_key(source_keys)
    db_by_key = group_indices_by_key(db_keys)

    matched_pairs: list[tuple[int, int]] = []
    matched_source: set[int] = set()
    matched_db: set[int] = set()

    for key, source_indices in source_by_key.items():
        db_indices = db_by_key.get(key, [])
        if len(source_indices) == 1 and len(db_indices) == 1:
            source_index = source_indices[0]
            db_index = db_indices[0]
            matched_pairs.append((source_index, db_index))
            matched_source.add(source_index)
            matched_db.add(db_index)

    unmatched_source = [index for index in range(len(source_df)) if index not in matched_source]
    unmatched_db = [index for index in range(len(db_df)) if index not in matched_db]
    return matched_pairs, unmatched_source, unmatched_db


def create_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}-pre-ajuste-emissao-compra-{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def update_issue_dates(conn: sqlite3.Connection, matched_df: pd.DataFrame) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (row.issue_date_new, now, row.db_id)
        for row in matched_df.itertuples(index=False)
        if row.issue_date_old != row.issue_date_new
    ]
    if not rows:
        return
    conn.executemany(
        """
        UPDATE financial_entries
        SET issue_date = ?, updated_at = ?
        WHERE id = ?
        """,
        rows,
    )
    conn.commit()


def build_output_frames(
    source_df: pd.DataFrame,
    db_df: pd.DataFrame,
    matched_pairs: list[tuple[int, int]],
    unmatched_source: list[int],
    unmatched_db: list[int],
    backup_path: Path,
    source_path: Path,
    db_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    matched_rows: list[dict[str, object]] = []
    for source_index, db_index in matched_pairs:
        source_row = source_df.iloc[source_index]
        db_row = db_df.iloc[db_index]
        matched_rows.append(
            {
                "db_id": db_row["id"],
                "fornecedor_banco": db_row["title"],
                "fornecedor_planilha": source_row["cliente_fornecedor"],
                "fatura_emp": source_row["fatura_emp"],
                "documento_banco": db_row["document_number"],
                "vencimento": db_row["due_date"],
                "valor_total": float(db_row["total_amount"]),
                "issue_date_antiga": db_row["issue_date"],
                "issue_date_nova": source_row["emissao_iso"],
                "source_system": db_row["source_system"],
                "source_reference": db_row["source_reference"],
                "categoria": db_row["category_name"],
            }
        )
    matched_df = pd.DataFrame(matched_rows).sort_values(
        by=["vencimento", "fornecedor_banco", "valor_total"], kind="stable"
    )
    matched_df = matched_df.rename(
        columns={
            "issue_date_antiga": "issue_date_old",
            "issue_date_nova": "issue_date_new",
        }
    )

    unmatched_source_df = source_df.iloc[unmatched_source][
        [
            "source_row_number",
            "cliente_fornecedor",
            "fornecedor_norm",
            "fatura_emp",
            "emissao_iso",
            "vencimento_iso",
            "valor_fatura",
            "amount_cents",
        ]
    ].copy()
    unmatched_source_df = unmatched_source_df.rename(
        columns={
            "source_row_number": "linha_planilha",
            "cliente_fornecedor": "fornecedor_planilha",
            "emissao_iso": "emissao_planilha",
            "vencimento_iso": "vencimento_planilha",
        }
    )

    unmatched_db_df = db_df.iloc[unmatched_db][
        [
            "id",
            "title",
            "counterparty_name",
            "document_number",
            "issue_date",
            "due_date",
            "total_amount",
            "status",
            "source_system",
            "source_reference",
            "category_name",
            "report_group",
            "report_subgroup",
        ]
    ].copy()
    unmatched_db_df = unmatched_db_df.rename(
        columns={
            "title": "fornecedor_banco",
            "counterparty_name": "contraparte_banco",
        }
    )

    summary_df = pd.DataFrame(
        [
            {"campo": "periodo_vencimento", "valor": f"{DATE_FROM} a {DATE_TO}"},
            {"campo": "planilha_origem", "valor": str(source_path)},
            {"campo": "banco_alvo", "valor": str(db_path)},
            {"campo": "backup_banco", "valor": str(backup_path)},
            {"campo": "linhas_planilha_filtradas", "valor": len(source_df)},
            {"campo": "registros_banco_alvo", "valor": len(db_df)},
            {"campo": "registros_atualizados", "valor": len(matched_df)},
            {"campo": "planilha_sem_match", "valor": len(unmatched_source_df)},
            {"campo": "banco_nao_alteradas", "valor": len(unmatched_db_df)},
            {
                "campo": "criterio_match",
                "valor": "fornecedor_normalizado + vencimento + valor; match apenas quando 1:1",
            },
            {
                "campo": "observacao",
                "valor": "A base atual nao possui document_number salvo para esse lote; por isso o match usou chave exata de fornecedor/vencimento/valor.",
            },
        ]
    )

    return matched_df, unmatched_source_df, unmatched_db_df, summary_df


def save_report(
    output_path: Path,
    summary_df: pd.DataFrame,
    matched_df: pd.DataFrame,
    unmatched_source_df: pd.DataFrame,
    unmatched_db_df: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Resumo")
        matched_df.to_excel(writer, index=False, sheet_name="Atualizadas")
        unmatched_source_df.to_excel(writer, index=False, sheet_name="PlanilhaSemMatch")
        unmatched_db_df.to_excel(writer, index=False, sheet_name="BancoNaoAlteradas")


if __name__ == "__main__":
    args = parse_args()
    db_path = Path(args.db).resolve()
    source_path = Path(args.source).resolve()
    output_path = Path(args.output).resolve()
    backup_dir = Path(args.backup_dir).resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"Banco nao encontrado: {db_path}")
    if not source_path.exists():
        raise FileNotFoundError(f"Planilha nao encontrada: {source_path}")

    source_df = load_source_rows(source_path, args.sheet)

    conn = sqlite3.connect(db_path)
    try:
        db_df = load_db_targets(conn)
        matched_pairs, unmatched_source, unmatched_db = build_match_sets(source_df, db_df)
        backup_path = create_backup(db_path, backup_dir)
        matched_df, unmatched_source_df, unmatched_db_df, summary_df = build_output_frames(
            source_df=source_df,
            db_df=db_df,
            matched_pairs=matched_pairs,
            unmatched_source=unmatched_source,
            unmatched_db=unmatched_db,
            backup_path=backup_path,
            source_path=source_path,
            db_path=db_path,
        )
        update_issue_dates(conn, matched_df)
        save_report(
            output_path=output_path,
            summary_df=summary_df,
            matched_df=matched_df,
            unmatched_source_df=unmatched_source_df,
            unmatched_db_df=unmatched_db_df,
        )
    finally:
        conn.close()

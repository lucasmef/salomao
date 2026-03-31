from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, select, text

from app.db.base import Base
from app.db.models import all_models  # noqa: F401

CRITICAL_TOTAL_QUERIES = {
    "financial_entries_total_amount": "SELECT COALESCE(SUM(total_amount), 0) FROM financial_entries",
    "financial_entries_paid_amount": "SELECT COALESCE(SUM(paid_amount), 0) FROM financial_entries",
    "bank_transactions_amount": "SELECT COALESCE(SUM(amount), 0) FROM bank_transactions",
    "receivable_titles_amount": "SELECT COALESCE(SUM(original_amount), 0) FROM receivable_titles",
}

CONSISTENCY_QUERIES = {
    "paid_over_total_entries": (
        "SELECT COUNT(*) FROM financial_entries "
        "WHERE COALESCE(paid_amount, 0) > COALESCE(total_amount, 0)"
    ),
    "settled_without_timestamp": (
        "SELECT COUNT(*) FROM financial_entries "
        "WHERE status = 'settled' AND settled_at IS NULL"
    ),
    "inactive_sessions_marked_active": (
        "SELECT COUNT(*) FROM auth_sessions "
        "WHERE is_active = 1 AND expires_at IS NULL"
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migra uma copia SQLite para PostgreSQL sem tocar no banco de producao local.")
    parser.add_argument("--sqlite-path", required=True, help="Caminho do arquivo SQLite de origem.")
    parser.add_argument("--postgres-url", required=True, help="DSN do PostgreSQL de destino.")
    parser.add_argument("--report-path", required=True, help="Arquivo JSON do relatorio de validacao.")
    parser.add_argument("--working-copy", default=None, help="Copia temporaria do SQLite. Se omitido, usa <arquivo>.migration.sqlite3.")
    parser.add_argument("--truncate-target", action="store_true", help="Limpa as tabelas do PostgreSQL antes da importacao.")
    return parser


def normalize_decimal(value: object) -> str:
    if value is None:
        return "0.00"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{Decimal(str(value)):.2f}"


def copy_sqlite_file(sqlite_path: Path, working_copy: Path) -> None:
    if working_copy.exists():
        working_copy.unlink()
    shutil.copy2(sqlite_path, working_copy)


def table_counts(engine) -> dict[str, int]:
    inspector = inspect(engine)
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table_name in inspector.get_table_names():
            counts[table_name] = connection.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
    return counts


def critical_totals(engine) -> dict[str, str]:
    totals: dict[str, str] = {}
    with engine.connect() as connection:
        for label, query in CRITICAL_TOTAL_QUERIES.items():
            totals[label] = normalize_decimal(connection.execute(text(query)).scalar_one())
    return totals


def consistency_checks(engine) -> dict[str, int]:
    checks: dict[str, int] = {}
    with engine.connect() as connection:
        for label, query in CONSISTENCY_QUERIES.items():
            checks[label] = int(connection.execute(text(query)).scalar_one())
    return checks


def sample_rows(engine) -> dict[str, list[dict[str, object]]]:
    snapshots: dict[str, list[dict[str, object]]] = {}
    sample_queries = {
        "financial_entries": (
            "SELECT id, status, total_amount, paid_amount, due_date, settled_at "
            "FROM financial_entries ORDER BY due_date DESC LIMIT 5"
        ),
        "bank_transactions": (
            "SELECT id, posted_at, amount, fit_id, account_id "
            "FROM bank_transactions ORDER BY posted_at DESC LIMIT 5"
        ),
        "users": (
            "SELECT id, email, role, is_active, mfa_enabled "
            "FROM users ORDER BY created_at DESC LIMIT 5"
        ),
    }
    with engine.connect() as connection:
        for label, query in sample_queries.items():
            snapshots[label] = [dict(row) for row in connection.execute(text(query)).mappings()]
    return snapshots


def foreign_key_issues(engine) -> list[dict[str, object]]:
    inspector = inspect(engine)
    issues: list[dict[str, object]] = []
    with engine.connect() as connection:
        for table_name in inspector.get_table_names():
            for fk in inspector.get_foreign_keys(table_name):
                constrained_columns = fk.get("constrained_columns") or []
                referred_columns = fk.get("referred_columns") or []
                referred_table = fk.get("referred_table")
                if len(constrained_columns) != 1 or len(referred_columns) != 1 or not referred_table:
                    continue
                constrained = constrained_columns[0]
                referred = referred_columns[0]
                count = connection.execute(
                    text(
                        f'SELECT COUNT(*) FROM "{table_name}" child '
                        f'LEFT JOIN "{referred_table}" parent ON child."{constrained}" = parent."{referred}" '
                        f'WHERE child."{constrained}" IS NOT NULL AND parent."{referred}" IS NULL'
                    )
                ).scalar_one()
                if count:
                    issues.append(
                        {
                            "table": table_name,
                            "column": constrained,
                            "referred_table": referred_table,
                            "referred_column": referred,
                            "orphan_count": int(count),
                        }
                    )
    return issues


def transfer_all_rows(sqlite_engine, postgres_engine, *, truncate_target: bool) -> None:
    source_metadata = MetaData()
    source_metadata.reflect(bind=sqlite_engine)
    Base.metadata.create_all(bind=postgres_engine)

    source_tables = {
        table.name: table
        for table in source_metadata.sorted_tables
        if table.name != "alembic_version"
    }
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name in source_tables
    ]
    with sqlite_engine.connect() as source_connection, postgres_engine.connect() as target_connection:
        autocommit_connection = target_connection.execution_options(isolation_level="AUTOCOMMIT")
        autocommit_connection.execute(text("SET session_replication_role = replica"))
        if target_connection.in_transaction():
            target_connection.commit()
        transaction = target_connection.begin()
        try:
            if truncate_target:
                for table in reversed(tables):
                    target_connection.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

            for table in tables:
                source_table = source_tables[table.name]
                rows = [dict(row) for row in source_connection.execute(select(source_table)).mappings()]
                if not rows:
                    continue
                target_connection.execute(table.insert(), rows)
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            if target_connection.in_transaction():
                target_connection.rollback()
            autocommit_connection.execute(text("SET session_replication_role = origin"))


def build_report(sqlite_engine, postgres_engine, sqlite_path: Path, working_copy: Path) -> dict[str, object]:
    source_counts = table_counts(sqlite_engine)
    target_counts = table_counts(postgres_engine)
    source_totals = critical_totals(sqlite_engine)
    target_totals = critical_totals(postgres_engine)
    source_consistency = consistency_checks(sqlite_engine)
    target_consistency = consistency_checks(postgres_engine)
    matching_tables = {
        table_name: source_counts.get(table_name) == target_counts.get(table_name)
        for table_name in sorted(set(source_counts) | set(target_counts))
    }
    matching_totals = {
        label: source_totals.get(label) == target_totals.get(label)
        for label in sorted(set(source_totals) | set(target_totals))
    }
    matching_consistency = {
        label: source_consistency.get(label) == target_consistency.get(label)
        for label in sorted(set(source_consistency) | set(target_consistency))
    }
    target_fk_issues = foreign_key_issues(postgres_engine)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sqlite_source": str(sqlite_path),
        "sqlite_working_copy": str(working_copy),
        "source_counts": source_counts,
        "target_counts": target_counts,
        "source_totals": source_totals,
        "target_totals": target_totals,
        "source_consistency": source_consistency,
        "target_consistency": target_consistency,
        "matching_tables": matching_tables,
        "matching_totals": matching_totals,
        "matching_consistency": matching_consistency,
        "target_foreign_key_issues": target_fk_issues,
        "source_samples": sample_rows(sqlite_engine),
        "target_samples": sample_rows(postgres_engine),
        "success": (
            all(matching_tables.values())
            and all(matching_totals.values())
            and all(matching_consistency.values())
            and not target_fk_issues
        ),
    }


def main() -> None:
    args = build_parser().parse_args()
    sqlite_path = Path(args.sqlite_path).resolve()
    working_copy = Path(args.working_copy).resolve() if args.working_copy else sqlite_path.with_suffix(".migration.sqlite3")
    report_path = Path(args.report_path).resolve()

    if not sqlite_path.exists():
        raise SystemExit(f"SQLite nao encontrado: {sqlite_path}")

    copy_sqlite_file(sqlite_path, working_copy)

    sqlite_engine = create_engine(f"sqlite:///{working_copy.as_posix()}")
    postgres_engine = create_engine(args.postgres_url, pool_pre_ping=True)
    try:
        transfer_all_rows(sqlite_engine, postgres_engine, truncate_target=args.truncate_target)
        report = build_report(sqlite_engine, postgres_engine, sqlite_path, working_copy)
    finally:
        sqlite_engine.dispose()
        postgres_engine.dispose()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()

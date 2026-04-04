from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.services.linx_auto_sync import run_linx_auto_sync_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a sincronizacao automatica do Linx.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Executa imediatamente sem respeitar a janela automatica das 22h.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SessionLocal() as db:
        runs = run_linx_auto_sync_cycle(db, force=args.force)

    if not runs:
        print("Nenhuma empresa habilitada para sincronizacao automatica do Linx.")
        return 0

    failure_found = False
    attempted = 0
    for run in runs:
        if run.attempted:
            attempted += 1
        print(f"{run.company_name}: {run.status}")
        if run.sales_message:
            print(f"  faturamento: {run.sales_message}")
        if run.receivables_message:
            print(f"  faturas: {run.receivables_message}")
        if run.error_message:
            failure_found = True
            print(f"  erro: {run.error_message}")

    if attempted == 0:
        print("Nenhuma sincronizacao precisava rodar nesta janela.")
        return 0
    return 1 if failure_found else 0


if __name__ == "__main__":
    sys.exit(main())

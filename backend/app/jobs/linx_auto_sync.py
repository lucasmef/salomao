from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.services.linx_auto_sync import run_linx_auto_sync_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a sincronizacao automatica do Linx via API.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Executa imediatamente sem respeitar a janela automatica das 06h as 22h.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SessionLocal() as db:
        runs = run_linx_auto_sync_cycle(db, force=args.force)

    if not runs:
        print("Nenhuma empresa habilitada para sincronizacao automatica do Linx.")
        return 0

    hard_failure_found = False
    attempted = 0
    for run in runs:
        if run.attempted:
            attempted += 1
        print(f"{run.company_name}: {run.status}")
        if run.inter_statement_message:
            print(f"  extrato inter: {run.inter_statement_message}")
        if run.inter_charges_message:
            print(f"  boletos inter: {run.inter_charges_message}")
        if run.customers_message:
            print(f"  clientes: {run.customers_message}")
        if run.birthday_alert_message:
            print(f"  aniversariantes: {run.birthday_alert_message}")
        if run.receivables_message:
            print(f"  faturas: {run.receivables_message}")
        if run.movements_message:
            print(f"  movimentos: {run.movements_message}")
        if run.products_message:
            print(f"  produtos: {run.products_message}")
        if run.error_message and run.status == "failed":
            hard_failure_found = True
            print(f"  erro: {run.error_message}")

    if attempted == 0:
        print("Nenhuma sincronizacao precisava rodar nesta janela.")
        return 0
    return 1 if hard_failure_found else 0


if __name__ == "__main__":
    sys.exit(main())

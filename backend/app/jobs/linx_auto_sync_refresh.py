from __future__ import annotations

import argparse
import sys

from app.db.models.security import Company
from app.db.session import SessionLocal
from app.services.auto_sync_refresh import finalize_auto_sync_refresh
from app.services.linx_auto_sync import run_linx_auto_sync_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a sincronizacao automatica do Linx com refresh central.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Executa imediatamente sem respeitar a janela automatica das 06h as 22h.",
    )
    return parser



def _run_has_refreshable_changes(run) -> bool:
    return any(
        message
        for message in (
            run.inter_statement_message,
            run.inter_charges_message,
            run.customers_message,
            run.receivables_message,
            run.movements_message,
            run.products_message,
            run.purchase_payables_message,
        )
    )



def _optional_run_message(run, field_name: str):
    return getattr(run, field_name, None)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SessionLocal() as db:
        runs = run_linx_auto_sync_cycle(db, force=args.force)
        for run in runs:
            if not run.attempted:
                continue
            if run.status not in {"success", "partial_failure"}:
                continue
            if not _run_has_refreshable_changes(run):
                continue
            company = db.get(Company, run.company_id)
            if company is None:
                continue
            finalize_auto_sync_refresh(db, company)

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
        birthday_alert_message = _optional_run_message(run, "birthday_alert_message")
        if birthday_alert_message:
            print(f"  aniversariantes: {birthday_alert_message}")
        if run.receivables_message:
            print(f"  faturas: {run.receivables_message}")
        if run.movements_message:
            print(f"  movimentos: {run.movements_message}")
        if run.products_message:
            print(f"  produtos: {run.products_message}")
        if run.error_message and run.status in {"failed", "partial_failure"}:
            hard_failure_found = True
            print(f"  erro: {run.error_message}")

    if attempted == 0:
        print("Nenhuma sincronizacao precisava rodar nesta janela.")
        return 0
    return 1 if hard_failure_found else 0


if __name__ == "__main__":
    sys.exit(main())

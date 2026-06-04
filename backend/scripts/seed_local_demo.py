from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.bootstrap import ensure_company_security, ensure_default_company
from app.services.local_demo_seed import seed_local_demo_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Popula o SQLite local com dados ficticios para desenvolvimento.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Nao remove os dados ficticios anteriores antes de recriar o seed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.is_sqlite:
        raise SystemExit("seed_local_demo deve ser usado apenas com DATABASE_URL sqlite.")
    if settings.is_server_mode:
        raise SystemExit("seed_local_demo nao deve ser usado em APP_MODE=server.")

    with SessionLocal() as db:
        company = ensure_default_company(db)
        ensure_company_security(db, company)
        summary = seed_local_demo_data(db, company, reset=not args.no_reset)
        db.commit()

    print("Dados ficticios locais criados:")
    print(f"- contas demo: {summary['accounts']}")
    print(f"- lancamentos financeiros demo: {summary['financial_entries']}")
    print(f"- registros comerciais/Linx/boletos demo: {summary['commercial_records']}")
    print(f"- transacoes bancarias demo: {summary['bank_transactions']}")


if __name__ == "__main__":
    main()

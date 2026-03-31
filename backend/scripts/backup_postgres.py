from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.crypto import encrypt_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera dump criptografado do PostgreSQL para operacao do servidor.")
    parser.add_argument("--database-url", required=True, help="DSN do PostgreSQL.")
    parser.add_argument("--output-dir", default=None, help="Diretorio de saida. Usa SERVER_BACKUP_DIR por padrao.")
    parser.add_argument("--pg-dump", default="pg_dump", help="Executavel do pg_dump.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    output_dir = Path(args.output_dir or settings.server_backup_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dump_name = f"gestor-financeiro-postgres-{datetime.now():%Y%m%d-%H%M%S}.sql"
    dump_path = output_dir / dump_name
    encrypted_path = dump_path.with_suffix(".sql.enc")

    result = subprocess.run(
        [args.pg_dump, "--dbname", args.database_url, "--no-owner", "--no-privileges", "--format=plain"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.decode("utf-8", errors="ignore") or "Falha ao executar pg_dump.")

    if settings.server_backup_encrypted:
        encrypted_path.write_bytes(encrypt_bytes(result.stdout))
        print(encrypted_path)
        return

    dump_path.write_bytes(result.stdout)
    print(dump_path)


if __name__ == "__main__":
    main()

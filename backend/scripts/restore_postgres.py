from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from app.core.crypto import decrypt_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restaura dump do PostgreSQL a partir de arquivo .sql ou .sql.enc.")
    parser.add_argument("--database-url", required=True, help="DSN do PostgreSQL.")
    parser.add_argument("--input", required=True, help="Arquivo de entrada do dump.")
    parser.add_argument("--psql", default="psql", help="Executavel do psql.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input).resolve()
    payload = input_path.read_bytes()
    if input_path.suffix == ".enc":
        payload = decrypt_bytes(payload)

    result = subprocess.run(
        [args.psql, args.database_url],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.decode("utf-8", errors="ignore") or "Falha ao restaurar dump.")
    print("restore-ok")


if __name__ == "__main__":
    main()

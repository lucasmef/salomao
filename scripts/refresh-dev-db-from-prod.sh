#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/resolve-env.sh"

PROD_APP_DIR="${PROD_APP_DIR:-/srv/salomao/prod/app}"
DEV_APP_DIR="${DEV_APP_DIR:-/srv/salomao/dev/app}"
PROD_ENV_FILE="${PROD_ENV_FILE:-$(resolve_backend_env_file "$PROD_APP_DIR")}"
DEV_ENV_FILE="${DEV_ENV_FILE:-$(resolve_backend_env_file "$DEV_APP_DIR")}"
BACKUP_DIR="${BACKUP_DIR:-/srv/salomao/backups}"
DATE_STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/prod_to_dev_${DATE_STAMP}.dump"
DEV_BACKUP_FILE="$BACKUP_DIR/dev_pre_refresh_${DATE_STAMP}.dump"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

read_env_value() {
  local file_path="$1"
  local key="$2"

  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$file_path"
}

parse_database_url() {
  local prefix="$1"
  local raw_url="$2"

  python3 - "$prefix" "$raw_url" <<'PY'
import shlex
import sys
from urllib.parse import urlparse, unquote

prefix = sys.argv[1]
raw = sys.argv[2]

if raw.startswith("postgresql+psycopg://"):
    raw = "postgresql://" + raw[len("postgresql+psycopg://"):]

parsed = urlparse(raw)
database_name = unquote(parsed.path.lstrip("/"))

values = {
    "HOST": parsed.hostname or "127.0.0.1",
    "PORT": str(parsed.port or 5432),
    "USER": unquote(parsed.username or ""),
    "PASSWORD": unquote(parsed.password or ""),
    "NAME": database_name,
}

for key, value in values.items():
    print(f"{prefix}_{key}={shlex.quote(value)}")
PY
}

require_command python3
require_command pg_dump
require_command pg_restore
require_command psql
require_command dropdb
require_command createdb
require_command mkdir
require_command awk

if [[ ! -f "$PROD_ENV_FILE" ]]; then
  echo "Arquivo de ambiente de prod nao encontrado: $PROD_ENV_FILE"
  exit 1
fi

if [[ ! -f "$DEV_ENV_FILE" ]]; then
  echo "Arquivo de ambiente de dev nao encontrado: $DEV_ENV_FILE"
  exit 1
fi

PROD_DATABASE_URL="$(read_env_value "$PROD_ENV_FILE" DATABASE_URL)"
DEV_DATABASE_URL="$(read_env_value "$DEV_ENV_FILE" DATABASE_URL)"

if [[ -z "$PROD_DATABASE_URL" || -z "$DEV_DATABASE_URL" ]]; then
  echo "Nao foi possivel localizar DATABASE_URL em prod ou dev"
  exit 1
fi

eval "$(parse_database_url PROD "$PROD_DATABASE_URL")"
eval "$(parse_database_url DEV "$DEV_DATABASE_URL")"

mkdir -p "$BACKUP_DIR"

echo "==> Backup preventivo do banco dev em $DEV_BACKUP_FILE"
export PGPASSWORD="$DEV_PASSWORD"
pg_dump   --host="$DEV_HOST"   --port="$DEV_PORT"   --username="$DEV_USER"   --dbname="$DEV_NAME"   --format=custom   --no-owner   --no-privileges   --file="$DEV_BACKUP_FILE" || echo "[WARN] Backup do banco dev falhou (banco pode estar vazio)"

echo "==> Gerando dump de prod em $DUMP_FILE"
export PGPASSWORD="$PROD_PASSWORD"
pg_dump   --host="$PROD_HOST"   --port="$PROD_PORT"   --username="$PROD_USER"   --dbname="$PROD_NAME"   --format=custom   --no-owner   --no-privileges   --file="$DUMP_FILE"

echo "==> Encerrando conexoes abertas no banco dev"
export PGPASSWORD="$DEV_PASSWORD"
psql   --host="$DEV_HOST"   --port="$DEV_PORT"   --username="$DEV_USER"   --dbname=postgres   --set=ON_ERROR_STOP=1   --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DEV_NAME' AND pid <> pg_backend_pid();" >/dev/null

echo "==> Recriando banco dev"
dropdb   --if-exists   --host="$DEV_HOST"   --port="$DEV_PORT"   --username="$DEV_USER"   "$DEV_NAME"

createdb   --host="$DEV_HOST"   --port="$DEV_PORT"   --username="$DEV_USER"   --owner="$DEV_USER"   "$DEV_NAME"

echo "==> Restaurando dump de prod em dev"
pg_restore   --host="$DEV_HOST"   --port="$DEV_PORT"   --username="$DEV_USER"   --dbname="$DEV_NAME"   --clean   --if-exists   --no-owner   --no-privileges   "$DUMP_FILE"

echo "==> Copia do banco concluida"

echo "==> Executando pos-refresh de seguranca"
bash "$SCRIPT_DIR/post-refresh-dev.sh"

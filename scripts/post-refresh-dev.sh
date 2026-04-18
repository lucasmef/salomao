#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------------------------------------
# post-refresh-dev.sh
#
# Executado apos restaurar o banco de prod no banco dev.
# Coloca o ambiente dev em modo seguro para evitar acoes reais
# com dados de producao.
# ----------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/resolve-env.sh"

DEV_APP_DIR="${DEV_APP_DIR:-/srv/salomao/dev/app}"
DEV_ENV_FILE="${DEV_ENV_FILE:-$(resolve_backend_env_file "$DEV_APP_DIR")}"
DEV_SERVICE="salomao-dev.service"

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
  local raw_url="$1"
  python3 - "$raw_url" <<'PY'
import shlex
import sys
from urllib.parse import urlparse, unquote

raw = sys.argv[1]
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
    print(f"DB_{key}={shlex.quote(value)}")
PY
}

require_command python3
require_command psql
require_command sudo
require_command sed

if [[ ! -f "$DEV_ENV_FILE" ]]; then
  echo "Arquivo de ambiente de dev nao encontrado: $DEV_ENV_FILE"
  exit 1
fi

DEV_DATABASE_URL="$(read_env_value "$DEV_ENV_FILE" DATABASE_URL)"
if [[ -z "$DEV_DATABASE_URL" ]]; then
  echo "DATABASE_URL nao encontrada em $DEV_ENV_FILE"
  exit 1
fi

eval "$(parse_database_url "$DEV_DATABASE_URL")"
export PGPASSWORD="$DB_PASSWORD"

PSQL_CMD=(psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$DB_NAME" --set=ON_ERROR_STOP=1)

echo "==> [pos-refresh] Desabilitando API do Inter em todas as contas"
"${PSQL_CMD[@]}" --command="UPDATE accounts SET inter_api_enabled = false WHERE inter_api_enabled = true;"

echo "==> [pos-refresh] Zerando credenciais Inter armazenadas"
"${PSQL_CMD[@]}" --command="
UPDATE accounts SET
  inter_api_key = NULL,
  inter_client_secret_encrypted = NULL,
  inter_certificate_pem_encrypted = NULL,
  inter_private_key_pem_encrypted = NULL
WHERE inter_api_key IS NOT NULL
   OR inter_client_secret_encrypted IS NOT NULL
   OR inter_certificate_pem_encrypted IS NOT NULL
   OR inter_private_key_pem_encrypted IS NOT NULL;
"

echo "==> [pos-refresh] Invalidando todas as sessoes ativas"
"${PSQL_CMD[@]}" --command="UPDATE auth_sessions SET is_active = false WHERE is_active = true;"

echo "==> [pos-refresh] Invalidando todos os dispositivos confiaveis MFA"
"${PSQL_CMD[@]}" --command="UPDATE mfa_trusted_devices SET is_active = false WHERE is_active = true;"

echo "==> [pos-refresh] Desabilitando alertas de email no .env dev"
if grep -q '^SECURITY_ALERT_EMAIL_ENABLED=' "$DEV_ENV_FILE"; then
  sed -i 's/^SECURITY_ALERT_EMAIL_ENABLED=.*/SECURITY_ALERT_EMAIL_ENABLED=false/' "$DEV_ENV_FILE"
fi

echo "==> [pos-refresh] Reiniciando servico dev"
sudo systemctl restart "$DEV_SERVICE"

echo "==> [pos-refresh] Modo seguro aplicado ao ambiente dev"

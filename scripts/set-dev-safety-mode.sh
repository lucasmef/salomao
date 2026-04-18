#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------------------------------------
# set-dev-safety-mode.sh
#
# Alterna o ambiente dev entre modo seguro e modo de validacao.
#
# Uso: $0 <safe|validate>
#
# safe     - desabilita integracoes e escritas externas (padrao apos refresh)
# validate - reabilita o minimo para janela de validacao com dados reais
# ----------------------------------------------------------------------

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 <safe|validate>"
  exit 1
fi

MODE="$1"
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

set_env_value() {
  local file_path="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "$file_path"; then
    sed -i "s/^${key}=.*/${key}=${value}/" "$file_path"
  else
    echo "${key}=${value}" >> "$file_path"
  fi
}

require_command python3
require_command psql
require_command sudo
require_command sed
require_command awk

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

case "$MODE" in
  safe)
    echo "==> Aplicando modo SEGURO no ambiente dev"

    echo "  -> Desabilitando API do Inter em todas as contas"
    "${PSQL_CMD[@]}" --command="UPDATE accounts SET inter_api_enabled = false WHERE inter_api_enabled = true;"

    echo "  -> Desabilitando alertas de email"
    set_env_value "$DEV_ENV_FILE" SECURITY_ALERT_EMAIL_ENABLED false

    echo "  -> Reiniciando servico dev"
    sudo systemctl restart "$DEV_SERVICE"

    echo "==> Modo SEGURO aplicado"
    echo "  - inter_api_enabled = false em todas as contas"
    echo "  - SECURITY_ALERT_EMAIL_ENABLED = false"
    echo "  - Servico dev reiniciado"
    ;;

  validate)
    echo "==> Aplicando modo VALIDACAO no ambiente dev"
    echo ""
    echo "  ATENCAO: este modo NAO reativa automaticamente a API do Inter."
    echo "  Com credenciais reais de producao, reativar o Inter poderia"
    echo "  causar operacoes reais (emissao de boletos, etc)."
    echo ""
    echo "  Se precisar validar a integracao Inter, reative manualmente"
    echo "  pela interface do sistema, conta a conta."
    echo ""

    echo "  -> Reiniciando servico dev"
    sudo systemctl restart "$DEV_SERVICE"

    echo "==> Modo VALIDACAO aplicado"
    echo "  - Servico dev reiniciado"
    echo "  - Inter NAO foi reativado (seguranca)"
    echo "  - Reative manualmente se necessario"
    ;;

  *)
    echo "Modo invalido: $MODE"
    echo "Use 'safe' ou 'validate'."
    exit 1
    ;;
esac

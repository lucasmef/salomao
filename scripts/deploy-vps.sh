#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <dev|prod>"
  exit 1
fi

TARGET="$1"
case "$TARGET" in
  dev)
    SERVICE_NAME="salomao-dev.service"
    HEALTHCHECK_URL="http://127.0.0.1:8101/api/v1/health"
    ;;
  prod)
    SERVICE_NAME="salomao-prod.service"
    HEALTHCHECK_URL="http://127.0.0.1:8100/api/v1/health"
    ;;
  *)
    echo "Ambiente invalido: $TARGET"
    echo "Use 'dev' ou 'prod'."
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_DIR="$REPO_ROOT/backend"
SYSTEMD_DIR="$REPO_ROOT/deploy/systemd"
ENV_FILE="$BACKEND_DIR/.env"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "$path" ]]; then
    echo "Arquivo obrigatorio ausente: $label ($path)"
    exit 1
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

require_file "$ENV_FILE" "backend/.env"
require_file "$PYTHON_BIN" "backend/.venv/bin/python"
require_file "$FRONTEND_DIR/package.json" "frontend/package.json"

require_command npm
require_command sudo
require_command curl

if ! grep -Eq '^APP_MODE=server$' "$ENV_FILE"; then
  echo "O arquivo $ENV_FILE precisa conter APP_MODE=server para deploy no VPS."
  exit 1
fi

if ! grep -Eq '^DATABASE_URL=postgresql\+psycopg://' "$ENV_FILE"; then
  echo "O arquivo $ENV_FILE precisa apontar DATABASE_URL para PostgreSQL."
  exit 1
fi

echo "==> Build do frontend ($TARGET)"
cd "$FRONTEND_DIR"
npm ci
npm run build

echo "==> Sincronizando dependencias Python ($TARGET)"
cd "$BACKEND_DIR"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path
import subprocess
import sys
import tomllib

dependencies = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
subprocess.run([sys.executable, "-m", "pip", "install", *dependencies], check=True)
PY

echo "==> Migracoes Alembic ($TARGET)"
cd "$BACKEND_DIR"
"$PYTHON_BIN" -m alembic upgrade head



echo "==> Reiniciando servico $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "==> Validando healthcheck"
HEALTHCHECK_OK=false
for attempt in $(seq 1 10); do
  sleep 3
  if curl --fail --silent --show-error "$HEALTHCHECK_URL" >/dev/null 2>&1; then
    HEALTHCHECK_OK=true
    break
  fi
  echo "  tentativa $attempt/10 falhou, aguardando..."
done

if [[ "$HEALTHCHECK_OK" != "true" ]]; then
  echo "Healthcheck falhou apos 10 tentativas"
  exit 1
fi
echo "Healthcheck ok: $HEALTHCHECK_URL"

echo "==> Status do servico"
sudo systemctl status "$SERVICE_NAME" --no-pager

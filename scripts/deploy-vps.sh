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
    SERVICE_PORT="8101"
    ;;
  prod)
    SERVICE_NAME="salomao-prod.service"
    HEALTHCHECK_URL="http://127.0.0.1:8100/api/v1/health"
    SERVICE_PORT="8100"
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
source "$SCRIPT_DIR/resolve-env.sh"
ENV_FILE="$(resolve_backend_env_file "$REPO_ROOT")"
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

require_file "$ENV_FILE" "arquivo de ambiente do backend"
require_file "$PYTHON_BIN" "backend/.venv/bin/python"
require_file "$FRONTEND_DIR/package.json" "frontend/package.json"

require_command npm
require_command sudo
require_command curl
require_command ps
require_command awk
require_command grep
require_command cut
require_command sort

if ! grep -Eq '^APP_MODE=server$' "$ENV_FILE"; then
  echo "O arquivo $ENV_FILE precisa conter APP_MODE=server para deploy no VPS."
  exit 1
fi

if ! grep -Eq '^DATABASE_URL=postgresql\+psycopg://' "$ENV_FILE"; then
  echo "O arquivo $ENV_FILE precisa apontar DATABASE_URL para PostgreSQL."
  exit 1
fi

current_systemd_main_pid() {
  sudo systemctl show "$SERVICE_NAME" -p MainPID --value 2>/dev/null || true
}

list_listener_pids() {
  local port="$1"
  sudo ss -ltnp "( sport = :$port )" 2>/dev/null \
    | grep -o 'pid=[0-9]\+' \
    | cut -d= -f2 \
    | sort -u
}

cleanup_orphan_listener() {
  local port="$1"
  local main_pid
  main_pid="$(current_systemd_main_pid)"

  mapfile -t listener_pids < <(list_listener_pids "$port")
  if [[ ${#listener_pids[@]} -eq 0 ]]; then
    return
  fi

  for listener_pid in "${listener_pids[@]}"; do
    if [[ -n "$main_pid" && "$main_pid" != "0" && "$listener_pid" == "$main_pid" ]]; then
      continue
    fi

    local command_line
    command_line="$(ps -p "$listener_pid" -o args= 2>/dev/null || true)"
    if [[ "$command_line" != *"uvicorn app.main:app"* || "$command_line" != *"--port $port"* ]]; then
      echo "Porta $port ocupada por processo inesperado: PID $listener_pid ($command_line)"
      exit 1
    fi

    echo "==> Encerrando listener orfao na porta $port: PID $listener_pid"
    echo "    comando: $command_line"
    sudo kill "$listener_pid" || true
  done

  sleep 2
  mapfile -t lingering_pids < <(list_listener_pids "$port")
  for lingering_pid in "${lingering_pids[@]}"; do
    if [[ -n "$main_pid" && "$main_pid" != "0" && "$lingering_pid" == "$main_pid" ]]; then
      continue
    fi
    echo "==> Forcando encerramento do listener restante na porta $port: PID $lingering_pid"
    sudo kill -9 "$lingering_pid" || true
  done
}

verify_systemd_listener() {
  local port="$1"
  local main_pid
  main_pid="$(current_systemd_main_pid)"
  if [[ -z "$main_pid" || "$main_pid" == "0" ]]; then
    echo "Servico $SERVICE_NAME sem MainPID ativo apos reinicio."
    exit 1
  fi

  if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Servico $SERVICE_NAME nao permaneceu ativo apos o healthcheck."
    exit 1
  fi

  mapfile -t listener_pids < <(list_listener_pids "$port")
  if [[ ${#listener_pids[@]} -eq 0 ]]; then
    echo "Nenhum listener encontrado na porta $port apos o deploy."
    exit 1
  fi

  for listener_pid in "${listener_pids[@]}"; do
    if [[ "$listener_pid" == "$main_pid" ]]; then
      echo "Listener validado na porta $port com MainPID $main_pid."
      return
    fi
  done

  echo "Healthcheck respondeu, mas o MainPID $main_pid nao e o processo que escuta a porta $port."
  echo "Listeners detectados: ${listener_pids[*]}"
  exit 1
}

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
cleanup_orphan_listener "$SERVICE_PORT"
sudo systemctl daemon-reload
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
verify_systemd_listener "$SERVICE_PORT"

echo "==> Status do servico"
sudo systemctl status "$SERVICE_NAME" --no-pager

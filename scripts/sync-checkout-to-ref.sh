#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Uso: $0 <app-dir> <git-ref>"
  exit 1
fi

APP_DIR="$1"
GIT_REF="$2"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

require_command git

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "==> Checkout Git nao encontrado em: $APP_DIR. Inicializando..."
  mkdir -p "$APP_DIR"
  
  # Obtem a URL do repositorio atual (onde este script esta rodando)
  # Isso garante que usaremos o mesmo transporte (SSH/HTTPS) que o runner ja usa.
  REPO_URL=$(git remote get-url origin 2>/dev/null || echo "https://github.com/lucasmef/salomao.git")
  
  echo "==> Clonando de $REPO_URL para $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Sincronizando checkout $APP_DIR com $GIT_REF"
git -C "$APP_DIR" reset --hard HEAD
git -C "$APP_DIR" clean -fd
git -C "$APP_DIR" fetch --all --prune

if git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$GIT_REF"; then
  git -C "$APP_DIR" checkout -B "$GIT_REF" "origin/$GIT_REF"
  git -C "$APP_DIR" reset --hard "origin/$GIT_REF"
else
  git -C "$APP_DIR" checkout "$GIT_REF"
fi

git -C "$APP_DIR" clean -fd

FINAL_SHA="$(git -C "$APP_DIR" rev-parse HEAD)"
echo "==> Checkout sincronizado: $GIT_REF @ $FINAL_SHA"

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

echo "==> Sincronizando checkout em $APP_DIR"
git -C "$APP_DIR" fetch --all --prune --tags --quiet

# Resolve o SHA alvo a partir do GIT_REF informado
TARGET_SHA=$(git -C "$APP_DIR" rev-parse --verify "$GIT_REF^{commit}")
echo "==> Ref alvo: $GIT_REF"
echo "==> SHA alvo: $TARGET_SHA"

# Limpeza e sincronizacao
git -C "$APP_DIR" reset --hard HEAD --quiet
git -C "$APP_DIR" clean -fd --quiet

# Tenta checkout inteligente:
# 1. Se for uma branch remota (origin/ref), cria/reseta branch local
# 2. Caso contrario (SHA ou tag), faz checkout desatachado (detached HEAD)
if git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$GIT_REF"; then
  echo "==> Detectado branch remota. Sincronizando branch local..."
  git -C "$APP_DIR" checkout -B "$GIT_REF" "origin/$GIT_REF" --quiet
  git -C "$APP_DIR" reset --hard "origin/$GIT_REF" --quiet
else
  echo "==> Fazendo checkout imutavel (detached HEAD)..."
  git -C "$APP_DIR" checkout "$TARGET_SHA" --quiet
fi

# Limpeza final
git -C "$APP_DIR" clean -fd --quiet

FINAL_SHA=$(git -C "$APP_DIR" rev-parse HEAD)
echo "==> Checkout sincronizado com sucesso: @ $FINAL_SHA"

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Uso: $0 <app-dir> <git-ref>"
  exit 1
fi

APP_DIR="$1"
GIT_REF="$2"
APP_PARENT_DIR="$(cd "$(dirname "$APP_DIR")" && pwd)"
APP_BASENAME="$(basename "$APP_DIR")"
EVIDENCE_DIR="${SYNC_CHECKOUT_EVIDENCE_DIR:-$APP_PARENT_DIR/deploy-evidence/$APP_BASENAME}"
LEGACY_EVIDENCE_DIR="$APP_DIR/deploy-evidence"
DIRTY_POLICY="${SYNC_CHECKOUT_DIRTY_POLICY:-fail}"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

require_command git

case "$DIRTY_POLICY" in
  fail|reset)
    ;;
  *)
    echo "Politica de checkout sujo invalida: $DIRTY_POLICY"
    echo "Use SYNC_CHECKOUT_DIRTY_POLICY=fail ou SYNC_CHECKOUT_DIRTY_POLICY=reset."
    exit 1
    ;;
esac

capture_checkout_evidence() {
  local target_dir="$1"
  local timestamp evidence_path
  timestamp="$(date +"%Y%m%d-%H%M%S")"
  evidence_path="$target_dir/checkout-dirty-$timestamp"
  mkdir -p "$evidence_path"

  git -C "$APP_DIR" status --short --branch --untracked-files=all > "$evidence_path/status.txt"
  git -C "$APP_DIR" diff --binary > "$evidence_path/tracked.diff" || true
  git -C "$APP_DIR" diff --cached --binary > "$evidence_path/staged.diff" || true
  git -C "$APP_DIR" ls-files --others --exclude-standard > "$evidence_path/untracked.txt"

  echo "$evidence_path"
}

migrate_legacy_evidence_dir() {
  if [[ ! -d "$LEGACY_EVIDENCE_DIR" ]]; then
    return
  fi

  mkdir -p "$EVIDENCE_DIR"

  local timestamp destination_path
  timestamp="$(date +"%Y%m%d-%H%M%S")"
  destination_path="$EVIDENCE_DIR/legacy-in-tree-$timestamp"

  mv "$LEGACY_EVIDENCE_DIR" "$destination_path"
  echo "==> Evidencia legada movida para fora do checkout: $destination_path"
}

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
migrate_legacy_evidence_dir

# Resolve o SHA alvo a partir do GIT_REF informado
TARGET_SHA=$(git -C "$APP_DIR" rev-parse --verify "$GIT_REF^{commit}")
echo "==> Ref alvo: $GIT_REF"
echo "==> SHA alvo: $TARGET_SHA"
echo "==> Politica para checkout sujo: $DIRTY_POLICY"

STATUS_OUTPUT="$(git -C "$APP_DIR" status --porcelain=v1 --untracked-files=all)"
if [[ -n "$STATUS_OUTPUT" ]]; then
  mkdir -p "$EVIDENCE_DIR"
  EVIDENCE_PATH="$(capture_checkout_evidence "$EVIDENCE_DIR")"
  echo "==> [ERROR] Checkout com alteracoes locais detectadas em $APP_DIR."
  echo "--- INICIO STATUS PORCELAIN ---"
  printf '%s\n' "$STATUS_OUTPUT"
  echo "--- FIM STATUS PORCELAIN ---"
  echo "==> Evidencia preservada em: $EVIDENCE_PATH"
  if [[ "$DIRTY_POLICY" == "reset" ]]; then
    echo "Aplicando reset/clean por politica explicita de ambiente nao produtivo."
    git -C "$APP_DIR" reset --hard HEAD --quiet
    git -C "$APP_DIR" clean -fd --quiet
  else
    echo "Abortando sincronizacao para nao apagar possiveis hotfixes ou vestigios operacionais."
    exit 1
  fi
fi

# Tenta checkout inteligente:
# 1. Se for uma branch remota (origin/ref), cria/reseta branch local
# 2. Caso contrario (SHA ou tag), faz checkout desatachado (detached HEAD)
if git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$GIT_REF"; then
  echo "==> Detectado branch remota. Sincronizando branch local..."
  git -C "$APP_DIR" checkout -B "$GIT_REF" "origin/$GIT_REF" --quiet
else
  echo "==> Fazendo checkout imutavel (detached HEAD)..."
  git -C "$APP_DIR" checkout --detach "$TARGET_SHA" --quiet
fi

FINAL_SHA=$(git -C "$APP_DIR" rev-parse HEAD)
echo "==> Checkout sincronizado com sucesso: @ $FINAL_SHA"

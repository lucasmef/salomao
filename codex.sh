#!/usr/bin/env bash
# Executar como salomao. Autoriza somente a chave pública deste atendimento.
set -euo pipefail
umask 077

PUBLIC_KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMOsYFg2AHaPTgeyOK9Wb847EqRCagWQU5Fwg1O45liO codex-salomao-20260930'
KEY_DATA='AAAAC3NzaC1lZDI1NTE5AAAAIMOsYFg2AHaPTgeyOK9Wb847EqRCagWQU5Fwg1O45liO'
ACTION="${1:-autorizar}"

if [[ "$(id -un)" != salomao ]]; then
  echo 'Execute como salomao, sem sudo: sudo -iu salomao'
  exit 1
fi
case "$ACTION" in
  autorizar|revogar) ;;
  *) echo 'Uso: bash autorizar-acesso-codex.sh [autorizar|revogar]'; exit 1 ;;
esac

SSH_DIR="$HOME/.ssh"
AUTHORIZED_KEYS="$SSH_DIR/authorized_keys"
if [[ -L "$SSH_DIR" || -L "$AUTHORIZED_KEYS" ]]; then
  echo 'Diretorio ou arquivo SSH e um link simbolico; revise manualmente.'
  exit 1
fi
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
touch "$AUTHORIZED_KEYS"
chmod 600 "$AUTHORIZED_KEYS"

# Remove somente esta chave para renovar ou revogar o acesso.
TEMP_FILE="$(mktemp "$SSH_DIR/.codex-keys.XXXXXX")"
trap 'rm -f "$TEMP_FILE"' EXIT
awk -v key="$KEY_DATA" 'index($0, key) == 0' "$AUTHORIZED_KEYS" > "$TEMP_FILE"
if [[ "$ACTION" == autorizar ]]; then
  EXPIRY="$(date -u -d '+24 hours' +%Y%m%d%H%M%SZ)"
  printf 'expiry-time="%s",no-agent-forwarding,no-port-forwarding,no-X11-forwarding %s\n' "$EXPIRY" "$PUBLIC_KEY" >> "$TEMP_FILE"
fi
cat "$TEMP_FILE" > "$AUTHORIZED_KEYS"
chmod 600 "$AUTHORIZED_KEYS"

if [[ "$ACTION" == revogar ]]; then
  echo 'Acesso desta chave revogado.'
  exit 0
fi
printf 'Chave autorizada ate %s (UTC).\n' "$EXPIRY"
echo 'Fingerprint SSH do servidor (envie ao Codex):'
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
if command -v tailscale >/dev/null 2>&1; then
  echo 'IP Tailscale do servidor:'
  tailscale ip -4 || true
fi
if sudo -n true 2>/dev/null; then
  echo 'sudo: disponivel sem senha para esta conta.'
else
  echo 'sudo: exige autenticacao; nenhum privilegio foi alterado.'
fi
echo 'O firewall e a configuracao do SSH foram preservados.'

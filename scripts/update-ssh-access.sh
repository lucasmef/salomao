#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 <ip-ou-cidr>"
  echo "Exemplo: $0 201.182.210.193"
  exit 1
fi

TARGET_SOURCE="$1"

if [[ ! "$TARGET_SOURCE" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$ ]] && [[ ! "$TARGET_SOURCE" =~ : ]]; then
  echo "Origem invalida: $TARGET_SOURCE"
  echo "Informe um IPv4/IPv6 ou CIDR valido."
  exit 1
fi

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

require_command sudo
require_command ufw
require_command awk
require_command grep

echo "==> Ajustando SSH para permitir somente: $TARGET_SOURCE"
echo "==> Regra nova sera aplicada antes da limpeza para evitar lockout da sessao atual"

if ! sudo ufw status | grep -Fq "22/tcp                     ALLOW IN    $TARGET_SOURCE"; then
  sudo ufw allow proto tcp from "$TARGET_SOURCE" to any port 22 comment 'managed-ssh-source'
fi

while true; do
  rule_number="$(
    sudo ufw status numbered \
      | awk -v target="$TARGET_SOURCE" '
          /(OpenSSH|22\/tcp)/ && $0 !~ target {
            gsub(/\[|\]/, "", $1)
            print $1
            exit
          }
        '
  )"

  if [[ -z "$rule_number" ]]; then
    break
  fi

  echo "==> Removendo regra SSH antiga: #$rule_number"
  sudo ufw --force delete "$rule_number"
done

echo
echo "==> Regras finais de SSH"
sudo ufw status | grep -E 'OpenSSH|22/tcp' || true

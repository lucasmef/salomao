#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="salomao-public"
NGINX_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Rode com sudo."
  exit 1
fi

echo "==> Fechando acesso publico HTTP/HTTPS"

if [[ -L "$NGINX_ENABLED" || -f "$NGINX_ENABLED" ]]; then
  rm -f "$NGINX_ENABLED"
  echo "Site publico desativado: $NGINX_ENABLED"
else
  echo "Site publico ja estava desativado."
fi

if [[ -f "$NGINX_AVAILABLE" ]]; then
  echo "Config preservada em: $NGINX_AVAILABLE"
fi

echo "==> Mantendo HTTP/HTTPS pela interface Tailscale, se existir"
if command -v ufw >/dev/null 2>&1; then
  if ip link show tailscale0 >/dev/null 2>&1; then
    ufw allow in on tailscale0 to any port 80 proto tcp || true
    ufw allow in on tailscale0 to any port 443 proto tcp || true
  else
    echo "Interface tailscale0 nao encontrada; pulando regra especifica de Tailscale."
  fi

  echo "==> Removendo regras globais de HTTP/HTTPS, se existirem"
  ufw --force delete allow 80/tcp || true
  ufw --force delete allow 443/tcp || true
  ufw --force delete allow http || true
  ufw --force delete allow https || true
fi

echo "==> Validando e recarregando Nginx"
nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo "==> Status"
systemctl is-active nginx || true
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose || true
fi
ss -ltnp | grep -E ':(80|443|8100|8101)\b' || true

echo
echo "Pronto. O site publico ${SITE_NAME} foi desativado."

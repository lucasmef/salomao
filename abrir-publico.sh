#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-prod}"
DOMAIN="${DOMAIN:-salomao.raquel-talita.vps-kinghost.net}"
SITE_NAME="salomao-public"
NGINX_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
WEBROOT="/var/www/html"

case "$TARGET" in
  prod)
    PORT="8100"
    SERVICE_NAME="salomao-prod.service"
    ;;
  dev)
    PORT="8101"
    SERVICE_NAME="salomao-dev.service"
    ;;
  *)
    echo "Uso: sudo bash abrir-publico.sh [prod|dev]"
    exit 2
    ;;
esac

if [[ "${EUID}" -ne 0 ]]; then
  echo "Rode com sudo."
  exit 1
fi

if [[ -f "./scripts/resolve-env.sh" ]]; then
  # shellcheck source=/dev/null
  source "./scripts/resolve-env.sh"
  ENV_FILE="$(resolve_backend_env_file "$(pwd)")"
elif [[ -f "./backend/.env" ]]; then
  ENV_FILE="./backend/.env"
else
  ENV_FILE=""
fi

if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  echo "==> Ajustando PUBLIC_ORIGIN em ${ENV_FILE}"
  if grep -q '^PUBLIC_ORIGIN=' "$ENV_FILE"; then
    sed -i "s|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=https://${DOMAIN}|" "$ENV_FILE"
  else
    printf '\nPUBLIC_ORIGIN=https://%s\n' "$DOMAIN" >> "$ENV_FILE"
  fi
else
  echo "Aviso: arquivo de ambiente nao encontrado; seguindo sem alterar PUBLIC_ORIGIN."
fi

echo "==> Reiniciando ${SERVICE_NAME}"
systemctl restart "$SERVICE_NAME" || true

mkdir -p "$WEBROOT"

cat > "$NGINX_AVAILABLE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"

echo "==> Liberando HTTP/HTTPS no UFW"
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
fi

echo "==> Validando Nginx HTTP"
nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo "==> Testando backend local"
for attempt in $(seq 1 10); do
  if curl --fail --silent --show-error --max-time 8 "http://127.0.0.1:${PORT}/api/v1/health"; then
    echo
    break
  fi
  echo "  tentativa ${attempt}/10 falhou; aguardando..."
  sleep 2
done

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  echo "==> Emitindo certificado Let's Encrypt"
  if ! command -v certbot >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y certbot
  fi

  certbot certonly \
    --webroot \
    -w "$WEBROOT" \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email
fi

cat > "$NGINX_AVAILABLE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

echo "==> Ativando HTTPS"
nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo "==> Status"
systemctl is-active nginx || true
systemctl is-active "$SERVICE_NAME" || true
ss -ltnp | grep -E ':(80|443|8100|8101)\b' || true
curl -k -I --max-time 10 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" || true

echo
echo "Pronto: https://${DOMAIN}"

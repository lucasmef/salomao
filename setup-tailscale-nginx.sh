#!/bin/bash
set -euo pipefail

DOMAIN="${TAILSCALE_HOST:-salomao-vps.tail2033b8.ts.net}"
TAILSCALE_IPV4="${TAILSCALE_IPV4:-$(tailscale ip -4)}"
TAILSCALE_IPV6="${TAILSCALE_IPV6:-$(tailscale ip -6 2>/dev/null || true)}"
DEV_PORT="${SALOMAO_DEV_TAILSCALE_PORT:-8443}"
NGINX_SSL_DIR="/etc/nginx/ssl"
CONF_FILE="/etc/nginx/sites-available/salomao-dev-tailscale"
LINK_FILE="/etc/nginx/sites-enabled/salomao-dev-tailscale"
LEGACY_PUBLIC_DEV_HOST="dev.raquel-talita.vps-kinghost.net"
LEGACY_PUBLIC_LINK="/etc/nginx/sites-enabled/$LEGACY_PUBLIC_DEV_HOST"

if [[ -z "$TAILSCALE_IPV4" ]]; then
    echo "Nao foi possivel resolver o IPv4 do Tailscale."
    exit 1
fi

echo "Criando diretorio para certificados SSL..."
mkdir -p "$NGINX_SSL_DIR"

SSL_CERT="$NGINX_SSL_DIR/$DOMAIN.crt"
SSL_KEY="$NGINX_SSL_DIR/$DOMAIN.key"

echo "Gerando certificados nativos do Tailscale para $DOMAIN..."
tailscale cert --cert-file "$SSL_CERT" --key-file "$SSL_KEY" "$DOMAIN"

echo "Configurando Nginx (Salomao Dev somente Tailscale, porta $DEV_PORT)..."
{
cat <<NGINX
server {
    listen $TAILSCALE_IPV4:$DEV_PORT ssl;
NGINX

if [[ -n "$TAILSCALE_IPV6" ]]; then
cat <<NGINX
    listen [$TAILSCALE_IPV6]:$DEV_PORT ssl;
NGINX
fi

cat <<NGINX
    server_name $DOMAIN;

    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;

    allow 100.64.0.0/10;
    deny all;
    error_page 403 =404 /denied;
    location = /denied { internal; return 404; }

    location / {
        proxy_pass http://127.0.0.1:8101;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
} > "$CONF_FILE"

ln -sf "$CONF_FILE" "$LINK_FILE"

# Remove especificamente o link do hostname publico legado se ainda estiver la.
if [ -L "$LEGACY_PUBLIC_LINK" ]; then
    rm "$LEGACY_PUBLIC_LINK"
fi

echo "Testando e recarregando Nginx..."
nginx -t
systemctl reload nginx

echo "Sucesso. Salomao dev privado em: https://$DOMAIN:$DEV_PORT"

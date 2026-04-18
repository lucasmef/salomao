#!/bin/bash
set -e

DOMAIN="salomao-vps.tail2033b8.ts.net"
NGINX_SSL_DIR="/etc/nginx/ssl"
CONF_FILE="/etc/nginx/sites-available/salomao-dev-tailscale"
LINK_FILE="/etc/nginx/sites-enabled/salomao-dev-tailscale"
LEGACY_PUBLIC_DEV_HOST="dev.raquel-talita.vps-kinghost.net"
LEGACY_PUBLIC_LINK="/etc/nginx/sites-enabled/$LEGACY_PUBLIC_DEV_HOST"

echo "Criando diretório para certificados SSL..."
mkdir -p "$NGINX_SSL_DIR"

SSL_CERT="$NGINX_SSL_DIR/$DOMAIN.crt"
SSL_KEY="$NGINX_SSL_DIR/$DOMAIN.key"

echo "Gerando certificados nativos do Tailscale para $DOMAIN..."
tailscale cert --cert-file "$SSL_CERT" --key-file "$SSL_KEY" "$DOMAIN"

echo "Configurando Nginx (Dev Tailscale)..."
cat > "$CONF_FILE" << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name salomao-vps.tail2033b8.ts.net;

    allow 100.64.0.0/10;
    deny all;
    error_page 403 =404 /denied;
    location = /denied { internal; return 404; }

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name salomao-vps.tail2033b8.ts.net;

    ssl_certificate /etc/nginx/ssl/salomao-vps.tail2033b8.ts.net.crt;
    ssl_certificate_key /etc/nginx/ssl/salomao-vps.tail2033b8.ts.net.key;

    allow 100.64.0.0/10;
    deny all;
    error_page 403 =404 /denied;
    location = /denied { internal; return 404; }

    location / {
        proxy_pass http://127.0.0.1:8101;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf "$CONF_FILE" "$LINK_FILE"

# Hardening: garantir que hosts nao reconhecidos retornem 404.
# Isso impede que o hostname publico legado do dev continue roteando para a app.
DEFAULT_CONF="/etc/nginx/sites-available/default-404"
DEFAULT_LINK="/etc/nginx/sites-enabled/default-404"

echo "Configurando hardening (default 404)..."
cat > "$DEFAULT_CONF" << EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 404;
}

server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;
    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;
    return 404;
}
EOF

ln -sf "$DEFAULT_CONF" "$DEFAULT_LINK"

# Remove link padrão antigo do Debian se existir
[ -L "/etc/nginx/sites-enabled/default" ] && rm "/etc/nginx/sites-enabled/default"

# Remove especificamente o link do hostname publico legado se ainda estiver la
if [ -L "$LEGACY_PUBLIC_LINK" ]; then
    rm "$LEGACY_PUBLIC_LINK"
fi

echo "Testando e reiniciando Nginx..."
nginx -t
systemctl restart nginx

echo "Sucesso! Ambiente dev migrado estritamente para Tailscale SSL e hardening aplicado."

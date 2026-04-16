#!/bin/bash
set -e

DOMAIN="salomao-vps.tail2033b8.ts.net"
NGINX_SSL_DIR="/etc/nginx/ssl"
CONF_FILE="/etc/nginx/sites-available/salomao-dev-tailscale"
LINK_FILE="/etc/nginx/sites-enabled/salomao-dev-tailscale"
OLD_LINK="/etc/nginx/sites-enabled/dev.raquel-talita.vps-kinghost.net"

echo "Criando diretório para certificados SSL..."
mkdir -p "$NGINX_SSL_DIR"

echo "Gerando certificados nativos do Tailscale para $DOMAIN..."
tailscale cert --cert-file "$NGINX_SSL_DIR/$DOMAIN.crt" --key-file "$NGINX_SSL_DIR/$DOMAIN.key" "$DOMAIN"

echo "Configurando Nginx..."
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
if [ -L "$OLD_LINK" ]; then
    rm "$OLD_LINK"
fi

echo "Testando e reiniciando Nginx..."
nginx -t
systemctl restart nginx

echo "Sucesso! Ambiente dev migrado estritamente para Tailscale SSL."

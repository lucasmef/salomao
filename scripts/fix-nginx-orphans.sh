#!/usr/bin/env bash
set -e

# Legado do ambiente dev publico. Deve existir apenas para limpeza defensiva.
LEGACY_PUBLIC_DEV_HOST="dev.raquel-talita.vps-kinghost.net"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"
DEFAULT_CONF="$NGINX_AVAILABLE/default-404"
DEFAULT_LINK="$NGINX_ENABLED/default-404"

# Certificados para o default server (fallback)
# Usaremos o do Tailscale já que foi configurado recentemente
SSL_CERT="/etc/nginx/ssl/salomao-vps.tail2033b8.ts.net.crt"
SSL_KEY="/etc/nginx/ssl/salomao-vps.tail2033b8.ts.net.key"

echo "==> Removendo resquicios de $LEGACY_PUBLIC_DEV_HOST"
# Remove o symlink
if [ -L "$NGINX_ENABLED/$LEGACY_PUBLIC_DEV_HOST" ]; then
    rm "$NGINX_ENABLED/$LEGACY_PUBLIC_DEV_HOST"
    echo "  Symlink removido."
fi

# Remove o arquivo de configuração se existir
if [ -f "$NGINX_AVAILABLE/$LEGACY_PUBLIC_DEV_HOST" ]; then
    rm "$NGINX_AVAILABLE/$LEGACY_PUBLIC_DEV_HOST"
    echo "  Arquivo de configuração em sites-available removido."
fi

echo "==> Criando configuração default-404 (Hardening)"
cat > "$DEFAULT_CONF" << EOF
# Catch-all server para HTTP
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 404;
}

# Catch-all server para HTTPS
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;

    # Fallback SSL (Browser ainda mostrará erro de nome, mas o retorno será 404)
    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;

    return 404;
}
EOF

# Habilita o default se não estiver habilitado
if [ ! -L "$DEFAULT_LINK" ]; then
    ln -s "$DEFAULT_CONF" "$DEFAULT_LINK"
    echo "  Configuração default-404 habilitada."
fi

# Tenta remover o link 'default' padrão do Debian/Ubuntu se existir e não for o nosso
if [ -L "$NGINX_ENABLED/default" ] && [ "$(readlink "$NGINX_ENABLED/default")" != "$DEFAULT_CONF" ]; then
    rm "$NGINX_ENABLED/default"
    echo "  Antigo link 'default' removido."
fi

echo "==> Testando e reiniciando Nginx"
if nginx -t; then
    systemctl restart nginx
    echo "SUCESSO: Nginx reconfigurado. O host legado $LEGACY_PUBLIC_DEV_HOST agora deve retornar 404."
else
    echo "ERRO: Falha no teste de configuração do Nginx. Revertendo (se necessário)..."
    exit 1
fi

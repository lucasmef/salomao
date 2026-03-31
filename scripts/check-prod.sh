#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
ENV_FILE="$BACKEND_DIR/.env"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
SERVICE_NAME="salomao-prod.service"
LOCAL_HEALTHCHECK_URL="http://127.0.0.1:8100/api/v1/health"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() {
  echo "[PASS] $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

warn() {
  echo "[WARN] $1"
  WARN_COUNT=$((WARN_COUNT + 1))
}

fail() {
  echo "[FAIL] $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

section() {
  echo
  echo "== $1 =="
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    fail "Comando obrigatorio ausente: $command_name"
    return 1
  fi
  pass "Comando disponivel: $command_name"
  return 0
}

read_env_value() {
  local key="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    return 1
  fi
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

mask_value() {
  local raw="$1"
  local length="${#raw}"
  if (( length <= 8 )); then
    printf '%s' '********'
    return
  fi
  printf '%s...%s' "${raw:0:4}" "${raw:length-4:4}"
}

check_service_active() {
  local service_name="$1"
  if sudo systemctl is-active --quiet "$service_name"; then
    pass "Servico ativo: $service_name"
  else
    fail "Servico inativo: $service_name"
  fi
}

check_service_enabled() {
  local service_name="$1"
  if sudo systemctl is-enabled --quiet "$service_name"; then
    pass "Servico habilitado no boot: $service_name"
  else
    warn "Servico nao habilitado no boot: $service_name"
  fi
}

check_http_health() {
  local label="$1"
  local url="$2"
  if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
    pass "Healthcheck ok: $label"
  else
    fail "Healthcheck falhou: $label ($url)"
  fi
}

check_http_status_ok() {
  local label="$1"
  local url="$2"
  local status
  status="$(curl --silent --output /dev/null --write-out "%{http_code}" "$url" 2>/dev/null || true)"
  if [[ "$status" == "200" || "$status" == "301" || "$status" == "302" ]]; then
    pass "Resposta HTTP valida: $label ($status)"
  else
    fail "Resposta HTTP inesperada: $label ($status)"
  fi
}

check_env_file() {
  section "Ambiente"

  if [[ -f "$ENV_FILE" ]]; then
    pass "Arquivo encontrado: $ENV_FILE"
  else
    fail "Arquivo ausente: $ENV_FILE"
    return
  fi

  local app_mode database_url session_secret field_key public_origin allow_header_auth
  app_mode="$(read_env_value APP_MODE)"
  database_url="$(read_env_value DATABASE_URL)"
  session_secret="$(read_env_value SESSION_SECRET)"
  field_key="$(read_env_value FIELD_ENCRYPTION_KEY)"
  public_origin="$(read_env_value PUBLIC_ORIGIN)"
  allow_header_auth="$(read_env_value ALLOW_HEADER_AUTH)"

  if [[ "$app_mode" == "server" ]]; then
    pass "APP_MODE=server"
  else
    fail "APP_MODE esperado 'server', atual: ${app_mode:-<vazio>}"
  fi

  if [[ "$database_url" == postgresql+psycopg://* ]]; then
    pass "DATABASE_URL aponta para PostgreSQL"
  else
    fail "DATABASE_URL nao aponta para PostgreSQL"
  fi

  if [[ -n "$session_secret" && "$session_secret" != "dev-session-secret-change-me" ]]; then
    pass "SESSION_SECRET configurado (${#session_secret} caracteres)"
  else
    fail "SESSION_SECRET ausente ou inseguro"
  fi

  if [[ -n "$field_key" && "$field_key" != "dev-field-encryption-key-change-me" ]]; then
    pass "FIELD_ENCRYPTION_KEY configurada ($(mask_value "$field_key"))"
  else
    fail "FIELD_ENCRYPTION_KEY ausente ou insegura"
  fi

  if [[ "$public_origin" == https://* ]]; then
    pass "PUBLIC_ORIGIN usa HTTPS: $public_origin"
  else
    fail "PUBLIC_ORIGIN deve usar HTTPS"
  fi

  if [[ "${allow_header_auth,,}" == "false" ]]; then
    pass "ALLOW_HEADER_AUTH=false"
  else
    warn "ALLOW_HEADER_AUTH deveria ficar false em producao"
  fi
}

check_processes() {
  section "Servicos"
  check_service_active "$SERVICE_NAME"
  check_service_enabled "$SERVICE_NAME"
  check_service_active "nginx"
  check_service_enabled "nginx"
  check_service_active "postgresql"
  check_service_enabled "postgresql"
  check_service_active "fail2ban"
  check_service_enabled "fail2ban"
}

check_networking() {
  section "Rede"

  check_http_health "backend local prod" "$LOCAL_HEALTHCHECK_URL"

  local public_origin
  public_origin="$(read_env_value PUBLIC_ORIGIN)"
  if [[ "$public_origin" == https://* ]]; then
    check_http_status_ok "origem publica" "$public_origin"
    check_http_health "healthcheck publico" "${public_origin%/}/api/v1/health"
  else
    warn "PUBLIC_ORIGIN ausente; checks publicos ignorados"
  fi

  local listen_output
  listen_output="$(sudo ss -ltnp 2>/dev/null || true)"

  if grep -Eq '127\.0\.0\.1:8100\b' <<<"$listen_output"; then
    pass "Backend prod ouvindo apenas em loopback na porta 8100"
  elif grep -Eq '0\.0\.0\.0:8100\b|:::8100\b' <<<"$listen_output"; then
    fail "Backend prod exposto diretamente na porta 8100"
  else
    warn "Porta 8100 nao encontrada na lista de sockets"
  fi

  if grep -Eq '0\.0\.0\.0:8101\b|:::8101\b' <<<"$listen_output"; then
    fail "Ambiente dev exposto diretamente na porta 8101"
  elif grep -Eq '127\.0\.0\.1:8101\b' <<<"$listen_output"; then
    pass "Ambiente dev restrito a loopback na porta 8101"
  else
    warn "Porta 8101 nao encontrada na lista de sockets"
  fi

  if grep -Eq '0\.0\.0\.0:22\b|:::22\b' <<<"$listen_output"; then
    pass "SSH ouvindo na porta 22"
  else
    warn "Porta 22 nao apareceu em ss -ltnp"
  fi

  if grep -Eq '0\.0\.0\.0:80\b|:::80\b' <<<"$listen_output"; then
    pass "HTTP publico ouvindo na porta 80"
  else
    warn "Porta 80 nao apareceu em ss -ltnp"
  fi

  if grep -Eq '0\.0\.0\.0:443\b|:::443\b' <<<"$listen_output"; then
    pass "HTTPS publico ouvindo na porta 443"
  else
    warn "Porta 443 nao apareceu em ss -ltnp"
  fi

  if grep -Eq '0\.0\.0\.0:5432\b|:::5432\b' <<<"$listen_output"; then
    fail "PostgreSQL exposto publicamente na porta 5432"
  elif grep -Eq '127\.0\.0\.1:5432\b' <<<"$listen_output"; then
    pass "PostgreSQL restrito a loopback na porta 5432"
  else
    warn "Porta 5432 nao encontrada na lista de sockets"
  fi
}

check_nginx_and_tls() {
  section "Nginx e TLS"

  if sudo nginx -t >/dev/null 2>&1; then
    pass "Configuracao do Nginx valida"
  else
    fail "Falha em nginx -t"
  fi

  local public_origin host
  public_origin="$(read_env_value PUBLIC_ORIGIN)"
  host="${public_origin#https://}"
  host="${host%%/*}"

  if [[ -n "$host" ]]; then
    local cert_output
    cert_output="$(echo | openssl s_client -servername "$host" -connect "$host:443" 2>/dev/null | openssl x509 -noout -subject -dates 2>/dev/null || true)"
    if [[ -n "$cert_output" ]]; then
      pass "Certificado HTTPS lido com sucesso para $host"
      echo "$cert_output" | sed 's/^/  /'
    else
      warn "Nao foi possivel ler o certificado HTTPS de $host"
    fi
  else
    warn "Host publico ausente; validacao de certificado ignorada"
  fi

  if command -v certbot >/dev/null 2>&1; then
    if sudo certbot renew --dry-run >/dev/null 2>&1; then
      pass "Renovacao do certificado passou no dry-run"
    else
      warn "Dry-run do certbot falhou"
    fi
  else
    warn "certbot nao encontrado"
  fi
}

check_firewall_and_bans() {
  section "Firewall e bans"

  local ufw_status fail2ban_status
  ufw_status="$(sudo ufw status 2>/dev/null || true)"
  fail2ban_status="$(sudo fail2ban-client status 2>/dev/null || true)"

  if grep -q "Status: active" <<<"$ufw_status"; then
    pass "UFW ativo"
  else
    fail "UFW inativo"
  fi

  if grep -Eq '(^|[[:space:]])22(/tcp)?[[:space:]]+ALLOW' <<<"$ufw_status"; then
    pass "UFW libera SSH"
  else
    fail "UFW nao mostra regra para SSH"
  fi

  if grep -Eq '(OpenSSH|22/tcp)[[:space:]]+ALLOW([[:space:]]+IN)?[[:space:]]+Anywhere([[:space:]]|\(|$)' <<<"$ufw_status"; then
    fail "UFW expõe SSH para Anywhere"
  elif grep -Eq '(OpenSSH|22/tcp)[[:space:]]+ALLOW([[:space:]]+IN)?[[:space:]]+Anywhere \(v6\)' <<<"$ufw_status"; then
    fail "UFW expõe SSH para Anywhere (v6)"
  elif grep -Eq '(OpenSSH|22/tcp)[[:space:]]+ALLOW([[:space:]]+IN)?[[:space:]]+([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?([[:space:]]+#.*)?$' <<<"$ufw_status"; then
    pass "UFW restringe SSH por IPv4 de origem"
  elif grep -Eq '(OpenSSH|22/tcp)[[:space:]]+ALLOW([[:space:]]+IN)?[[:space:]]+[0-9a-fA-F:]+(/[0-9]{1,3})?([[:space:]]+#.*)?$' <<<"$ufw_status"; then
    pass "UFW restringe SSH por IPv6 de origem"
  else
    warn "Nao foi possivel confirmar se o SSH esta restrito por IP"
  fi

  if grep -Eq '(^|[[:space:]])80(/tcp)?[[:space:]]+ALLOW' <<<"$ufw_status"; then
    pass "UFW libera HTTP"
  else
    fail "UFW nao mostra regra para HTTP"
  fi

  if grep -Eq '(^|[[:space:]])443(/tcp)?[[:space:]]+ALLOW' <<<"$ufw_status"; then
    pass "UFW libera HTTPS"
  else
    fail "UFW nao mostra regra para HTTPS"
  fi

  if grep -Eq '(^|[[:space:]])8100(/tcp)?[[:space:]]+ALLOW|(^|[[:space:]])8101(/tcp)?[[:space:]]+ALLOW|(^|[[:space:]])5432(/tcp)?[[:space:]]+ALLOW' <<<"$ufw_status"; then
    fail "UFW contem porta sensivel exposta (8100/8101/5432)"
  else
    pass "UFW nao expoe 8100, 8101 ou 5432"
  fi

  if grep -q "Status" <<<"$fail2ban_status"; then
    pass "fail2ban-client respondeu"
    echo "$fail2ban_status" | sed 's/^/  /'
  else
    warn "Nao foi possivel consultar fail2ban-client"
  fi
}

check_ssh_policy() {
  section "SSH"

  if ! command -v sshd >/dev/null 2>&1; then
    warn "sshd nao encontrado para validar configuracao efetiva"
    return
  fi

  local sshd_output
  sshd_output="$(sudo sshd -T 2>/dev/null || true)"

  if grep -q '^permitrootlogin no$' <<<"$sshd_output"; then
    pass "Root login via SSH desativado"
  else
    fail "Root login via SSH nao esta explicitamente desativado"
  fi

  if grep -q '^passwordauthentication no$' <<<"$sshd_output"; then
    pass "Autenticacao por senha no SSH desativada"
  else
    warn "Autenticacao por senha no SSH nao esta desativada"
  fi

  if grep -q '^pubkeyauthentication yes$' <<<"$sshd_output"; then
    pass "Autenticacao por chave publica habilitada"
  else
    fail "Autenticacao por chave publica nao esta habilitada"
  fi
}

check_backend_runtime() {
  section "Runtime Python"

  if [[ -f "$PYTHON_BIN" ]]; then
    pass "Python do backend encontrado"
  else
    fail "Python do backend ausente: $PYTHON_BIN"
    return
  fi

  if "$PYTHON_BIN" -c "import psycopg, fastapi, sqlalchemy" >/dev/null 2>&1; then
    pass "Dependencias principais do backend importam sem erro"
  else
    fail "Falha ao importar dependencias principais do backend"
  fi
}

main() {
  echo "Auditoria rapida de producao"
  echo "Repositorio: $REPO_ROOT"
  echo "Arquivo de ambiente: $ENV_FILE"

  section "Pre-check"
  require_command sudo || true
  require_command curl || true
  require_command openssl || true
  require_command awk || true
  require_command grep || true

  check_env_file
  check_backend_runtime
  check_processes
  check_networking
  check_nginx_and_tls
  check_firewall_and_bans
  check_ssh_policy

  echo
  echo "Resumo: PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT"
  if (( FAIL_COUNT > 0 )); then
    exit 1
  fi
  exit 0
}

main "$@"

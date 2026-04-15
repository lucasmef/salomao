#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------------------------------------
# sanitize-dev-db.sh
#
# Anonimiza dados sensiveis no banco dev apos a janela de validacao.
# Preserva a estrutura, relacionamentos e massa minima util para
# testes e desenvolvimento com o frontend.
#
# NAO apaga tudo — substitui dados pessoais/sensiveis por valores
# ficticios anonimos.
# ----------------------------------------------------------------------

DEV_ENV_FILE="${DEV_ENV_FILE:-/srv/salomao/dev/app/backend/.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/salomao}"
DATE_STAMP="$(date +%Y%m%d_%H%M%S)"
SANITIZE_BACKUP_FILE="$BACKUP_DIR/dev_pre_sanitize_${DATE_STAMP}.dump"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatorio nao encontrado: $command_name"
    exit 1
  fi
}

read_env_value() {
  local file_path="$1"
  local key="$2"
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$file_path"
}

parse_database_url() {
  local raw_url="$1"
  python3 - "$raw_url" <<'PY'
import shlex
import sys
from urllib.parse import urlparse, unquote

raw = sys.argv[1]
if raw.startswith("postgresql+psycopg://"):
    raw = "postgresql://" + raw[len("postgresql+psycopg://"):]

parsed = urlparse(raw)
database_name = unquote(parsed.path.lstrip("/"))

values = {
    "HOST": parsed.hostname or "127.0.0.1",
    "PORT": str(parsed.port or 5432),
    "USER": unquote(parsed.username or ""),
    "PASSWORD": unquote(parsed.password or ""),
    "NAME": database_name,
}

for key, value in values.items():
    print(f"DB_{key}={shlex.quote(value)}")
PY
}

require_command python3
require_command psql
require_command pg_dump
require_command mkdir
require_command awk

if [[ ! -f "$DEV_ENV_FILE" ]]; then
  echo "Arquivo de ambiente de dev nao encontrado: $DEV_ENV_FILE"
  exit 1
fi

DEV_DATABASE_URL="$(read_env_value "$DEV_ENV_FILE" DATABASE_URL)"
if [[ -z "$DEV_DATABASE_URL" ]]; then
  echo "DATABASE_URL nao encontrada em $DEV_ENV_FILE"
  exit 1
fi

eval "$(parse_database_url "$DEV_DATABASE_URL")"
export PGPASSWORD="$DB_PASSWORD"

PSQL_CMD=(psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$DB_NAME" --set=ON_ERROR_STOP=1)

mkdir -p "$BACKUP_DIR"

# --- Backup preventivo ---------------------------------------------------

echo "==> Backup preventivo do banco dev em $SANITIZE_BACKUP_FILE"
pg_dump   --host="$DB_HOST"   --port="$DB_PORT"   --username="$DB_USER"   --dbname="$DB_NAME"   --format=custom   --no-owner   --no-privileges   --file="$SANITIZE_BACKUP_FILE"

# --- Gerar hash de senha padrao para dev ----------------------------------

echo "==> Gerando hash de senha padrao para usuarios dev"
DEV_PASSWORD_HASH="$(python3 - <<'PY'
import hashlib
import secrets

password = "dev-test-2026"
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac(
    "sha256",
    password.encode("utf-8"),
    salt.encode("utf-8"),
    120_000,
).hex()
print(f"pbkdf2_sha256$120000${salt}${digest}")
PY
)"

# --- Sanitizacao -----------------------------------------------------------

echo "==> Sanitizando tabela: companies"
"${PSQL_CMD[@]}" --command="
UPDATE companies SET
  legal_name = 'Empresa Dev ' || substr(id, 1, 8),
  trade_name = 'Dev ' || substr(id, 1, 8),
  document  = lpad(floor(random() * 99999999999)::text, 11, '0');
"

echo "==> Sanitizando tabela: users"
"${PSQL_CMD[@]}" --command="
UPDATE users SET
  full_name                   = 'Usuario Dev ' || substr(id, 1, 8),
  email                       = 'dev-' || substr(id, 1, 8) || '@dev.local',
  password_hash               = '$DEV_PASSWORD_HASH',
  mfa_enabled                 = false,
  mfa_secret_encrypted        = NULL,
  mfa_pending_secret_encrypted = NULL,
  mfa_enrolled_at             = NULL;
"

echo "==> Sanitizando tabela: accounts (credenciais Inter)"
"${PSQL_CMD[@]}" --command="
UPDATE accounts SET
  inter_api_enabled                 = false,
  inter_api_key                     = NULL,
  inter_account_number              = NULL,
  inter_client_secret_encrypted     = NULL,
  inter_certificate_pem_encrypted   = NULL,
  inter_private_key_pem_encrypted   = NULL,
  account_number                    = lpad(floor(random() * 999999)::text, 6, '0'),
  branch_number                     = lpad(floor(random() * 9999)::text, 4, '0');
"

echo "==> Sanitizando tabela: financial_entries"
"${PSQL_CMD[@]}" --command="
UPDATE financial_entries SET
  counterparty_name = CASE WHEN counterparty_name IS NOT NULL THEN 'Terceiro ' || substr(id, 1, 8) ELSE NULL END,
  document_number   = CASE WHEN document_number IS NOT NULL THEN lpad(floor(random() * 99999999999)::text, 11, '0') ELSE NULL END,
  description       = CASE WHEN description IS NOT NULL THEN 'Descricao anonimizada' ELSE NULL END,
  notes             = CASE WHEN notes IS NOT NULL THEN 'Nota anonimizada' ELSE NULL END;
"

echo "==> Sanitizando tabela: recurrence_rules"
"${PSQL_CMD[@]}" --command="
UPDATE recurrence_rules SET
  counterparty_name = CASE WHEN counterparty_name IS NOT NULL THEN 'Terceiro Rec ' || substr(id, 1, 8) ELSE NULL END,
  document_number   = CASE WHEN document_number IS NOT NULL THEN lpad(floor(random() * 99999999999)::text, 11, '0') ELSE NULL END,
  notes             = CASE WHEN notes IS NOT NULL THEN 'Nota anonimizada' ELSE NULL END;
"

echo "==> Sanitizando tabela: bank_transactions"
"${PSQL_CMD[@]}" --command="
UPDATE bank_transactions SET
  name        = CASE WHEN name IS NOT NULL THEN 'Transacao ' || substr(id, 1, 8) ELSE NULL END,
  memo        = CASE WHEN memo IS NOT NULL THEN 'Memo anonimizado' ELSE NULL END,
  raw_payload = NULL;
"

echo "==> Sanitizando tabela: boleto_customer_configs"
"${PSQL_CMD[@]}" --command="
UPDATE boleto_customer_configs SET
  client_name        = 'Cliente Dev ' || substr(id, 1, 8),
  tax_id             = CASE WHEN tax_id IS NOT NULL THEN lpad(floor(random() * 99999999999)::text, 11, '0') ELSE NULL END,
  address_street     = CASE WHEN address_street IS NOT NULL THEN 'Rua Dev ' || substr(id, 1, 8) ELSE NULL END,
  address_number     = CASE WHEN address_number IS NOT NULL THEN floor(random() * 9999)::text ELSE NULL END,
  address_complement = NULL,
  neighborhood       = CASE WHEN neighborhood IS NOT NULL THEN 'Bairro Dev' ELSE NULL END,
  city               = CASE WHEN city IS NOT NULL THEN 'Cidade Dev' ELSE NULL END,
  state              = CASE WHEN state IS NOT NULL THEN 'SP' ELSE NULL END,
  zip_code           = CASE WHEN zip_code IS NOT NULL THEN lpad(floor(random() * 99999999)::text, 8, '0') ELSE NULL END,
  phone_primary      = NULL,
  phone_secondary    = NULL,
  mobile             = NULL,
  state_registration = NULL,
  notes              = CASE WHEN notes IS NOT NULL THEN 'Nota anonimizada' ELSE NULL END;
"

echo "==> Sanitizando tabela: boleto_records"
"${PSQL_CMD[@]}" --command="
UPDATE boleto_records SET
  client_name     = 'Cliente Dev ' || substr(id, 1, 8),
  client_key      = 'cliente-dev-' || substr(id, 1, 8),
  barcode         = NULL,
  linha_digitavel = NULL,
  pix_copia_e_cola = NULL;
"

echo "==> Sanitizando tabela: receivable_titles"
"${PSQL_CMD[@]}" --command="
UPDATE receivable_titles SET
  customer_name      = 'Cliente Dev ' || substr(id, 1, 8),
  seller_name        = CASE WHEN seller_name IS NOT NULL THEN 'Vendedor Dev ' || substr(id, 1, 8) ELSE NULL END,
  document_reference = CASE WHEN document_reference IS NOT NULL THEN lpad(floor(random() * 99999999999)::text, 11, '0') ELSE NULL END;
"

echo "==> Sanitizando tabela: suppliers"
"${PSQL_CMD[@]}" --command="
UPDATE suppliers SET
  name            = 'Fornecedor Dev ' || substr(id, 1, 8),
  document_number = CASE WHEN document_number IS NOT NULL THEN lpad(floor(random() * 99999999999999)::text, 14, '0') ELSE NULL END;
"

echo "==> Sanitizando tabela: loan_contracts"
"${PSQL_CMD[@]}" --command="
UPDATE loan_contracts SET
  lender_name     = 'Credor Dev ' || substr(id, 1, 8),
  contract_number = CASE WHEN contract_number IS NOT NULL THEN 'CTR-' || substr(id, 1, 8) ELSE NULL END;
"

echo "==> Sanitizando tabela: purchase_invoices (raw_text, raw_xml, nfe_key)"
"${PSQL_CMD[@]}" --command="
UPDATE purchase_invoices SET
  raw_text = NULL,
  raw_xml  = NULL,
  nfe_key  = CASE WHEN nfe_key IS NOT NULL THEN lpad(floor(random() * 999999999)::text, 44, '0') ELSE NULL END;
"

echo "==> Sanitizando tabela: reconciliation_rules"
"${PSQL_CMD[@]}" --command="
UPDATE reconciliation_rules SET
  counterparty_name = CASE WHEN counterparty_name IS NOT NULL THEN 'Terceiro Regra ' || substr(id, 1, 8) ELSE NULL END;
"

echo "==> Sanitizando tabela: audit_logs (before_state, after_state)"
"${PSQL_CMD[@]}" --command="
UPDATE audit_logs SET
  before_state = NULL,
  after_state  = NULL;
"

echo "==> Limpando sessoes e dispositivos confiaveis"
"${PSQL_CMD[@]}" --command="
TRUNCATE auth_sessions;
TRUNCATE mfa_trusted_devices;
"

echo "==> Sanitizacao concluida"
echo ""
echo "  Senha padrao dos usuarios: dev-test-2026"
echo "  MFA desabilitado para todos os usuarios"
echo "  Email do admin trocado para dev-*@dev.local"
echo "  Credenciais Inter removidas de todas as contas"
echo "  Dados pessoais anonimizados em todas as tabelas"
echo ""
echo "  Um backup pre-sanitizacao foi salvo em:"
echo "  $SANITIZE_BACKUP_FILE"

#!/usr/bin/env bash
set -euo pipefail

resolve_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir/.."
  pwd
}

default_external_env_file() {
  local repo_root="$1"
  local parent_dir
  parent_dir="$(cd "$repo_root/.." && pwd)"
  printf '%s\n' "$parent_dir/salomao-config/backend.env"
}

resolve_backend_env_file() {
  local repo_root="${1:-$(resolve_repo_root)}"
  local explicit_env_file="${SALOMAO_ENV_FILE:-${BACKEND_ENV_FILE:-}}"
  if [[ -n "$explicit_env_file" ]]; then
    printf '%s\n' "$explicit_env_file"
    return
  fi

  local external_env_file
  external_env_file="$(default_external_env_file "$repo_root")"
  if [[ -f "$external_env_file" ]]; then
    printf '%s\n' "$external_env_file"
    return
  fi

  printf '%s\n' "$repo_root/backend/.env"
}

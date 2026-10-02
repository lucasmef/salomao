#!/usr/bin/env bash
# Targeted, reversible maintenance of the already deployed SMTP release.
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin
umask 077
[[ $(id -un) == salomao && $# == 1 && $1 =~ ^[a-f0-9]{40}$ ]] || exit 2
app=/srv/salomao/prod/app
base=8d73881327490410ab27869060ee26e436d9c382
target=$1
cd "$app"
exec 9>/home/salomao/.security-oct2.lock
flock -n 9 || { echo 'Outra manutencao em andamento'; exit 1; }
[[ $(git rev-parse HEAD) == "$base" ]] || { echo 'Producao mudou; revisao necessaria'; exit 1; }
[[ -z $(git status --porcelain) ]] || { echo 'Checkout alterado; preservado'; exit 1; }
git merge-base --is-ancestor "$base" "$target"
# Preserve every SMTP file and reject an unreviewed release scope.
while IFS= read -r name; do
  case "$name" in
    backend/pyproject.toml|backend/uv.lock|backend/app/services/linx_auto_sync.py|backend/tests/test_linx_auto_sync.py|diagnosticar-seguranca.sh|scripts/security-requirements.txt|scripts/apply-security-oct2.sh|specs/2026-10-02-security-completion.md) ;;
    *) echo 'Escopo de alteracoes inesperado; abortado'; exit 1;;
  esac
done < <(git diff --name-only "$base" "$target")
curl -fsS --max-time 15 http://127.0.0.1:8100/api/v1/health >/dev/null
[[ $(systemctl show -p ActiveState --value salomao-linx-auto-sync@prod.service) != activating ]] || { echo 'Sincronizacao em andamento; aguarde'; exit 1; }
recovery=$(mktemp -d /srv/salomao/prod/.security-oct2.XXXXXX)
printf '%s\n' "$base" > "$recovery/base"
git show "$target:scripts/security-requirements.txt" > "$recovery/requirements.txt"
cp -a backend/.venv "$recovery/venv-next"
# Install only in the staged environment; never import production config here.
"$recovery/venv-next/bin/python" -m pip install --disable-pip-version-check --no-input --upgrade 'pip==26.2.0' > "$recovery/install.log" 2>&1
"$recovery/venv-next/bin/python" -m pip install --disable-pip-version-check --no-input --require-hashes -r "$recovery/requirements.txt" >> "$recovery/install.log" 2>&1
"$recovery/venv-next/bin/python" -m pip check
"$recovery/venv-next/bin/python" - <<'PY'
import importlib.metadata as m
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
for name, version in {'anyio':'4.14.2','cryptography':'50.0.2','pypdf':'6.19.0','starlette':'1.3.1','idna':'3.15','mako':'1.3.12','pip':'26.2.0'}.items():
    assert m.version(name)==version, name
c=AESGCM(b'0'*32); n=b'1'*12
assert c.decrypt(n,c.encrypt(n,b'recovery-check',b'test'),b'test')==b'recovery-check'
PY
# Old processes remain running while all preparation completes.
[[ $(git rev-parse HEAD) == "$base" && -z $(git status --porcelain) ]] || exit 1
[[ $(systemctl show -p ActiveState --value salomao-linx-auto-sync@prod.service) != activating ]] || { echo 'Sincronizacao iniciou; aplicacao adiada'; exit 1; }
sha256sum /srv/salomao/prod/salomao-config/backend.env > "$recovery/env.sha256"
old_moved=0
new_moved=0
rollback() {
  code=$?
  trap - ERR INT TERM
  set +e
  git checkout --detach "$base" >/dev/null 2>&1
  if [[ $new_moved == 1 ]]; then mv backend/.venv "$recovery/venv-failed"; fi
  if [[ $old_moved == 1 ]]; then mv "$recovery/venv-before" backend/.venv; fi
  sudo -n /usr/bin/systemctl restart salomao-prod.service
  echo "Falha: versao anterior restaurada. Recuperacao: $recovery"
  exit "$code"
}
trap rollback ERR INT TERM
git checkout --detach "$target"
mv backend/.venv "$recovery/venv-before"
old_moved=1
mv "$recovery/venv-next" backend/.venv
new_moved=1
# Console scripts created in staging must point at the final venv path.
backend/.venv/bin/python - "$recovery/venv-next" <<'PY'
import pathlib,sys
prefix=('#!'+sys.argv[1]+'/bin/python').encode()
for p in pathlib.Path('backend/.venv/bin').iterdir():
    if p.is_file() and not p.is_symlink():
        raw=p.read_bytes()
        if raw.startswith(prefix):
            p.write_bytes(raw.replace(prefix,b'#!/srv/salomao/prod/app/backend/.venv/bin/python',1))
PY
sudo -n /usr/bin/systemctl restart salomao-prod.service
healthy=false
for attempt in {1..15}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8100/api/v1/health >/dev/null 2>&1; then healthy=true; break; fi
  sleep 2
done
[[ $healthy == true ]]
sha256sum --status --check "$recovery/env.sha256"
curl -fsS --max-time 15 https://salomao.raquel-talita.vps-kinghost.net/api/v1/health >/dev/null
trap - ERR INT TERM
printf '%s\n' "$target" > "$recovery/applied"
echo "Correcao aplicada e HTTPS validado. Recuperacao: $recovery"
echo 'SMTP preservado; nenhum banco, backup ou e-mail alterado.'

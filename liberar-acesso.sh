#!/usr/bin/env bash
# Salomao: janela temporaria de Tailscale SSH. Nao altera SMTP, firewall ou sudoers.
set -euo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'Execute: sudo bash liberar-acesso.sh [revogar]'; exit 1; }
[[ $# -le 1 && "${1:-liberar}" =~ ^(liberar|revogar)$ ]] || exit 1
exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8 /usr/bin/python3 -I - "${1:-liberar}" <<'PY'
import datetime,json,os,pathlib,stat,subprocess,sys,tempfile
os.umask(0o077)
base=pathlib.Path('/etc/systemd/system')
name='salomao-temporary-tailscale-ssh-expiry'
service=base/(name+'.service'); timer=base/(name+'.timer')
ts=pathlib.Path('/usr/bin/tailscale')
def run(args):
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=40)
    if p.returncode: raise RuntimeError('Comando administrativo falhou; nenhuma credencial foi exibida.')
    return p.stdout

def trusted_dir(path):
    for p in [*reversed(path.parents),path]:
        s=p.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:
            raise RuntimeError('Diretorio administrativo com permissoes inesperadas.')

def write(path,content):
    if path.exists() or path.is_symlink():
        s=path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:
            raise RuntimeError('Arquivo existente inseguro; preservado.')
        if '# Salomao temporary SSH window' not in path.read_text():
            raise RuntimeError('Arquivo existente nao pertence a este script; preservado.')
    fd,tmp=tempfile.mkstemp(prefix='.salomao-ssh-',dir=base)
    try:
        with os.fdopen(fd,'w') as f:f.write(content);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644);os.replace(tmp,path)
    finally:pathlib.Path(tmp).unlink(missing_ok=True)

try:
    trusted_dir(base)
    if not ts.is_file():raise RuntimeError('Tailscale nao encontrado em /usr/bin/tailscale.')
    if sys.argv[1]=='revogar':
        run([ts,'set','--ssh=false'])
        subprocess.run(['systemctl','disable','--now',name+'.timer'],capture_output=True)
        print('Tailscale SSH desativado. Remova tambem a permissao temporaria no painel Tailscale.')
        raise SystemExit(0)
    state=json.loads(run([ts,'status','--json']))
    if state.get('BackendState')!='Running' or '100.81.12.64' not in state.get('Self',{}).get('TailscaleIPs',[]):
        raise RuntimeError('Este nao e o servidor Salomao conectado esperado; nada liberado.')
    deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=4)).replace(microsecond=0)
    calendar=deadline.strftime('%Y-%m-%d %H:%M:%S UTC')
    run(['systemd-analyze','calendar',calendar])
    write(service,'''# Salomao temporary SSH window
[Unit]
Description=Encerrar janela temporaria de Tailscale SSH do Salomao
Wants=tailscaled.service
After=tailscaled.service
StartLimitIntervalSec=0
[Service]
Type=oneshot
ExecStart=/usr/bin/tailscale set --ssh=false
Restart=on-failure
RestartSec=30s
''')
    write(timer,'''# Salomao temporary SSH window
[Unit]
Description=Expiracao de acesso temporario ao Salomao
[Timer]
OnCalendar='''+calendar+'''
Persistent=true
AccuracySec=1s
RandomizedDelaySec=0
Unit='''+name+'''.service
[Install]
WantedBy=timers.target
''')
    run(['systemctl','daemon-reload'])
    run(['systemctl','enable',name+'.timer'])
    run(['systemctl','restart',name+'.timer'])
    run(['systemctl','is-active','--quiet',name+'.timer'])
    # Enable access only after the persistent expiry timer is active.
    try:run([ts,'set','--ssh=true'])
    except Exception:
        subprocess.run([str(ts),'set','--ssh=false'],capture_output=True,timeout=40)
        raise
    print('Tailscale SSH habilitado por quatro horas no servidor.')
    print('Encerramento automatico agendado: '+calendar)
    print('A politica central ainda precisa autorizar TCP 22 e SSH somente como salomao, para sua conta.')
    print('Sem alteracoes de email, bancos, firewall ou sudoers. Nenhum sudo sem senha criado.')
    print('Revogar antes do prazo: sudo bash liberar-acesso.sh revogar')
    print('Ao concluir, remover tambem as regras temporarias no painel Tailscale.')
except Exception as exc:
    print(str(exc) if isinstance(exc,RuntimeError) else 'Falha na preparacao do acesso; revisar pelo console.',file=sys.stderr)
    raise SystemExit(1)
PY

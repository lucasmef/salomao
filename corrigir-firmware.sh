#!/bin/bash
# Only repair the fwupd daemon/library mismatch. Never install device firmware.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
umask 077
[[ $EUID -eq 0 && $# -eq 0 ]] || exit 2
[[ $(systemd-detect-virt) == xen ]] || { echo 'Virtualizacao mudou; revisar'; exit 1; }
# Share the maintenance lock without truncating any user-controlled file.
if [[ -f /home/salomao/.security-oct2.lock && ! -L /home/salomao/.security-oct2.lock ]]; then
  exec 9</home/salomao/.security-oct2.lock
  flock -x 9
fi
recovery=$(mktemp -d /var/backups/salomao-fwupd-20261002.XXXXXX)
export SALOMAO_FWUPD_RECOVERY="$recovery"
python3 - <<'PY'
import hashlib,json,os,subprocess
from pathlib import Path
r=Path(os.environ['SALOMAO_FWUPD_RECOVERY'])
units=['salomao-prod.service','salomao-dev.service','salomao-inter-dev.service','nginx.service','postfix.service']
envs=['/srv/salomao/prod/salomao-config/backend.env','/srv/salomao/dev/salomao-config/backend.env','/srv/salomao/inter-dev/app/backend/.env']
s={'pids':{u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in units},'envs':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in envs}}
(r/'before.json').write_text(json.dumps(s))
p=subprocess.run(['apt-get','--simulate','--no-remove','install','fwupd=2.0.20-1ubuntu2~24.04.2','libfwupd3=2.0.20-1ubuntu2~24.04.2'],capture_output=True,text=True,check=True)
(r/'apt-plan.txt').write_text(p.stdout)
installed={line.split()[1] for line in p.stdout.splitlines() if line.startswith('Inst ')}
assert not any(line.startswith('Remv ') for line in p.stdout.splitlines()), 'Removal refused'
assert installed <= {'fwupd','libfwupd3'}, 'Unexpected package refused'
PY
tar --ignore-failed-read -czf "$recovery/fwupd-config-before.tar.gz" /etc/fwupd /etc/systemd/system/fwupd.service.d /var/lib/fwupd 2>"$recovery/tar.log"
dpkg-query -W fwupd libfwupd2 > "$recovery/versions-before.txt"
apt-get --yes --no-remove -o Dpkg::Options::=--force-confold install fwupd=2.0.20-1ubuntu2~24.04.2 libfwupd3=2.0.20-1ubuntu2~24.04.2 > "$recovery/apt.log" 2>&1
# Only these two updater units may be restarted.
systemctl restart fwupd.service
systemctl start fwupd-refresh.service || true
python3 - <<'PY'
import hashlib,json,os,pwd,subprocess,tempfile
from pathlib import Path
r=Path(os.environ['SALOMAO_FWUPD_RECOVERY']);s=json.loads((r/'before.json').read_text())
report={'recovery':str(r),'pids_unchanged':all(subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip()==p for u,p in s['pids'].items()),'smtp_env_files_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in s['envs'].items())}
for u in ['fwupd.service','fwupd-refresh.service']:
 report[u]=subprocess.check_output(['systemctl','show',u,'-p','Result','-p','ActiveState','-p','ExecMainStatus'],text=True)
try:
 p=subprocess.run(['fwupdmgr','get-devices','--json'],capture_output=True,text=True,timeout=30)
 report['device_query_exit']=p.returncode
 # Device serials and identifiers remain in the root-only recovery directory.
 (r/'devices.json').write_text(p.stdout)
except subprocess.TimeoutExpired: report['device_query_timeout']=True
(r/'result.json').write_text(json.dumps(report,indent=2))
u=pwd.getpwnam('salomao');fd,tmp=tempfile.mkstemp(prefix='.fwupd-result-',dir='/home/salomao')
with os.fdopen(fd,'w') as f:
 json.dump(report,f,indent=2);os.fchown(f.fileno(),u.pw_uid,u.pw_gid)
os.replace(tmp,'/home/salomao/resultado-firmware.json')
assert report['pids_unchanged'] and report['smtp_env_files_unchanged'], 'Unexpected change; review required'
print('Pacotes do atualizador corrigidos. Nenhum firmware fisico instalado.')
print('Salomao e SMTP preservados. Relatorio disponivel para verificacao por SSH.')
PY

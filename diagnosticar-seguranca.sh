#!/bin/bash
# Fixed read-only root diagnostics for Salomao. No grants or service changes.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash diagnosticar-seguranca.sh'; exit 1; }
[[ $# -eq 0 ]] || exit 2
/usr/bin/python3 - <<'PY'
import json, os, pwd, re, subprocess, tempfile
from pathlib import Path

def run(args, timeout=20):
    try:
        p=subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {'exit':p.returncode,'output':p.stdout+p.stderr}
    except subprocess.TimeoutExpired:
        return {'timeout':True}

result={}
result['virtualization']=run(['/usr/bin/systemd-detect-virt'])
result['firmware_journal']=run(['/usr/bin/journalctl','-u','fwupd.service','-u','fwupd-refresh.service','-n','80','--no-pager','-o','cat'])
result['firmware_devices']=run(['/usr/bin/fwupdmgr','get-devices','--json'],25)
result['packages']=run(['/usr/bin/dpkg-query','-W','-f=${Package} ${Version}\n','fwupd','libfwupd2','linux-firmware'])
result['backup']=run(['/usr/bin/systemctl','show','salomao-prod-backup.service','-p','Result','-p','ExecMainStatus','-p','ExecMainExitTimestamp'])
# These fixed units do not contain application/email settings. Redact identifiers
# and URL credentials defensively before exporting the diagnostic report.
s=json.dumps(result,ensure_ascii=False,indent=2)
s=re.sub(r'(?i)(password|token|secret|authorization)([=: ]+)[^\s"\\]+',r'\1\2[redacted]',s)
s=re.sub(r'https?://[^\s"\\]+','[url]',s)
s=re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[email]',s)
user=pwd.getpwnam('salomao')
# Atomic replacement does not follow an existing symlink at the report path.
fd,path=tempfile.mkstemp(prefix='.security-diagnostic-',dir='/home/salomao')
with os.fdopen(fd,'w') as f:
    f.write(s+'\n')
    f.flush(); os.fsync(f.fileno()); os.fchown(f.fileno(),user.pw_uid,user.pw_gid)
os.replace(path,'/home/salomao/diagnostico-seguranca.json')
print('Diagnostico concluido. Codex pode ler o relatorio por SSH.')
print('Nenhum servico, SMTP, banco, firewall ou autorizacao sudo foi alterado.')
PY

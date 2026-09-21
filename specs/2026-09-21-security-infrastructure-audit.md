# Auditoria de segurança do repositório e infraestrutura representada

## Metadata

- Status: review
- Mode: research
- Complexity: high
- Created: 2026-09-21
- Updated: 2026-09-21

## Objective

Auditar a segurança da aplicação, do repositório, de dependências, CI/CD e da infraestrutura representada, separando evidência confirmada, risco de configuração, dívida de atualização, hardening e itens não aplicáveis.

## Scope

- [x] SAL-003: aplicação e repositório.
- [x] SAL-004: configuração e versões da infraestrutura verificáveis sem acesso à VPS.
- [x] Executar o scanner oficial e inspeção proporcional de código, dependências, workflows e scripts.

## Out of scope

- Acesso, comandos ou mudanças na VPS/produção.
- Deploy, restart, atualização, migração, dados reais ou rotação de segredos.

## Grill Gate

Decision: not_needed

Reason: trata-se de auditoria read-only explicitamente autorizada; verificações live não autorizadas serão listadas como pendentes, sem serem executadas.

## Sensitive-work plan

1. Mapear superfícies: autenticação, autorização, API, sessão, arquivos, cabeçalhos, segredos, logs e dependências.
2. Inspecionar scripts, workflows e documentação de deploy sem executar operação remota.
3. Rodar `python scripts/security_scan.py` e os checks locais seguros disponíveis.
4. Classificar achados e registrar evidências redigidas, impacto e próximos passos.

## Progress

- 2026-09-21 - Contexto, arquitetura, deploy e regras específicas de segurança carregados.
- 2026-09-21 - Scanner oficial passou; testes de configuração, primitivas, MFA/sessões e alertas passaram (14 testes).
- 2026-09-21 - `pip-audit` encontrou vulnerabilidades conhecidas nas versões travadas de AnyIO, Click, Cryptography e pypdf. Nenhum valor sensível foi registrado.
- 2026-09-21 - Inspecionados autenticação/autorização, sessão/MFA, CORS/headers, upload, logs, isolamento por empresa, dependências, CI/CD e scripts de auditoria de VPS.

## Decisions

- Decision: SAL-003 e SAL-004 compartilham esta spec de auditoria, com seções e rastreabilidade separadas.
  Reason: ambos são levantamento read-only do mesmo perímetro operacional e dependem das mesmas fontes (configuração versionada, workflows e scripts).
  ADR needed: no

## Validation

Commands run:

- [x] `uv run --project backend python scripts/security_scan.py`
- [x] `cd backend && PYTHONPATH=. uv run --extra dev pytest tests/test_config_security.py tests/test_security_primitives.py tests/test_auth_trusted_devices.py tests/test_security_alerts.py -q`
- [x] `cd backend && uv export --all-extras --no-hashes --output-file /private/tmp/salomao-audit-requirements.txt && uv run --with pip-audit pip-audit -r /private/tmp/salomao-audit-requirements.txt`
- [x] Inspeção de manifestos, rotas, serviços, workflows e scripts.
- [ ] `npm audit --audit-level=high` — não executado: `npm` não está instalado no host. `pnpm audit --prod --json` não é compatível com o único lockfile disponível (`package-lock.json`).
- [ ] Auditoria live da VPS — fora da autorização desta rodada.

Results:

- Scanner oficial: passou.
- Testes de segurança: 14 passaram; somente avisos de depreciação de dependências/framework.
- `pip-audit`: 25 entradas de advisory em 4 pacotes; classificação e versões de correção abaixo.
- Nenhuma verificação live foi interpretada como evidência de segurança.

## Next step

SAL-003 concluído em revisão; SAL-004 concluído apenas para o perímetro versionado e permanece pendente de auditoria live autorizada.

## SAL-003 findings

### Vulnerabilidades confirmadas

- **Alta — pypdf 6.13.3 vulnerável.** `pip-audit` encontrou múltiplos advisories com correções distribuídas entre 6.14.0 e 6.16.1. O pacote processa PDFs recebidos de integração antes de gerar exportações; atualizar para pelo menos 6.16.1, revisar changelog e testar a exportação de boletos.
- **Alta — cryptography 48.0.1 vulnerável.** Há correções disponíveis em 49.0.0 e 50.0.0. Como a aplicação cifra credenciais e usa mTLS, tratar como atualização prioritária e validar cifragem/decifragem, TLS e integração em ambiente seguro.
- **Média — AnyIO 4.13.0 e Click 8.3.2 vulneráveis.** Correções informadas: AnyIO 4.14.2 e Click 8.3.3. Atualizar lockfile e executar a suíte de backend.
- **Média — uploads e extração de ZIP são ilimitados.** Rotas autenticadas usam `await file.read()` e serviços leem entradas ZIP em memória sem limites explícitos de tamanho, quantidade ou taxa de expansão. Um usuário autenticado pode provocar exaustão de memória/disco/CPU com arquivo grande ou compactado malicioso. Limitar corpo/arquivo, número/tamanho total descompactado e validar tipo/estrutura antes do parse.

### Configurações de risco

- **Média — telemetria pública de erro aceita texto ilimitado e o persiste em log.** `POST /api/v1/meta/client-error` não requer sessão, não usa rate limiting e registra URL, detalhes e user agent. A rotação limita o arquivo, mas permite poluição de logs e potencial retenção de dados sensíveis enviados pelo cliente. Restringir tamanhos, aplicar rate limit e redigir query strings/detalhes.
- **Média — logs HTTP registram a query string inteira; exceções registram `str(exc)`.** Permissões locais são restritivas (diretório 0750, arquivo 0640), mas parâmetros sensíveis ou mensagens de exceção podem permanecer no disco. Adotar allowlist/redação de parâmetros e não registrar detalhes não confiáveis em exceções.
- **Baixa — isolamento por empresa não é imposto pelo usuário atual.** `get_current_company` usa a empresa padrão e é chamado pela maior parte das rotas; o modelo armazena `company_id`. A aplicação aparenta tenant único, mas uma evolução multiempresa precisaria de escopo pelo usuário. Não é BOLA confirmado no modelo atual; é risco de desenho.

### Hardening recomendado

- Adicionar CSP baseada no frontend real, `Strict-Transport-Security` no proxy e `Cross-Origin-Opener-Policy`; headers atuais cobrem frame, MIME, referrer, permissions e cache só em modo servidor.
- Trocar rate limiting em memória por mecanismo compartilhado (Redis já presente) caso haja mais de um processo/instância.
- Revisar dispositivo confiável MFA (janela de 15 dias, sinalização de mudança de agente e revogação global após troca de senha).
- Adicionar verificação de dependências Python ao workflow `Security Checks`; hoje ele só executa scanner de arquivos e `npm audit` do frontend.
- Corrigir referências históricas de infraestrutura que ainda contêm identificadores reais em documentação versionada; não foram reproduzidas nesta spec.

### Falsos positivos / não aplicável

- SQL injection: não foi encontrado SQL textual construído com entrada do usuário nas superfícies amostradas; consultas são SQLAlchemy/parametrizadas.
- XSS: a UI React não mostrou `dangerouslySetInnerHTML` na busca estática.
- CSRF: autenticação normal usa cookie `HttpOnly` com `SameSite=Lax`, origem CORS explícita e header de autenticação desativado em servidor. Reavaliar se autenticação cross-site for habilitada.
- Segredos rastreados: scanner oficial passou; exemplos de ambiente usam placeholders. Busca histórica por padrões de chave não produziu conteúdo e não é evidência de segredo ativo.

## SAL-004 findings

### Evidência representada no repositório

- Produção prevista: Nginx/TLS, systemd, PostgreSQL, UFW, fail2ban e backend restrito a loopback; homologação e SSH previstos via Tailscale. `scripts/check-prod.sh` verifica serviços, portas, firewall, política SSH, TLS e runtime.
- CI/CD usa ações principais versionadas e permissões mínimas declaradas (`contents: read`, deploy somente nos workflows de deploy).
- Não há Docker/Compose versionado para Salomão nem inventário versionado de versões do SO, Nginx, PostgreSQL, Redis, UFW, fail2ban, OpenSSH, serviços, processos ou backups reais. Não é possível declarar versão, suporte ou exposição live desses componentes.

### Dívida de atualização

- As dependências Python acima são o runtime verificável com correções disponíveis. A atualização deve alterar `backend/pyproject.toml`/`uv.lock` em spec própria, com testes de regressão e sem tocar a VPS.
- A ausência de auditoria de dependência Python no CI é dívida de cobertura, não confirmação de vulnerabilidade do host.

### Verificações pendentes que exigem autorização de acesso à VPS

- Estado/SO e pacotes: `cat /etc/os-release`, `uname -r`, `apt-cache policy`, `systemctl --version`.
- Serviços/processos/portas: `systemctl --no-pager --type=service --state=running`, `ps auxww`, `sudo ss -ltnp`.
- Firewall, SSH e proxy: `sudo ufw status numbered`, `sudo sshd -T`, `sudo nginx -T` e `sudo nginx -t`.
- TLS: `openssl s_client` contra o host público e leitura de datas/cadeia, sem exibir chave privada.
- Dados/Redis/backups: versões e listeners de PostgreSQL/Redis, política de backup e restauração, permissões e retenção; nunca listar valores de ambiente ou conteúdo de backups.
- Auditoria consolidada: `bash scripts/check-prod.sh` requer privilégios e inclui dry-run de renovação de certificado; não foi executado.

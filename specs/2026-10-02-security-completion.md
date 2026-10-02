# Conclusão da auditoria Salomão

## Metadata
- Status: in_progress
- Mode: bugfix
- Complexity: high
- Created: 2026-10-02
- Updated: 2026-10-02

## Objetivo e critérios
Corrigir dependências vulneráveis efetivamente usadas e preservar registro de falha dos resumos. Concluir diagnóstico de firmware, backup externo e acesso temporário sem alterar SMTP, bancos ativos ou regras financeiras.

## Contexto e Grill Gate
Autorização explícita nesta conversa para corrigir servidor e concluir as pendências; operações sudo pelo console do usuário, scripts publicados via Git. Produção está em 8d73881 (SMTP), não em main. Base preservada para não remover funcionalidades. Destino do backup externo aguardando escolha. Nenhuma necessidade de perguntar novamente sobre correções já autorizadas.

## Plano sensível e ordem
1. Atualizar cryptography, AnyIO, pypdf e Click com lock reproduzível; auditar frontend da base real.
2. Persistir erro de envio no audit existente, sem esquema novo, credenciais ou reenvio.
3. Testar backend, lint, build e scanners; publicar correções e script administrativo restrito via Git.
4. Diagnosticar fwupd como root; agir apenas conforme evidência. Preservar recuperação e serviços.
5. Configurar backup externo no destino autorizado; validar cópia e autenticação.
6. Revisar DNS e encerrar acesso temporário somente depois das verificações.

## Compatibilidade e reversão
Sem migração, alteração SMTP ou operação financeira. Reversão de código/dependências para o snapshot anterior. Antes de aplicação, guardar cópias protegidas e conferir saúde. Nenhuma promoção ampla de dev/main nem substituição da versão SMTP. Diagnóstico de firmware não instala firmware físico numa VPS. Chaves e relatórios administrativos ficam fora do Git.

## Validação prevista
- uv sync --extra dev; uv run pytest; ruff check arquivos alterados.
- uv export e pip-audit; npm audit, typecheck/build; security_scan.py.
- Teste de falha de envio persistente depois de execução seguinte, sem dados sensíveis.
- Saúde HTTPS e ambientes após alterações, comparação SMTP sem exibir valores.

## Fora do escopo
Reenvio de e-mails, mudanças nas regras de baixa e sincronização, auditoria integral de código.

## Progresso
- Inventário atual: fwupd/refresh falhos; três ambientes saudáveis. Produção usa AnyIO 4.13.0, cryptography 48.0.1, pypdf 6.14.2.
- 19 alertas GitHub pertencem à branch padrão; frontend da produção já tem correções que não chegaram a main.

## Validação parcial
- Backend: 319 testes passaram, 21 avisos de depreciação preexistentes.
- Ruff dirigido: passou.
- pip-audit do novo lock: nenhuma vulnerabilidade conhecida.
- npm audit do frontend de produção: zero vulnerabilidades.
- Diagnóstico root publicado em 7af3a18 e baixado via Git; aguarda execução no console.
- Registro email_error persistente usa somente classe da exceção; SMTP e gatilhos de envio preservados.

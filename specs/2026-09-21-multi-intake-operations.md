# Rodada multi-intake: operação e documentação

## Metadata

- Status: done
- Mode: architecture
- Complexity: architectural
- Created: 2026-09-21
- Updated: 2026-09-21

## Objective

Regularizar a documentação operacional para rodadas com múltiplos IDs SAL, preservando BuilderFlow como processo primário e uma rastreabilidade individual por ID.

## Scope

- [x] SAL-001: atualizar contexto, instruções operacionais, DOIT e ADR.
- [x] Registrar a decisão operacional durável sem criar um segundo sistema de PRDs.

## Out of scope

- Alterar fluxo de deploy, produção ou dados reais.

## Grill Gate

Decision: not_needed

Reason: o pedido define o resultado e os caminhos reais serão descobertos no repositório; não há decisão material de produto pendente para documentação operacional.

## Progress

- 2026-09-21 - Contexto obrigatório e skills BuilderFlow, gestor-financeiro-workflow e gestor-financeiro-docs carregados.
- 2026-09-21 - Branch remota `origin/dev` atualizada e worktree isolado criado, sem tocar no checkout sujo original.
- 2026-09-21 - Confirmado que `.agents/skills/builderflow/SKILL.md` e `.agents/skills/gestor-financeiro-workflow/SKILL.md` existem; `.claude/skills/builderflow/SKILL.md` não existe.
- 2026-09-21 - Regularizadas as instruções, o contexto durável, a referência do DOIT e o ADR operacional.

## Decisions

- Decision: uma spec para a regularização documental, separada das auditorias.
  Reason: mudança operacional durável, de risco arquitetural, mas sem mudança de aplicação.
  ADR needed: yes

## Validation

Commands run:

- [x] `uv run --project backend python scripts/security_scan.py`
- [x] `git diff --check`
- [x] Busca por referências inexistentes em `AGENTS.md`, `DOIT.md`, `docs/` e `.agents/`

Results:

- Scanner oficial: passou, sem arquivo bloqueado ou padrão de segredo de alta confiança.
- `git diff --check`: passou.
- A referência inexistente `$gestor-financeiro-doit-workflow` foi substituída por `$gestor-financeiro-workflow`; a referência `.claude/skills/builderflow/SKILL.md` foi removida em favor do caminho real `.agents/skills/builderflow/SKILL.md`.

## Files changed

- `AGENTS.md` - fluxo de rodada multi-intake, rastreabilidade individual e evidência visual.
- `.agents/skills/builderflow/SKILL.md` - BuilderFlow passou a admitir decomposição autônoma sem sistema paralelo de PRD.
- `.agents/skills/gestor-financeiro-workflow/SKILL.md` - regra do projeto alinhada a BuilderFlow e à referência instalada.
- `docs/CONTEXT.md` - contexto genérico substituído por fatos verificados de produto, stack, operação, validação e áreas sensíveis.
- `DOIT.md` - referência de skill corrigida.
- `docs/ADR.md` - ADR-002 registra a decisão operacional durável.

## Next step

SAL-001 concluído; aguardar a resposta Grill Me de SAL-002 apenas para alterações futuras dependentes de prioridades de tabela.

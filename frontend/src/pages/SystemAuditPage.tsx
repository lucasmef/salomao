import { SectionChrome } from "../components/SectionChrome";
import { Button } from "../components/ui";
import type { MainNavChild } from "../data/navigation";
import { formatDate } from "../lib/format";
import type { BackupRead, ImportSummary } from "../types";

type Props = {
  tabs: MainNavChild[];
  importSummary: ImportSummary;
  backups: BackupRead[];
};

export function SystemAuditPage({ tabs, importSummary, backups }: Props) {
  const currentTab = tabs.find((item) => item.key === "auditoria") ?? tabs[0];
  const eventCount = importSummary.import_batches.length + backups.length;

  return (
    <SectionChrome
      sectionLabel="Sistema"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Período
            <input type="date" />
          </label>
          <label>
            Usuário
            <input placeholder="Todos" />
          </label>
          <label>
            Evento
            <input placeholder="Importação, backup..." />
          </label>
          <Button type="button" variant="primary">
            Atualizar
          </Button>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Eventos do período</span><strong>{eventCount}</strong></article>
        <article className="kpi-card"><span>Importações</span><strong>{importSummary.import_batches.length}</strong></article>
        <article className="kpi-card"><span>Backups</span><strong>{backups.length}</strong></article>
        <article className="kpi-card"><span>Restauros</span><strong>0</strong></article>
      </section>

      <section className="panel">
        <div className="table-shell">
          <table className="erp-table">
            <thead><tr><th>Data/Hora</th><th>Usuário</th><th>Evento</th><th>Detalhe</th></tr></thead>
            <tbody>
              {importSummary.import_batches.slice(0, 8).map((batch) => (
                <tr key={batch.id}>
                  <td>{formatDate(batch.created_at)}</td>
                  <td>Sistema</td>
                  <td>Importação concluída</td>
                  <td>{batch.filename}</td>
                </tr>
              ))}
              {backups.slice(0, 8).map((backup) => (
                <tr key={backup.filename}>
                  <td>{formatDate(backup.created_at)}</td>
                  <td>Sistema</td>
                  <td>Backup criado</td>
                  <td>{backup.filename}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

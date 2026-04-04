import { useMemo, useState } from "react";

import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatEntryStatus } from "../lib/format";
import type { Account, ImportSummary } from "../types";

type Props = {
  tabs: MainNavChild[];
  accounts: Account[];
  importSummary: ImportSummary;
  submitting: boolean;
  onUploadHistorical: (file: File) => Promise<void>;
  onSyncInterStatement: () => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return (
    importSummary.import_batches.find((batch) =>
      sourceType.endsWith(":") ? batch.source_type.startsWith(sourceType) : batch.source_type === sourceType,
    ) ?? null
  );
}

export function SystemImportsGeneralPage({
  tabs,
  accounts,
  importSummary,
  submitting,
  onUploadHistorical,
  onSyncInterStatement,
}: Props) {
  const currentTab = tabs.find((item) => item.key === "importacoes-gerais") ?? tabs[0];
  const [historicalFile, setHistoricalFile] = useState<File | null>(null);
  const hasInterAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const latestHistoricalImport = useMemo(() => latestBatchFor(importSummary, "historical_cashbook"), [importSummary]);
  const latestInterStatementImport = useMemo(
    () => latestBatchFor(importSummary, "inter_statement"),
    [importSummary],
  );

  return (
    <SectionChrome
      sectionLabel="Sistema"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="content-grid two-columns">
        <article className="panel compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Histórico</p>
            <h3>Livro caixa antigo</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xlsx" onChange={(event) => setHistoricalFile(event.target.files?.[0] ?? null)} />
            <div className="import-last-meta">
              {latestHistoricalImport ? `Última importação: ${latestHistoricalImport.filename} em ${formatDate(latestHistoricalImport.created_at)}` : "Última importação: nenhuma"}
            </div>
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !historicalFile}
              onClick={() => historicalFile && void onUploadHistorical(historicalFile)}
              type="button"
            >
              Importar
            </button>
          </div>
        </article>

        <article className="panel compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Banco Inter</p>
            <h3>Extrato</h3>
          </div>
          <div className="compact-upload-box">
            {!hasInterAccount && (
              <div className="import-last-meta">Nenhuma conta com API Inter habilitada.</div>
            )}
            <div className="import-last-meta">
              {latestInterStatementImport
                ? `Última sincronização: ${latestInterStatementImport.filename} em ${formatDate(latestInterStatementImport.created_at)}`
                : "Última sincronização: nenhuma"}
            </div>
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !hasInterAccount}
              onClick={() => void onSyncInterStatement()}
              type="button"
            >
              Atualizar
            </button>
          </div>
        </article>

      </section>

      <section className="panel">
        <div className="panel-title"><h3>Histórico de importações</h3></div>
        <div className="table-shell">
          <table className="erp-table">
            <thead><tr><th>Data</th><th>Arquivo</th><th>Tipo</th><th>Processo</th><th>Status</th><th>Observação</th></tr></thead>
            <tbody>
              {importSummary.import_batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{formatDate(batch.created_at)}</td>
                  <td>{batch.filename}</td>
                  <td>{batch.source_type}</td>
                  <td>{batch.records_valid}/{batch.records_total}</td>
                  <td>{formatEntryStatus(batch.status)}</td>
                  <td>{batch.error_summary ?? "Processado sem observações."}</td>
                </tr>
              ))}
              {!importSummary.import_batches.length && (
                <tr>
                  <td colSpan={6} className="empty-cell">Nenhuma importação registrada ainda.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

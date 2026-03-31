import { useMemo, useState } from "react";

import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatEntryStatus } from "../lib/format";
import type { ImportSummary } from "../types";

type Props = {
  tabs: MainNavChild[];
  importSummary: ImportSummary;
  submitting: boolean;
  onUploadHistorical: (file: File) => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

export function SystemImportsGeneralPage({ tabs, importSummary, submitting, onUploadHistorical }: Props) {
  const currentTab = tabs.find((item) => item.key === "importacoes-gerais") ?? tabs[0];
  const [historicalFile, setHistoricalFile] = useState<File | null>(null);
  const latestHistoricalImport = useMemo(() => latestBatchFor(importSummary, "historical_cashbook"), [importSummary]);

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
            <p className="eyebrow">Historico</p>
            <h3>Livro caixa antigo</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xlsx" onChange={(event) => setHistoricalFile(event.target.files?.[0] ?? null)} />
            <div className="import-last-meta">
              {latestHistoricalImport ? `Ultima importacao: ${latestHistoricalImport.filename} em ${formatDate(latestHistoricalImport.created_at)}` : "Ultima importacao: nenhuma"}
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

        <article className="panel">
          <div className="panel-title"><h3>Base importada</h3></div>
          <div className="summary-list">
            <div className="summary-row"><span>Faturamento</span><strong>{importSummary.sales_snapshot_count}</strong></div>
            <div className="summary-row"><span>Titulos a receber</span><strong>{importSummary.receivable_title_count}</strong></div>
            <div className="summary-row"><span>Movimentos OFX</span><strong>{importSummary.bank_transaction_count}</strong></div>
            <div className="summary-row"><span>Livro caixa</span><strong>{importSummary.historical_cashbook_count}</strong></div>
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-title"><h3>Historico de importacoes</h3></div>
        <div className="table-shell">
          <table className="erp-table">
            <thead><tr><th>Data</th><th>Arquivo</th><th>Tipo</th><th>Processo</th><th>Status</th><th>Observacao</th></tr></thead>
            <tbody>
              {importSummary.import_batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{formatDate(batch.created_at)}</td>
                  <td>{batch.filename}</td>
                  <td>{batch.source_type}</td>
                  <td>{batch.records_valid}/{batch.records_total}</td>
                  <td>{formatEntryStatus(batch.status)}</td>
                  <td>{batch.error_summary ?? "Processado sem observacoes."}</td>
                </tr>
              ))}
              {!importSummary.import_batches.length && (
                <tr>
                  <td colSpan={6} className="empty-cell">Nenhuma importacao registrada ainda.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

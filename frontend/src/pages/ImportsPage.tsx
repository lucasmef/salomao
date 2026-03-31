import { useMemo, useState } from "react";

import { formatDate, formatEntryStatus } from "../lib/format";
import type { Account, ImportBatch, ImportSummary } from "../types";

type Props = {
  submitting: boolean;
  accounts: Account[];
  importSummary: ImportSummary;
  onUpload: (path: string, file: File, fields?: Record<string, string>) => Promise<void>;
};

function latestBatchFor(importBatches: ImportBatch[], sourceType: string) {
  return (
    importBatches.find((batch) =>
      sourceType === "ofx" ? batch.source_type.startsWith("ofx:") : batch.source_type === sourceType,
    ) ?? null
  );
}

export function ImportsPage({ submitting, accounts, importSummary, onUpload }: Props) {
  const [salesFile, setSalesFile] = useState<File | null>(null);
  const [receivablesFile, setReceivablesFile] = useState<File | null>(null);
  const [ofxFile, setOfxFile] = useState<File | null>(null);
  const [historicalCashbookFile, setHistoricalCashbookFile] = useState<File | null>(null);
  const [ofxAccountId, setOfxAccountId] = useState("");
  const ofxAccounts = useMemo(
    () => accounts.filter((account) => account.is_active && account.import_ofx_enabled),
    [accounts],
  );

  const latestImports = useMemo(
    () => ({
      sales: latestBatchFor(importSummary.import_batches, "linx_sales"),
      receivables: latestBatchFor(importSummary.import_batches, "linx_receivables"),
      ofx: latestBatchFor(importSummary.import_batches, "ofx"),
      historical: latestBatchFor(importSummary.import_batches, "historical_cashbook"),
    }),
    [importSummary.import_batches],
  );

  function renderLastImport(batch: ImportBatch | null) {
    if (!batch) {
      return <div className="import-last-meta">Ultima importacao: nenhuma</div>;
    }
    return (
      <div className="import-last-meta">
        Ultima importacao: {batch.filename} em {formatDate(batch.created_at)}
      </div>
    );
  }

  return (
    <div className="page-layout">
      <section className="content-grid two-columns">
        <article className="panel-card compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Linx</p>
            <h3>Importar faturamento</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xls,.html" onChange={(event) => setSalesFile(event.target.files?.[0] ?? null)} />
            {renderLastImport(latestImports.sales)}
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !salesFile}
              onClick={() => salesFile && void onUpload("/imports/linx-sales", salesFile)}
              type="button"
            >
              Importar
            </button>
          </div>
        </article>

        <article className="panel-card compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Linx</p>
            <h3>Importar faturas a receber</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xls,.xlsx,.html,.zip" onChange={(event) => setReceivablesFile(event.target.files?.[0] ?? null)} />
            {renderLastImport(latestImports.receivables)}
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !receivablesFile}
              onClick={() => receivablesFile && void onUpload("/imports/linx-receivables", receivablesFile)}
              type="button"
            >
              Importar
            </button>
          </div>
        </article>

        <article className="panel-card compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Historico</p>
            <h3>Livro caixa antigo</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xlsx" onChange={(event) => setHistoricalCashbookFile(event.target.files?.[0] ?? null)} />
            {renderLastImport(latestImports.historical)}
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !historicalCashbookFile}
              onClick={() => historicalCashbookFile && void onUpload("/imports/historical-cashbook", historicalCashbookFile)}
              type="button"
            >
              Importar
            </button>
          </div>
        </article>

        <article className="panel-card compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Banco</p>
            <h3>Importar OFX</h3>
          </div>
          <div className="compact-upload-box">
            <select value={ofxAccountId} onChange={(event) => setOfxAccountId(event.target.value)}>
              <option value="">Selecionar conta</option>
              {ofxAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
            {!ofxAccounts.length && (
              <div className="import-last-meta">Nenhuma conta com importacao OFX habilitada.</div>
            )}
            <input type="file" accept=".ofx" onChange={(event) => setOfxFile(event.target.files?.[0] ?? null)} />
            {renderLastImport(latestImports.ofx)}
            <button
              className="primary-button compact-action-button"
              disabled={submitting || !ofxFile || !ofxAccountId}
              onClick={() => ofxFile && void onUpload("/imports/ofx", ofxFile, { account_id: ofxAccountId })}
              type="button"
            >
              Importar
            </button>
          </div>
        </article>
      </section>

      <section className="content-grid two-columns">
        <article className="panel-card">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Resumo</p>
            <h3>Base importada</h3>
          </div>
          <div className="stats-grid compact-stats-grid">
            <div className="stat-box"><span>Faturamento</span><strong>{importSummary.sales_snapshot_count}</strong></div>
            <div className="stat-box"><span>Receber</span><strong>{importSummary.receivable_title_count}</strong></div>
            <div className="stat-box"><span>Movimentos OFX</span><strong>{importSummary.bank_transaction_count}</strong></div>
            <div className="stat-box"><span>Livro caixa</span><strong>{importSummary.historical_cashbook_count}</strong></div>
          </div>
        </article>

        <article className="panel-card">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Historico</p>
            <h3>Ultimos lotes importados</h3>
          </div>
          <div className="table-list compact-table-list">
            {importSummary.import_batches.map((batch) => (
              <div key={batch.id} className="entry-row compact-entry-row">
                <div>
                  <strong>{batch.filename}</strong>
                  <p>{batch.source_type}</p>
                  <p>{batch.error_summary ?? "Processado sem observacoes."}</p>
                </div>
                <div className="entry-aside">
                  <strong>{batch.records_valid}/{batch.records_total}</strong>
                  <p>{formatEntryStatus(batch.status)}</p>
                </div>
              </div>
            ))}
            {!importSummary.import_batches.length && <p className="empty-state">Nenhuma importacao realizada ainda.</p>}
          </div>
        </article>
      </section>
    </div>
  );
}

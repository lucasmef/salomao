import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDateTime, formatEntryStatus } from "../lib/format";
import type { Account, ImportBatch, ImportSummary } from "../types";

type Props = {
  tabs: MainNavChild[];
  accounts: Account[];
  importSummary: ImportSummary;
  submitting: boolean;
  onUploadHistorical: (file: File) => Promise<void>;
  onUploadBoletoInter: (file: File) => Promise<void>;
  onSyncCustomers: () => Promise<void>;
  onSyncInterCharges: () => Promise<void>;
  onSyncInterStatement: () => Promise<void>;
  onSyncReceivables: () => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return (
    importSummary.import_batches.find((batch) =>
      sourceType.endsWith(":") ? batch.source_type.startsWith(sourceType) : batch.source_type === sourceType,
    ) ?? null
  );
}

function renderBatchMeta(batch: ImportBatch | null, emptyLabel = "Ultima carga: nenhuma"): ReactNode {
  if (!batch) {
    return <small className="compact-muted">{emptyLabel}</small>;
  }
  return (
    <small className="compact-muted">
      Ultima carga: {batch.filename} em {formatDateTime(batch.created_at)}
    </small>
  );
}

export function SystemImportsGeneralPage({
  tabs,
  accounts,
  importSummary,
  submitting,
  onUploadHistorical,
  onUploadBoletoInter,
  onSyncCustomers,
  onSyncInterCharges,
  onSyncInterStatement,
  onSyncReceivables,
}: Props) {
  const currentTab = tabs.find((item) => item.key === "importacoes-gerais") ?? tabs[0];
  const [historicalFile, setHistoricalFile] = useState<File | null>(null);
  const [interFile, setInterFile] = useState<File | null>(null);
  const hasInterAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const latestHistoricalImport = useMemo(() => latestBatchFor(importSummary, "historical_cashbook"), [importSummary]);
  const latestInterStatementImport = useMemo(() => latestBatchFor(importSummary, "inter_statement"), [importSummary]);
  const latestLinxReceivablesImport = useMemo(
    () => latestBatchFor(importSummary, "linx_open_receivables"),
    [importSummary],
  );
  const latestLinxCustomersImport = useMemo(() => latestBatchFor(importSummary, "linx_customers"), [importSummary]);
  const latestInterBoletoImport = useMemo(() => latestBatchFor(importSummary, "boletos:inter"), [importSummary]);
  const latestInterChargeSync = useMemo(() => latestBatchFor(importSummary, "inter_charge_sync"), [importSummary]);

  async function handleUploadInterReport() {
    if (!interFile) {
      return;
    }
    await onUploadBoletoInter(interFile);
    setInterFile(null);
  }

  return (
    <SectionChrome
      sectionLabel="Sistema"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="content-grid billing-summary-grid">
        <article className="panel-card compact-panel-card billing-summary-panel">
          <div className="panel-title compact-title-row">
            <h3>Importação rápida da cobrança</h3>
          </div>
          <div className="billing-import-meta">
            <small className="compact-muted">O relatório C6 agora é importado pela aba Cobrança &gt; Boletos faltando.</small>
          </div>
          <div className="compact-import-grid billing-import-grid">
            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Faturas Linx API</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting}
                  onClick={() => void onSyncReceivables()}
                  title="Atualizar faturas em aberto da API Linx"
                  type="button"
                >
                  Atualizar
                </button>
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestLinxReceivablesImport)}
                <small className="compact-muted">Usa a base espelho da API para a cobrança.</small>
              </div>
            </div>

            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Clientes Linx API</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting}
                  onClick={() => void onSyncCustomers()}
                  title="Atualizar clientes do Linx"
                  type="button"
                >
                  Atualizar
                </button>
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestLinxCustomersImport)}
                <small className="compact-muted">Cadastro usado para nome e dados de boleto.</small>
              </div>
            </div>

            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Relatório Inter</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting || !interFile}
                  onClick={() => void handleUploadInterReport()}
                  title="Importar relatório Inter"
                  type="button"
                >
                  Importar
                </button>
              </div>
              <input
                id="system-boletos-inter-file"
                className="hidden-file-input"
                type="file"
                accept=".zip"
                onChange={(event) => setInterFile(event.target.files?.[0] ?? null)}
              />
              <div className="billing-file-picker-row">
                <label className="secondary-button compact-file-trigger" htmlFor="system-boletos-inter-file">
                  Selecionar
                </label>
                {interFile ? (
                  <span className="compact-file-name" title={interFile.name}>
                    {interFile.name}
                  </span>
                ) : null}
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestInterBoletoImport)}
                {interFile ? (
                  <small className="compact-muted" title={interFile.name}>
                    Novo arquivo: {interFile.name}
                  </small>
                ) : null}
              </div>
            </div>

            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Inter</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting || !hasInterAccount}
                  onClick={() => void onSyncInterCharges()}
                  title="Atualizar cobranças do Inter"
                  type="button"
                >
                  Atualizar
                </button>
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestInterChargeSync, "Ultima sincronizacao: nenhuma")}
                {!hasInterAccount ? (
                  <small className="compact-muted">Cadastre a chave da API do Inter na conta para habilitar.</small>
                ) : null}
              </div>
            </div>
          </div>
        </article>
      </section>

      <section className="content-grid two-columns">
        <article className="panel compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Histórico</p>
            <h3>Livro caixa antigo</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xlsx" onChange={(event) => setHistoricalFile(event.target.files?.[0] ?? null)} />
            <div className="import-last-meta">
              {latestHistoricalImport
                ? `Última importação: ${latestHistoricalImport.filename} em ${formatDateTime(latestHistoricalImport.created_at)}`
                : "Última importação: nenhuma"}
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
            {!hasInterAccount && <div className="import-last-meta">Nenhuma conta com API Inter habilitada.</div>}
            <div className="import-last-meta">
              {latestInterStatementImport
                ? `Última sincronização: ${latestInterStatementImport.filename} em ${formatDateTime(latestInterStatementImport.created_at)}`
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
            <thead><tr><th>Data/Hora</th><th>Arquivo</th><th>Tipo</th><th>Processo</th><th>Status</th><th>Observação</th></tr></thead>
            <tbody>
              {importSummary.import_batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{formatDateTime(batch.created_at)}</td>
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

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
  onUploadBoletoC6: (file: File) => Promise<void>;
  onRunC6Settlement: () => Promise<void>;
  onSyncCustomers: () => Promise<void>;
  onSyncPurchaseInvoices: () => Promise<string | void>;
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
  onUploadBoletoC6,
  onRunC6Settlement,
  onSyncCustomers,
  onSyncPurchaseInvoices,
  onSyncInterCharges,
  onSyncInterStatement,
  onSyncReceivables,
}: Props) {
  const currentTab = tabs.find((item) => item.key === "importacoes-gerais") ?? tabs[0];
  const [historicalFile, setHistoricalFile] = useState<File | null>(null);
  const [interFile, setInterFile] = useState<File | null>(null);
  const [c6File, setC6File] = useState<File | null>(null);

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
  const latestLinxPurchaseInvoicesImport = useMemo(
    () => latestBatchFor(importSummary, "linx_purchase_payables"),
    [importSummary],
  );
  const latestInterBoletoImport = useMemo(() => latestBatchFor(importSummary, "boletos:inter"), [importSummary]);
  const latestC6BoletoImport = useMemo(() => latestBatchFor(importSummary, "boletos:c6"), [importSummary]);
  const latestInterChargeSync = useMemo(() => latestBatchFor(importSummary, "inter_charge_sync"), [importSummary]);

  async function handleUploadInterReport() {
    if (!interFile) {
      return;
    }
    await onUploadBoletoInter(interFile);
    setInterFile(null);
  }

  async function handleUploadC6Report() {
    if (!c6File) {
      return;
    }
    await onUploadBoletoC6(c6File);
    setC6File(null);
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
            <h3>Importacao rapida da cobranca</h3>
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
                <small className="compact-muted">Usa a base espelho da API para a cobranca.</small>
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
                <strong>Faturas de compra Linx API</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting}
                  onClick={() => void onSyncPurchaseInvoices()}
                  title="Atualizar faturas de compra da API Linx"
                  type="button"
                >
                  Atualizar
                </button>
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestLinxPurchaseInvoicesImport)}
                <small className="compact-muted">
                  Busca faturas de compra em aberto da API Linx e inclui somente lancamentos novos ou alterados.
                </small>
              </div>
            </div>

            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Relatorio C6</strong>
                <div className="billing-import-actions">
                  <button
                    className="secondary-button compact-action-button"
                    disabled={submitting}
                    onClick={() => void onRunC6Settlement()}
                    title="Forcar baixa automatica dos boletos C6 no Linx"
                    type="button"
                  >
                    Forcar baixa
                  </button>
                  <button
                    className="primary-button compact-action-button"
                    disabled={submitting || !c6File}
                    onClick={() => void handleUploadC6Report()}
                    title="Importar relatorio C6"
                    type="button"
                  >
                    Importar
                  </button>
                </div>
              </div>
              <input
                id="system-boletos-c6-file"
                className="hidden-file-input"
                type="file"
                accept=".csv"
                onChange={(event) => setC6File(event.target.files?.[0] ?? null)}
              />
              <div className="billing-file-picker-row">
                <label className="secondary-button compact-file-trigger" htmlFor="system-boletos-c6-file">
                  Selecionar
                </label>
                {c6File ? (
                  <span className="compact-file-name" title={c6File.name}>
                    {c6File.name}
                  </span>
                ) : null}
              </div>
              <div className="billing-import-meta">
                {renderBatchMeta(latestC6BoletoImport)}
                <small className="compact-muted">CSV usado para conferir boletos faltando, retornos do C6 e disparar a baixa no Linx.</small>
                {c6File ? (
                  <small className="compact-muted" title={c6File.name}>
                    Novo arquivo: {c6File.name}
                  </small>
                ) : null}
              </div>
            </div>

            <div className="compact-import-card billing-import-card">
              <div className="billing-import-header">
                <strong>Relatorio Inter</strong>
                <button
                  className="primary-button compact-action-button"
                  disabled={submitting || !interFile}
                  onClick={() => void handleUploadInterReport()}
                  title="Importar relatorio Inter"
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
                <small className="compact-muted">ZIP do retorno/importacao de boletos do Inter.</small>
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
                  title="Atualizar cobrancas do Inter"
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
            <p className="eyebrow">Historico</p>
            <h3>Livro caixa antigo</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xlsx" onChange={(event) => setHistoricalFile(event.target.files?.[0] ?? null)} />
            <div className="import-last-meta">
              {latestHistoricalImport
                ? `Ultima importacao: ${latestHistoricalImport.filename} em ${formatDateTime(latestHistoricalImport.created_at)}`
                : "Ultima importacao: nenhuma"}
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
                ? `Ultima sincronizacao: ${latestInterStatementImport.filename} em ${formatDateTime(latestInterStatementImport.created_at)}`
                : "Ultima sincronizacao: nenhuma"}
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
        <div className="panel-title">
          <h3>Historico de importacoes</h3>
        </div>
        <div className="table-shell">
          <table className="erp-table">
            <thead>
              <tr>
                <th>Data/Hora</th>
                <th>Arquivo</th>
                <th>Tipo</th>
                <th>Processo</th>
                <th>Status</th>
                <th>Observacao</th>
              </tr>
            </thead>
            <tbody>
              {importSummary.import_batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{formatDateTime(batch.created_at)}</td>
                  <td>{batch.filename}</td>
                  <td>{batch.source_type}</td>
                  <td>
                    {batch.records_valid}/{batch.records_total}
                  </td>
                  <td>{formatEntryStatus(batch.status)}</td>
                  <td>{batch.error_summary ?? "Processado sem observacoes."}</td>
                </tr>
              ))}
              {!importSummary.import_batches.length && (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    Nenhuma importacao registrada ainda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

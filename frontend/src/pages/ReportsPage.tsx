import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { ReportConfigModal } from "../components/ReportConfigModal";
import { PageHeader } from "../components/PageHeader";
import { formatDate, formatMoney } from "../lib/format";
import type {
  DreReport,
  DroReport,
  ImportSummary,
  ReportConfig,
  ReportDashboardCard,
  ReportTreeNode,
  ReportsOverview,
} from "../types";

type ReportTab = "dre" | "dro";

type Props = {
  reports: ReportsOverview | null;
  importSummary: ImportSummary;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: () => Promise<void>;
  onExport: (kind: "dre" | "dro", format: "pdf" | "csv" | "xls") => Promise<void>;
  onUploadSales: (file: File) => Promise<void>;
  onSyncSales: (period: { start: string; end: string }) => Promise<void>;
  onLoadConfig: (kind: "dre" | "dro") => Promise<ReportConfig>;
  onSaveConfig: (kind: "dre" | "dro", payload: { lines: ReportConfig["lines"] }) => Promise<ReportConfig>;
  embedded?: boolean;
  forcedTab?: ReportTab | null;
};

type StatementTableProps = {
  nodes: ReportTreeNode[];
  expandedKeys: Set<string>;
  onToggle: (key: string) => void;
};

function collectExpandableKeys(nodes: ReportTreeNode[]): string[] {
  return nodes.flatMap((node) => (node.children.length > 0 ? [node.key, ...collectExpandableKeys(node.children)] : []));
}

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

function ReportStatementTable({ nodes, expandedKeys, onToggle }: StatementTableProps) {
  function renderRows(items: ReportTreeNode[], depth = 0) {
    return items.flatMap((node) => {
      const isExpanded = expandedKeys.has(node.key);
      const hasChildren = node.children.length > 0;
      const valueToneClass = Number(node.amount) < 0 ? "negative" : "positive";
      const row = (
        <Fragment key={node.key}>
          <tr className={`report-row tone-${node.tone}`}>
            <td>
              <div className="report-label-cell" style={{ paddingLeft: `${depth * 18}px` }}>
                {hasChildren ? (
                  <button className="report-toggle" onClick={() => onToggle(node.key)} type="button">
                    {isExpanded ? "-" : "+"}
                  </button>
                ) : (
                  <span className="report-toggle placeholder" />
                )}
                <div className="report-label-stack">
                  <strong>{node.label}</strong>
                  {node.code && <span className="report-code">{node.code}</span>}
                </div>
              </div>
            </td>
            <td className={`report-value-cell ${valueToneClass}`}>{formatMoney(node.amount)}</td>
            <td className={`report-value-cell ${valueToneClass}`}>{node.percent === null ? "" : `${Number(node.percent).toFixed(2)}%`}</td>
          </tr>
          {hasChildren && isExpanded ? renderRows(node.children, depth + 1) : null}
        </Fragment>
      );
      return [row];
    });
  }

  return (
    <div className="table-shell">
      <table className="erp-table report-table">
        <thead>
          <tr>
            <th>Contas</th>
            <th>Valor (R$)</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>{renderRows(nodes)}</tbody>
      </table>
    </div>
  );
}

function ReportDashboardSummary({ cards }: { cards: ReportDashboardCard[] }) {
  if (!cards.length) {
    return null;
  }
  return (
    <section className="kpi-grid compact-kpis-four">
      {cards.map((card) => (
        <article className="kpi-card" key={card.key}>
          <span>{card.label}</span>
          <strong>{formatMoney(card.amount)}</strong>
        </article>
      ))}
    </section>
  );
}

export function ReportsPage({
  reports,
  importSummary,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
  onExport,
  onUploadSales,
  onSyncSales,
  onLoadConfig,
  onSaveConfig,
  embedded = false,
  forcedTab = null,
}: Props) {
  const [activeTab, setActiveTab] = useState<ReportTab>(forcedTab ?? "dre");
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [salesFile, setSalesFile] = useState<File | null>(null);
  const [configByKind, setConfigByKind] = useState<Record<ReportTab, ReportConfig | null>>({ dre: null, dro: null });
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const hasMountedAutoApplyRef = useRef(false);

  const latestSalesImport = useMemo(() => latestBatchFor(importSummary, "linx_sales"), [importSummary]);
  const latestReceivablesImport = useMemo(() => latestBatchFor(importSummary, "linx_receivables"), [importSummary]);

  useEffect(() => {
    if (forcedTab) {
      setActiveTab(forcedTab);
    }
  }, [forcedTab]);

  useEffect(() => {
    setExpandedKeys(new Set());
  }, [activeTab, reports]);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void onApplyFilters();
  }, [filters.end, filters.start]);

  function toggleNode(key: string) {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  async function openConfigModal() {
    setConfigModalOpen(true);
    if (configByKind[activeTab]) {
      return;
    }
    setConfigLoading(true);
    try {
      const config = await onLoadConfig(activeTab);
      setConfigByKind((current) => ({ ...current, [activeTab]: config }));
    } finally {
      setConfigLoading(false);
    }
  }

  async function handleSaveConfig(payload: { lines: ReportConfig["lines"] }) {
    setConfigSaving(true);
    try {
      const saved = await onSaveConfig(activeTab, payload);
      setConfigByKind((current) => ({ ...current, [activeTab]: saved }));
      return saved;
    } finally {
      setConfigSaving(false);
    }
  }

  const currentReport = activeTab === "dre" ? reports?.dre : reports?.dro;
  const currentNodes = currentReport?.statement ?? [];
  const allExpandableKeys = useMemo(() => collectExpandableKeys(currentNodes), [currentNodes]);
  const allExpanded = allExpandableKeys.length > 0 && allExpandableKeys.every((key: string) => expandedKeys.has(key));

  function toggleAllNodes() {
    setExpandedKeys(() => (allExpanded ? new Set() : new Set(allExpandableKeys)));
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Relatorios"
          title="DRE e DRO"
          description="Demonstrativos separados, com filtros obrigatórios por período e leitura expansível por nível de detalhe."
          actions={
            <div className="toolbar">
              <label>Inicio<input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} /></label>
              <label>Fim<input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} /></label>
              <button className="secondary-button" disabled={loading} onClick={() => void onExport(activeTab, "pdf")} type="button">{activeTab.toUpperCase()} PDF</button>
              <button className="secondary-button" disabled={loading} onClick={() => void onExport(activeTab, "xls")} type="button">{activeTab.toUpperCase()} XLS</button>
              <button className="ghost-button" disabled={loading} onClick={() => void onExport(activeTab, "csv")} type="button">{activeTab.toUpperCase()} CSV</button>
            </div>
          }
        />
      )}

      {embedded && (
        <section className="section-toolbar-panel">
          <div className="section-toolbar-content compact-filter-layout">
            <label>Inicio<input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} /></label>
            <label>Fim<input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} /></label>
            <button className="secondary-button" disabled={loading} onClick={() => void onExport(activeTab, "pdf")} type="button">{activeTab.toUpperCase()} PDF</button>
            <button className="secondary-button" disabled={loading} onClick={() => void onExport(activeTab, "xls")} type="button">{activeTab.toUpperCase()} XLS</button>
            <button className="ghost-button" disabled={loading} onClick={() => void onExport(activeTab, "csv")} type="button">{activeTab.toUpperCase()} CSV</button>
          </div>
        </section>
      )}

      <section className="content-grid two-columns">
        <article className="panel compact-import-panel">
          <div className="panel-heading compact-panel-heading">
            <p className="eyebrow">Linx</p>
            <h3>Importar faturamento</h3>
          </div>
          <div className="compact-upload-box">
            <input type="file" accept=".xls,.html" onChange={(event) => setSalesFile(event.target.files?.[0] ?? null)} />
            <div className="import-last-meta">
              {latestSalesImport ? `Última importação: ${latestSalesImport.filename} em ${formatDate(latestSalesImport.created_at)}` : "Última importação: nenhuma"}
            </div>
            <button className="primary-button compact-action-button" disabled={loading || !salesFile} onClick={() => salesFile && void onUploadSales(salesFile)} type="button">
              Importar
            </button>
            <button className="secondary-button compact-action-button" disabled={loading} onClick={() => void onSyncSales(filters)} type="button">
              Sincronizar Linx
            </button>
          </div>
        </article>

        <article className="panel">
          <div className="panel-title"><h3>Bases utilizadas</h3></div>
          <div className="summary-list">
            <div className="summary-row"><span>Faturamento Linx</span><strong>{latestSalesImport ? formatDate(latestSalesImport.created_at) : "Sem carga"}</strong></div>
            <div className="summary-row"><span>Faturas a receber</span><strong>{latestReceivablesImport ? formatDate(latestReceivablesImport.created_at) : "Sem carga"}</strong></div>
            <div className="summary-row"><span>Entrada de recebíveis</span><strong>Cobrança</strong></div>
          </div>
        </article>
      </section>

      <section className="panel">
        {!forcedTab && (
          <div className="report-tabs">
            <button className={activeTab === "dre" ? "report-tab active" : "report-tab"} onClick={() => setActiveTab("dre")} type="button">DRE</button>
            <button className={activeTab === "dro" ? "report-tab active" : "report-tab"} onClick={() => setActiveTab("dro")} type="button">DRO</button>
          </div>
        )}

        {currentReport ? (
          <div className="page-layout">
            <div className="report-period-header">
              <div>
                <p className="section-label">{activeTab === "dre" ? "Demonstração do Resultado do Exercício" : "Demonstrativo de Resultados Operacionais"}</p>
                <h3>{currentReport.period_label}</h3>
              </div>
              <div className="report-period-actions">
                <button className="secondary-button icon-button report-config-button" onClick={() => void openConfigModal()} title={`Configurar ${activeTab.toUpperCase()}`} type="button">
                  <span className="button-icon">⚙</span>
                </button>
                <button className="secondary-button" disabled={allExpandableKeys.length === 0} onClick={toggleAllNodes} type="button">
                  {allExpanded ? "Fechar todos os lançamentos" : "Abrir todos os lançamentos"}
                </button>
              </div>
            </div>

            <ReportDashboardSummary cards={currentReport.dashboard_cards} />
            <ReportStatementTable expandedKeys={expandedKeys} nodes={currentNodes} onToggle={toggleNode} />
          </div>
        ) : (
          <div className="empty-panel">
            <p className="empty-state">Sem dados para o período selecionado.</p>
          </div>
        )}
      </section>

      {configModalOpen && (
        <ReportConfigModal
          config={configByKind[activeTab]}
          kind={activeTab}
          loading={configLoading}
          onClose={() => setConfigModalOpen(false)}
          onSave={handleSaveConfig}
          saving={configSaving}
        />
      )}
    </div>
  );
}

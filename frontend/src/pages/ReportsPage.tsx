import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { ReportConfigModal } from "../components/ReportConfigModal";
import { PageHeader } from "../components/PageHeader";
import { formatDate, formatMoneyNumber } from "../lib/format";
import type {
  ImportSummary,
  ReportConfig,
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
  onSyncMovements: () => Promise<void>;
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

function formatRangeLabel(start: string, end: string) {
  if (!start && !end) {
    return "Selecionar periodo";
  }
  if (start && end) {
    return `${formatDate(start)} - ${formatDate(end)}`;
  }
  return start ? `${formatDate(start)} - ...` : `... - ${formatDate(end)}`;
}

function CalendarRangeIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M4 1.75a.75.75 0 0 1 1.5 0V3h5V1.75a.75.75 0 0 1 1.5 0V3h.75A2.25 2.25 0 0 1 15 5.25v7.5A2.25 2.25 0 0 1 12.75 15h-9.5A2.25 2.25 0 0 1 1 12.75v-7.5A2.25 2.25 0 0 1 3.25 3H4V1.75ZM2.5 6.5v6.25c0 .414.336.75.75.75h9.5a.75.75 0 0 0 .75-.75V6.5h-11Zm11-1.5v-.75a.75.75 0 0 0-.75-.75h-.75v.5a.75.75 0 0 1-1.5 0v-.5h-5v.5a.75.75 0 0 1-1.5 0v-.5h-.75a.75.75 0 0 0-.75.75V5h11Z" />
    </svg>
  );
}

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <path
        d="M6.37 1.88c.22-.83 1.4-.83 1.62 0l.2.76a1.5 1.5 0 0 0 1.09 1.06l.77.2c.84.21.84 1.4 0 1.61l-.77.2a1.5 1.5 0 0 0-1.09 1.07l-.2.76c-.22.83-1.4.83-1.62 0l-.2-.76A1.5 1.5 0 0 0 5.08 5.7l-.76-.2c-.84-.21-.84-1.4 0-1.61l.76-.2a1.5 1.5 0 0 0 1.1-1.06l.19-.76Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
      <path
        d="M10.58 8.74c.17-.63 1.07-.63 1.24 0l.14.5c.09.34.36.6.7.7l.5.14c.64.17.64 1.07 0 1.24l-.5.14c-.34.1-.61.36-.7.7l-.14.5c-.17.64-1.07.64-1.24 0l-.14-.5a.97.97 0 0 0-.7-.7l-.5-.14c-.64-.17-.64-1.07 0-1.24l.5-.14c.34-.1.61-.36.7-.7l.14-.5Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
    </svg>
  );
}

function ExpandRowsIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <path d="M3 4h10M3 8h10M3 12h10" stroke="currentColor" strokeLinecap="round" strokeWidth="1.3" />
      {expanded ? (
        <path d="m6 6 2 2 2-2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.3" />
      ) : (
        <path d="m6 10 2-2 2 2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.3" />
      )}
    </svg>
  );
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
            <td className={`report-value-cell ${valueToneClass}`}>{formatMoneyNumber(node.amount)}</td>
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
            <th>Valor</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>{renderRows(nodes)}</tbody>
      </table>
    </div>
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
  onSyncMovements,
  onLoadConfig,
  onSaveConfig,
  embedded = false,
  forcedTab = null,
}: Props) {
  const [periodDraft, setPeriodDraft] = useState(() => ({ start: filters.start, end: filters.end }));
  const [activeTab, setActiveTab] = useState<ReportTab>(forcedTab ?? "dre");
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [configByKind, setConfigByKind] = useState<Record<ReportTab, ReportConfig | null>>({ dre: null, dro: null });
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);
  const hasMountedAutoApplyRef = useRef(false);
  const latestFiltersRef = useRef(filters);
  const periodCommitTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    latestFiltersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    setPeriodDraft({ start: filters.start, end: filters.end });
  }, [filters.end, filters.start]);

  useEffect(() => () => {
    if (periodCommitTimerRef.current) {
      clearTimeout(periodCommitTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (forcedTab) {
      setActiveTab(forcedTab);
    }
  }, [forcedTab]);

  useEffect(() => {
    setExpandedKeys(new Set());
  }, [activeTab, reports]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
      if (showPresetMenu && presetMenuRef.current && !presetMenuRef.current.contains(target)) {
        setShowPresetMenu(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showPeriodPopover, showPresetMenu]);

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

  function commitDateRange(start: string, end: string) {
    onChangeFilters({ ...latestFiltersRef.current, start, end });
  }

  function scheduleDateRangeCommit(start: string, end: string) {
    if (periodCommitTimerRef.current) {
      clearTimeout(periodCommitTimerRef.current);
    }
    if ((start && start.length < 10) || (end && end.length < 10)) {
      return;
    }
    periodCommitTimerRef.current = window.setTimeout(() => {
      commitDateRange(start, end);
    }, 450);
  }

  function setDateRange(start: string, end: string, immediate = false) {
    setPeriodDraft({ start, end });
    if (immediate) {
      if (periodCommitTimerRef.current) {
        clearTimeout(periodCommitTimerRef.current);
      }
      commitDateRange(start, end);
      return;
    }
    scheduleDateRangeCommit(start, end);
  }

  function applyPresetRange(kind: "today" | "current_month" | "previous_month" | "current_year") {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const formatValue = (value: Date) => value.toISOString().slice(0, 10);

    if (kind === "today") {
      const current = formatValue(today);
      setDateRange(current, current, true);
      return;
    }

    if (kind === "current_month") {
      setDateRange(formatValue(new Date(year, month, 1)), formatValue(new Date(year, month + 1, 0)), true);
      return;
    }

    if (kind === "previous_month") {
      setDateRange(formatValue(new Date(year, month - 1, 1)), formatValue(new Date(year, month, 0)), true);
      return;
    }

    setDateRange(formatValue(new Date(year, 0, 1)), formatValue(new Date(year, 11, 31)), true);
  }

  const currentReport = activeTab === "dre" ? reports?.dre : reports?.dro;
  const currentNodes = currentReport?.statement ?? [];
  const allExpandableKeys = useMemo(() => collectExpandableKeys(currentNodes), [currentNodes]);
  const allExpanded = allExpandableKeys.length > 0 && allExpandableKeys.every((key: string) => expandedKeys.has(key));

  function toggleAllNodes() {
    setExpandedKeys(() => (allExpanded ? new Set() : new Set(allExpandableKeys)));
  }

  const reportFiltersContent = (
    <div className="reports-top-toolbar">
      <div className="reports-top-toolbar-main">
        <div className="entries-period-group" ref={periodPopoverRef}>
          <button
            aria-expanded={showPeriodPopover}
            aria-label="Selecionar periodo"
            className={`entries-period-trigger ${showPeriodPopover ? "is-active" : ""}`}
            disabled={loading}
            onClick={() => {
              setShowPresetMenu(false);
              setShowPeriodPopover((current) => !current);
            }}
            type="button"
          >
            <CalendarRangeIcon />
            <span>{formatRangeLabel(periodDraft.start, periodDraft.end)}</span>
          </button>
          {showPeriodPopover && (
            <div className="entries-floating-panel entries-period-popover">
              <div className="entries-period-fields">
                <label>
                  Inicio
                  <input disabled={loading} type="date" value={periodDraft.start} onChange={(event) => setDateRange(event.target.value, periodDraft.end)} />
                </label>
                <label>
                  Fim
                  <input disabled={loading} type="date" value={periodDraft.end} onChange={(event) => setDateRange(periodDraft.start, event.target.value)} />
                </label>
              </div>
              <div className="entries-period-footer">
                <button
                  className="secondary-button compact-button"
                  onClick={() => {
                    setDateRange("", "", true);
                    setShowPeriodPopover(false);
                  }}
                  type="button"
                >
                  Limpar
                </button>
                <button className="primary-button compact-button" onClick={() => {
                  setDateRange(periodDraft.start, periodDraft.end, true);
                  setShowPeriodPopover(false);
                }} type="button">
                  Concluir
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="entries-toolbar-icon-wrap" ref={presetMenuRef}>
          <button
            aria-expanded={showPresetMenu}
            aria-label="Periodos pre-definidos"
            className={`entries-toolbar-icon ${showPresetMenu ? "is-active" : ""}`}
            disabled={loading}
            onClick={() => {
              setShowPeriodPopover(false);
              setShowPresetMenu((current) => !current);
            }}
            title="Periodos pre-definidos"
            type="button"
          >
            <FilterFunnelIcon />
          </button>
          {showPresetMenu && (
            <div className="entries-floating-panel entries-icon-menu">
              <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("today"); setShowPresetMenu(false); }} type="button">Hoje</button>
              <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("current_month"); setShowPresetMenu(false); }} type="button">Mes atual</button>
              <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("previous_month"); setShowPresetMenu(false); }} type="button">Mes anterior</button>
              <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("current_year"); setShowPresetMenu(false); }} type="button">Ano atual</button>
            </div>
          )}
        </div>
      </div>

      <div className="reports-top-toolbar-actions">
        <button
          aria-label={`Configurar ${activeTab.toUpperCase()}`}
          className="entries-toolbar-icon"
          disabled={loading}
          onClick={() => void openConfigModal()}
          title={`Configurar ${activeTab.toUpperCase()}`}
          type="button"
        >
          <SettingsIcon />
        </button>
        <button
          aria-label={allExpanded ? "Fechar todos os lancamentos" : "Abrir todos os lancamentos"}
          className="entries-toolbar-icon"
          disabled={allExpandableKeys.length === 0}
          onClick={toggleAllNodes}
          title={allExpanded ? "Fechar todos os lancamentos" : "Abrir todos os lancamentos"}
          type="button"
        >
          <ExpandRowsIcon expanded={allExpanded} />
        </button>
      </div>
    </div>
  );

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Relatorios"
          title="DRE e DRO"
          description="Demonstrativos separados, com filtros obrigatorios por periodo e leitura expansivel por nivel de detalhe."
        />
      )}

      <section className={`section-toolbar-panel reports-filter-panel ${embedded ? "reconciliation-filter-panel" : ""}`}>
        {reportFiltersContent}
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
            <ReportStatementTable expandedKeys={expandedKeys} nodes={currentNodes} onToggle={toggleNode} />
          </div>
        ) : (
          <div className="empty-panel">
            <p className="empty-state">Sem dados para o periodo selecionado.</p>
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

import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { RefreshIcon } from "../components/RefreshIcon";
import { formatDate, formatMoneyNumber } from "../lib/format";
import type { Account, CashflowOverview } from "../types";

type Props = {
  cashflow: CashflowOverview | null;
  accounts: Account[];
  filters: CashflowFilters;
  loading: boolean;
  onChangeFilters: (filters: CashflowFilters) => void;
  onApplyFilters: (filters?: CashflowFilters) => Promise<void>;
  onRefreshData: () => Promise<void>;
  embedded?: boolean;
};

type ViewMode = "daily" | "weekly" | "monthly";
type CashflowFilters = {
  start: string;
  end: string;
  account_id: string;
  include_purchase_planning: boolean;
  include_crediario_receivables: boolean;
};

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

function ChevronDownIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="14"
      viewBox="0 0 16 16"
      width="14"
      style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.16s ease" }}
    >
      <path d="m4 6 4 4 4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function formatProjectionReference(reference: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(reference)) {
    return formatDate(reference);
  }
  if (/^\d{4}-\d{2}$/.test(reference)) {
    const [year, month] = reference.split("-");
    return `01/${month}/${year}`;
  }
  return reference;
}

export function CashflowPage({
  cashflow,
  accounts,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
  onRefreshData,
  embedded = false,
}: Props) {
  const [filterDraft, setFilterDraft] = useState<CashflowFilters>(filters);
  const [viewMode, setViewMode] = useState<ViewMode>("daily");
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);
  const [showBalancePopover, setShowBalancePopover] = useState(false);
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);
  const balancePopoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setFilterDraft(filters);
  }, [filters]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
      if (showPresetMenu && presetMenuRef.current && !presetMenuRef.current.contains(target)) {
        setShowPresetMenu(false);
      }
      if (showBalancePopover && balancePopoverRef.current && !balancePopoverRef.current.contains(target)) {
        setShowBalancePopover(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showBalancePopover, showPeriodPopover, showPresetMenu]);

  const projection = useMemo(() => {
    if (viewMode === "weekly") {
      return cashflow?.weekly_projection ?? [];
    }
    if (viewMode === "monthly") {
      return cashflow?.monthly_projection ?? [];
    }
    return cashflow?.daily_projection ?? [];
  }, [cashflow, viewMode]);

  function setDateRange(start: string, end: string) {
    setFilterDraft((current) => ({ ...current, start, end }));
  }

  async function applyDraftFilters() {
    onChangeFilters(filterDraft);
    await onApplyFilters(filterDraft);
  }

  function handleImmediateFilterChange(updater: (current: CashflowFilters) => CashflowFilters) {
    const nextFilters = updater(filters);
    setFilterDraft(nextFilters);
    onChangeFilters(nextFilters);
    void onApplyFilters(nextFilters);
  }

  function applyPresetRange(kind: "today" | "current_month" | "previous_month" | "current_year") {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const formatValue = (value: Date) => value.toISOString().slice(0, 10);

    if (kind === "today") {
      const current = formatValue(today);
      setDateRange(current, current);
      return;
    }

    if (kind === "current_month") {
      setDateRange(formatValue(new Date(year, month, 1)), formatValue(new Date(year, month + 1, 0)));
      return;
    }

    if (kind === "previous_month") {
      setDateRange(formatValue(new Date(year, month - 1, 1)), formatValue(new Date(year, month, 0)));
      return;
    }

    setDateRange(formatValue(new Date(year, 0, 1)), formatValue(new Date(year, 11, 31)));
  }

  const cashflowFiltersContent = (
    <div className="cashflow-top-toolbar">
      <div className="cashflow-top-select-field">
        <select
          aria-label="Conta do fluxo de caixa"
          className="reconciliation-top-select"
          disabled={loading}
          value={filterDraft.account_id}
          onChange={(event) => handleImmediateFilterChange((current) => ({ ...current, account_id: event.target.value }))}
        >
          <option value="">Todas as contas</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} {account.exclude_from_balance ? "(ignorado)" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="entries-period-group cashflow-period-group" ref={periodPopoverRef}>
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
          <span>{formatRangeLabel(filterDraft.start, filterDraft.end)}</span>
        </button>
        {showPeriodPopover && (
          <div className="entries-floating-panel entries-period-popover">
            <div className="entries-period-fields">
              <label>
                Inicio
                <input disabled={loading} type="date" value={filterDraft.start} onChange={(event) => setDateRange(event.target.value, filterDraft.end)} />
              </label>
              <label>
                Fim
                <input disabled={loading} type="date" value={filterDraft.end} onChange={(event) => setDateRange(filterDraft.start, event.target.value)} />
              </label>
            </div>
            <div className="entries-period-footer">
              <button
                className="secondary-button compact-button"
                onClick={() => {
                  setDateRange("", "");
                  setShowPeriodPopover(false);
                }}
                type="button"
                >
                  Limpar
                </button>
              <button className="primary-button compact-button" onClick={() => {
                setShowPeriodPopover(false);
                void applyDraftFilters();
              }} type="button">
                Aplicar
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

      <div className="entries-toolbar-icon-wrap">
        <button
          aria-label="Atualizar dados analiticos"
          className={`entries-toolbar-icon ${loading ? "is-loading" : ""}`}
          disabled={loading}
          onClick={() => void onRefreshData()}
          title="Atualizar dados analiticos"
          type="button"
        >
          <RefreshIcon />
          <span className="entries-toolbar-icon-label">Atualizar</span>
        </button>
      </div>

      <div className="cashflow-toggle-group">
        <label className="reconciliation-subtle-toggle">
          <input
            checked={filterDraft.include_purchase_planning}
            disabled={loading}
            onChange={(event) =>
              handleImmediateFilterChange((current) => ({ ...current, include_purchase_planning: event.target.checked }))
            }
            type="checkbox"
          />
          <span>Incluir compras planejadas</span>
        </label>
        <label className="reconciliation-subtle-toggle">
          <input
            checked={filterDraft.include_crediario_receivables}
            disabled={loading}
            onChange={(event) =>
              handleImmediateFilterChange((current) => ({ ...current, include_crediario_receivables: event.target.checked }))
            }
            type="checkbox"
          />
          <span>Incluir receitas crediario</span>
        </label>
      </div>

      <div className="cashflow-inline-meta">
        <div className="reconciliation-balance-wrap" ref={balancePopoverRef}>
          <button
            aria-expanded={showBalancePopover}
            className={`reconciliation-balance-trigger ${showBalancePopover ? "is-active" : ""}`}
            onClick={() => setShowBalancePopover((current) => !current)}
            type="button"
          >
            <span>Saldo por conta</span>
            <strong>{formatMoneyNumber(cashflow?.current_balance)}</strong>
            <ChevronDownIcon expanded={showBalancePopover} />
          </button>
          {showBalancePopover && (
            <div className="reconciliation-balance-popover">
              {(cashflow?.account_balances ?? []).map((item) => (
                <div className={`reconciliation-balance-row ${item.exclude_from_balance ? "is-ignored-account" : ""}`} key={item.account_id}>
                  <span title={`${item.account_name} | ${item.account_type}`}>
                    {item.account_name}
                    {item.exclude_from_balance && <span className="ignored-badge"> (Ignorado)</span>}
                  </span>
                  <strong>{formatMoneyNumber(item.current_balance)}</strong>
                </div>
              ))}
              {!cashflow?.account_balances.length && (
                <div className="reconciliation-balance-empty">Nenhum saldo disponivel.</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Financeiro"
          title="Fluxo de caixa"
          description="Leitura do caixa previsto e realizado por conta, com foco em saldo final e risco de aperto."
        />
      )}

      <section className={`section-toolbar-panel cashflow-filter-panel ${embedded ? "reconciliation-filter-panel" : ""}`}>
        {cashflowFiltersContent}
      </section>

      <section className="kpi-grid cashflow-kpi-grid">
        <article className="kpi-card cashflow-kpi-card"><span>Saldo atual</span><strong>{formatMoneyNumber(cashflow?.current_balance)}</strong></article>
        <article className="kpi-card cashflow-kpi-card"><span>Entradas previstas</span><strong>{formatMoneyNumber(cashflow?.projected_inflows)}</strong></article>
        <article className="kpi-card cashflow-kpi-card"><span>Saidas previstas</span><strong>{formatMoneyNumber(cashflow?.projected_outflows)}</strong></article>
        <article className="kpi-card cashflow-kpi-card"><span>Compras planejadas</span><strong>{formatMoneyNumber(cashflow?.planned_purchase_outflows)}</strong></article>
        <article className="kpi-card cashflow-kpi-card emphasis"><span>Saldo projetado</span><strong>{formatMoneyNumber(cashflow?.projected_ending_balance)}</strong></article>
      </section>

      {!!cashflow?.alerts.length && (
        <section className="panel warning-panel">
          <div className="panel-title"><h3>Alertas de caixa</h3></div>
          <ul className="plain-list">
            {cashflow.alerts.map((alert) => <li key={alert}>{alert}</li>)}
          </ul>
        </section>
      )}

      <section className="panel cashflow-projection-panel">
        <div className="panel-title">
          <h3>Projecao por horizonte</h3>
          <div className="report-tabs compact">
            <button className={viewMode === "daily" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("daily")} type="button">Diario</button>
            <button className={viewMode === "weekly" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("weekly")} type="button">Semanal</button>
            <button className={viewMode === "monthly" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("monthly")} type="button">Mensal</button>
          </div>
        </div>
        <div className="table-shell cashflow-projection-shell">
          <table className="erp-table cashflow-projection-table">
            <thead><tr><th>Periodo</th><th>Saldo inicial</th><th>Crediario</th><th>Cartao</th><th>Despesas lancadas</th><th>Previsao de compras</th><th>Fechamento</th></tr></thead>
            <tbody>
              {projection.map((point) => (
                <tr key={point.reference}>
                  <td>{formatProjectionReference(point.reference)}</td>
                  <td>{formatMoneyNumber(point.opening_balance)}</td>
                  <td>{formatMoneyNumber(point.crediario_inflows)}</td>
                  <td>{formatMoneyNumber(point.card_inflows)}</td>
                  <td>{formatMoneyNumber(point.launched_outflows)}</td>
                  <td>{formatMoneyNumber(point.planned_purchase_outflows)}</td>
                  <td>{formatMoneyNumber(point.closing_balance)}</td>
                </tr>
              ))}
              {!projection.length && <tr><td colSpan={7} className="empty-cell">Sem pontos de projecao para o periodo informado.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

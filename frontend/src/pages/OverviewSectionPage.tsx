import { useEffect, useRef, useState } from "react";

import { BarChart } from "../components/BarChart";
import { RefreshIcon } from "../components/RefreshIcon";
import { RevenueComparisonChart } from "../components/RevenueComparisonChart";
import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
  onRefreshData: () => Promise<void>;
};

function toInput(value: Date) {
  return value.toISOString().slice(0, 10);
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

export function OverviewSectionPage({
  tabs,
  dashboard,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
  onRefreshData,
}: Props) {
  const currentTab = tabs[0];
  const hasMountedAutoApplyRef = useRef(false);
  const applyFiltersRef = useRef(onApplyFilters);
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);
  const accountBalances = dashboard?.account_balances ?? [];
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);

  useEffect(() => {
    applyFiltersRef.current = onApplyFilters;
  }, [onApplyFilters]);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void applyFiltersRef.current();
  }, [filters.end, filters.start]);

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

  function setDateRange(start: string, end: string) {
    onChangeFilters({ start, end });
  }

  async function applyQuickRange(kind: "month" | "previous" | "year") {
    const now = new Date();
    let nextFilters = filters;

    if (kind === "month") {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), now.getMonth(), 1)),
        end: toInput(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
      };
    } else if (kind === "previous") {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
        end: toInput(new Date(now.getFullYear(), now.getMonth(), 0)),
      };
    } else {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), 0, 1)),
        end: toInput(new Date(now.getFullYear(), 11, 31)),
      };
    }

    onChangeFilters(nextFilters);
  }

  return (
    <SectionChrome
      sectionLabel="Visão Geral"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel entries-top-panel overview-top-panel">
        <div className="entries-toolbar-bar overview-toolbar-bar">
          <div className="entries-period-group" ref={periodPopoverRef}>
            <button
              aria-expanded={showPeriodPopover}
              aria-label="Selecionar período"
              className={`entries-period-trigger ${showPeriodPopover ? "is-active" : ""}`}
              disabled={loading}
              onClick={() => {
                setShowPresetMenu(false);
                setShowPeriodPopover((current) => !current);
              }}
              type="button"
            >
              <CalendarRangeIcon />
              <span>{formatRangeLabel(filters.start, filters.end)}</span>
            </button>
            {showPeriodPopover && (
              <div className="entries-floating-panel entries-period-popover">
                <div className="entries-period-fields">
                  <label>
                    Início
                    <input
                      disabled={loading}
                      type="date"
                      value={filters.start}
                      onChange={(event) => setDateRange(event.target.value, filters.end)}
                    />
                  </label>
                  <label>
                    Fim
                    <input
                      disabled={loading}
                      type="date"
                      value={filters.end}
                      onChange={(event) => setDateRange(filters.start, event.target.value)}
                    />
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
                  <button
                    className="primary-button compact-button"
                    onClick={() => setShowPeriodPopover(false)}
                    type="button"
                  >
                    Concluir
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="entries-toolbar-icon-wrap" ref={presetMenuRef}>
            <button
              aria-expanded={showPresetMenu}
              aria-label="Filtros pré-definidos de data"
              className={`entries-toolbar-icon ${showPresetMenu ? "is-active" : ""}`}
              disabled={loading}
              onClick={() => {
                setShowPeriodPopover(false);
                setShowPresetMenu((current) => !current);
              }}
              title="Períodos pré-definidos"
              type="button"
            >
              <FilterFunnelIcon />
              <span className="entries-toolbar-icon-label">Atalhos</span>
            </button>
            {showPresetMenu && (
              <div className="entries-floating-panel entries-icon-menu">
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("month");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês atual
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("previous");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês anterior
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("year");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Ano atual
                </button>
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
        </div>

        <div className="overview-balance-strip" aria-label="Saldos por conta">
          {accountBalances.length ? (
            accountBalances.map((account) => (
              <article
                className={`overview-balance-chip${account.exclude_from_balance ? " is-ignored-account" : ""}`}
                key={account.account_id}
              >
                <span title={account.account_name}>{account.account_name}</span>
                <strong className="tabular-nums">{formatMoney(account.current_balance)}</strong>
              </article>
            ))
          ) : (
            <div className="overview-balance-empty">Nenhum saldo por conta disponivel.</div>
          )}
        </div>
      </section>
      
      <section className="kpi-grid compact-kpis overview-top-kpis">
        <article className="kpi-card overview-kpi-card">
          <div className="kpi-card-icon">
            <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
              <path d="M22 12A10 10 0 0 0 12 2v10z" />
              <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
            </svg>
          </div>
          <span>Saldo atual</span>
          <strong className="tabular-nums">{formatMoney(dashboard?.kpis?.current_balance ?? 0)}</strong>
        </article>
        <article className="kpi-card overview-kpi-card">
          <div className="kpi-card-icon">
            <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
              <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
              <line x1="4" x2="4" y1="22" y2="15" />
            </svg>
          </div>
          <span>Saldo projetado</span>
          <strong className="tabular-nums">{formatMoney(dashboard?.kpis?.projected_balance ?? 0)}</strong>
        </article>
        <article className="kpi-card overview-kpi-card">
          <div className="kpi-card-icon">
            <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" x2="12" y1="8" y2="12" />
              <line x1="12" x2="12.01" y1="16" y2="16" />
            </svg>
          </div>
          <span>Conciliações pendentes</span>
          <strong className="tabular-nums">{dashboard?.kpis?.pending_reconciliations ?? 0}</strong>
        </article>
      </section>

      <section className="content-grid two-columns overview-grid">
        <div className="overview-dre-column">
          <BarChart title="DRE resumido" data={dashboard?.dre_chart ?? []} tone="success" />
        </div>
        <div className="overview-side-column">
          <RevenueComparisonChart
            title="Comparacao de Ano x Ano em Vendas"
            comparison={
              dashboard?.revenue_comparison ?? {
                current_year: new Date().getFullYear(),
                previous_year: new Date().getFullYear() - 1,
                points: [],
              }
            }
          />
        </div>
      </section>
    </SectionChrome>
  );
}

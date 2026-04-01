import { useEffect, useRef } from "react";

import { BarChart } from "../components/BarChart";
import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
};

function toInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

export function OverviewSectionPage({
  tabs,
  dashboard,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
}: Props) {
  const currentTab = tabs[0];
  const hasMountedAutoApplyRef = useRef(false);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void onApplyFilters();
  }, [filters.end, filters.start]);

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
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content">
          <div className="quick-chip-row">
            <button className="ghost-button compact" onClick={() => void applyQuickRange("month")} type="button">
              Mes atual
            </button>
            <button className="ghost-button compact" onClick={() => void applyQuickRange("previous")} type="button">
              Mes anterior
            </button>
            <button className="ghost-button compact" onClick={() => void applyQuickRange("year")} type="button">
              Ano atual
            </button>
          </div>
          <div className="toolbar-date-range">
            <label>
              Inicio
              <input
                type="date"
                value={filters.start}
                onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })}
              />
            </label>
            <label>
              Fim
              <input
                type="date"
                value={filters.end}
                onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })}
              />
            </label>
          </div>
        </div>
      </section>

      <section className="kpi-grid dashboard-kpis compact-kpis-four">
        {(dashboard?.dre_cards ?? []).map((item) => (
          <article className="kpi-card" key={item.label}>
            <span>{item.label}</span>
            <strong>{formatMoney(item.value)}</strong>
          </article>
        ))}
        <article className="kpi-card"><span>Saldo atual</span><strong>{formatMoney(dashboard?.kpis.current_balance)}</strong></article>
        <article className="kpi-card"><span>Saldo projetado</span><strong>{formatMoney(dashboard?.kpis.projected_balance)}</strong></article>
        <article className="kpi-card"><span>Conciliacoes pendentes</span><strong>{dashboard?.kpis.pending_reconciliations ?? 0}</strong></article>
      </section>

      <section className="content-grid two-columns">
        <BarChart title="DRE resumido" data={dashboard?.dre_chart ?? []} tone="success" />
        <article className="panel">
          <div className="panel-title"><h3>Saldos por conta</h3></div>
          <div className="table-shell">
            <table className="erp-table overview-balance-table">
              <thead><tr><th>Conta</th><th>Saldo atual</th></tr></thead>
              <tbody>
                {(dashboard?.account_balances ?? []).map((account) => (
                  <tr key={account.account_id}>
                    <td>{account.account_name}</td>
                    <td className="numeric-cell">{formatMoney(account.current_balance)}</td>
                  </tr>
                ))}
                {!dashboard?.account_balances.length && (
                  <tr><td className="empty-cell" colSpan={2}>Nenhum saldo por conta disponivel.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </SectionChrome>
  );
}

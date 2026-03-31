import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { formatMoney } from "../lib/format";
import type { Account, CashflowOverview } from "../types";

type Props = {
  cashflow: CashflowOverview | null;
  accounts: Account[];
  filters: {
    start: string;
    end: string;
    account_id: string;
    include_purchase_planning: boolean;
    include_crediario_receivables: boolean;
  };
  loading: boolean;
  onChangeFilters: (filters: {
    start: string;
    end: string;
    account_id: string;
    include_purchase_planning: boolean;
    include_crediario_receivables: boolean;
  }) => void;
  onApplyFilters: () => Promise<void>;
  embedded?: boolean;
};

type ViewMode = "daily" | "weekly" | "monthly";

export function CashflowPage({ cashflow, accounts, filters, loading, onChangeFilters, onApplyFilters, embedded = false }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("daily");
  const hasMountedAutoApplyRef = useRef(false);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void onApplyFilters();
  }, [filters.account_id, filters.end, filters.include_crediario_receivables, filters.include_purchase_planning, filters.start]);

  const projection = useMemo(() => {
    if (viewMode === "weekly") {
      return cashflow?.weekly_projection ?? [];
    }
    if (viewMode === "monthly") {
      return cashflow?.monthly_projection ?? [];
    }
    return cashflow?.daily_projection ?? [];
  }, [cashflow, viewMode]);

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Financeiro"
          title="Fluxo de caixa"
          description="Leitura do caixa previsto e realizado por conta, com foco em saldo final e risco de aperto."
          actions={
            <div className="toolbar">
              <label>Inicio<input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} /></label>
              <label>Fim<input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} /></label>
              <label>
                Conta
                <select value={filters.account_id} onChange={(event) => onChangeFilters({ ...filters, account_id: event.target.value })}>
                  <option value="">Todas</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <label className="checkbox-line compact-inline">
                <input
                  type="checkbox"
                  checked={filters.include_purchase_planning}
                  onChange={(event) => onChangeFilters({ ...filters, include_purchase_planning: event.target.checked })}
                />
                Incluir compras planejadas
              </label>
              <label className="checkbox-line compact-inline">
                <input
                  type="checkbox"
                  checked={filters.include_crediario_receivables}
                  onChange={(event) => onChangeFilters({ ...filters, include_crediario_receivables: event.target.checked })}
                />
                Incluir receitas crediário
              </label>
            </div>
          }
        />
      )}

      {embedded && (
        <section className="section-toolbar-panel">
          <div className="section-toolbar-content compact-filter-layout">
            <label>Inicio<input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} /></label>
            <label>Fim<input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} /></label>
            <label>
              Conta
              <select value={filters.account_id} onChange={(event) => onChangeFilters({ ...filters, account_id: event.target.value })}>
                <option value="">Todas</option>
                {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
              </select>
            </label>
            <label className="checkbox-line compact-inline compact-checkbox-chip">
              <input
                type="checkbox"
                checked={filters.include_purchase_planning}
                onChange={(event) => onChangeFilters({ ...filters, include_purchase_planning: event.target.checked })}
              />
              Incluir compras planejadas
            </label>
            <label className="checkbox-line compact-inline compact-checkbox-chip">
              <input
                type="checkbox"
                checked={filters.include_crediario_receivables}
                onChange={(event) => onChangeFilters({ ...filters, include_crediario_receivables: event.target.checked })}
              />
              Incluir receitas crediário
            </label>
          </div>
        </section>
      )}

      <section className="kpi-grid">
        <article className="kpi-card"><span>Saldo atual</span><strong>{formatMoney(cashflow?.current_balance)}</strong></article>
        <article className="kpi-card"><span>Entradas previstas</span><strong>{formatMoney(cashflow?.projected_inflows)}</strong></article>
        <article className="kpi-card"><span>Saidas previstas</span><strong>{formatMoney(cashflow?.projected_outflows)}</strong></article>
        <article className="kpi-card"><span>Compras planejadas</span><strong>{formatMoney(cashflow?.planned_purchase_outflows)}</strong></article>
        <article className="kpi-card emphasis"><span>Saldo projetado</span><strong>{formatMoney(cashflow?.projected_ending_balance)}</strong></article>
      </section>

      {!!cashflow?.alerts.length && (
        <section className="panel warning-panel">
          <div className="panel-title"><h3>Alertas de caixa</h3></div>
          <ul className="plain-list">
            {cashflow.alerts.map((alert) => <li key={alert}>{alert}</li>)}
          </ul>
        </section>
      )}

      <section className="content-grid two-columns">
        <article className="panel cashflow-account-panel">
          <div className="panel-title"><h3>Saldos por conta</h3></div>
          <div className="table-shell">
            <table className="erp-table cashflow-account-table">
              <thead><tr><th>Conta</th><th>Tipo</th><th>Saldo atual</th></tr></thead>
              <tbody>
                {(cashflow?.account_balances ?? []).map((item) => (
                  <tr key={item.account_id}>
                    <td>{item.account_name}</td>
                    <td>{item.account_type}</td>
                    <td>{formatMoney(item.current_balance)}</td>
                  </tr>
                ))}
                {!cashflow?.account_balances.length && <tr><td colSpan={3} className="empty-cell">Nenhuma conta encontrada para o filtro atual.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel cashflow-period-panel">
          <div className="panel-title">
            <h3>Leitura do periodo</h3>
          </div>
          <div className="summary-list cashflow-period-summary">
            <div className="summary-row">
              <span>Fonte das entradas</span>
              <strong>{filters.include_crediario_receivables ? "Crediario importado dos boletos" : "Crediario desconsiderado"}</strong>
            </div>
            <div className="summary-row">
              <span>Fonte das saidas</span>
              <strong>{filters.include_purchase_planning ? "Despesas lancadas + previsao de compras" : "Despesas lancadas"}</strong>
            </div>
            <div className="summary-row">
              <span>Base do saldo atual</span>
              <strong>Lancamentos pagos e recebidos</strong>
            </div>
            <div className="summary-row">
              <span>Conciliacao</span>
              <strong>Extrato apenas vincula os lancamentos</strong>
            </div>
            <div className="summary-row">
              <span>Conta filtrada</span>
              <strong>{filters.account_id ? "Conta especifica" : "Consolidado"}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="panel cashflow-projection-panel">
        <div className="panel-title">
          <h3>Projecao por horizonte</h3>
          <div className="report-tabs compact">
            <button className={viewMode === "daily" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("daily")} type="button">Diario</button>
            <button className={viewMode === "weekly" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("weekly")} type="button">Semanal</button>
            <button className={viewMode === "monthly" ? "report-tab active" : "report-tab"} onClick={() => setViewMode("monthly")} type="button">Mensal</button>
          </div>
        </div>
        <div className="table-shell tall">
          <table className="erp-table cashflow-projection-table">
            <thead><tr><th>Periodo</th><th>Saldo inicial</th><th>Crediario</th><th>Cartao</th><th>Despesas lancadas</th><th>Previsao de compras</th><th>Fechamento</th></tr></thead>
            <tbody>
              {projection.map((point) => (
                <tr key={point.reference}>
                  <td>{point.reference}</td>
                  <td>{formatMoney(point.opening_balance)}</td>
                  <td>{formatMoney(point.crediario_inflows)}</td>
                  <td>{formatMoney(point.card_inflows)}</td>
                  <td>{formatMoney(point.launched_outflows)}</td>
                  <td>{formatMoney(point.planned_purchase_outflows)}</td>
                  <td>{formatMoney(point.closing_balance)}</td>
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

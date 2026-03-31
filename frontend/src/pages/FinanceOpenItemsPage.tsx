import { useMemo, useState } from "react";

import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { Account, FinancialEntry, FinancialEntryListResponse } from "../types";

type OpenTab = "payables" | "receivables" | "overdue" | "today" | "next7" | "next30";

type Props = {
  tabs: MainNavChild[];
  activeTabLabel: string;
  accounts: Account[];
  payables: FinancialEntryListResponse;
  receivables: FinancialEntryListResponse;
  filters: Record<string, string | boolean>;
  onChangeFilters: (filters: Record<string, string | boolean>) => void;
  onApplyFilters: () => Promise<void>;
};

function daysUntil(value: string | null) {
  if (!value) {
    return Number.POSITIVE_INFINITY;
  }
  const today = new Date();
  const current = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const target = new Date(value).getTime();
  return Math.floor((target - current) / 86400000);
}

function openBalance(entry: FinancialEntry) {
  return Math.max(Number(entry.total_amount) - Number(entry.paid_amount), 0);
}

export function FinanceOpenItemsPage({
  tabs,
  activeTabLabel,
  accounts,
  payables,
  receivables,
  filters,
  onChangeFilters,
  onApplyFilters,
}: Props) {
  const [openTab, setOpenTab] = useState<OpenTab>("payables");
  const currentTab = tabs.find((item) => item.key === "em-aberto") ?? tabs[0];

  const rows = useMemo(() => {
    const all = [...payables.items, ...receivables.items];
    switch (openTab) {
      case "payables":
        return payables.items;
      case "receivables":
        return receivables.items;
      case "overdue":
        return all.filter((entry) => daysUntil(entry.due_date) < 0);
      case "today":
        return all.filter((entry) => daysUntil(entry.due_date) === 0);
      case "next7":
        return all.filter((entry) => {
          const diff = daysUntil(entry.due_date);
          return diff >= 0 && diff <= 7;
        });
      case "next30":
        return all.filter((entry) => {
          const diff = daysUntil(entry.due_date);
          return diff >= 0 && diff <= 30;
        });
      default:
        return all;
    }
  }, [openTab, payables.items, receivables.items]);

  const openTotal = rows.reduce((sum, entry) => sum + openBalance(entry), 0);
  const overdueTotal = rows
    .filter((entry) => daysUntil(entry.due_date) < 0)
    .reduce((sum, entry) => sum + openBalance(entry), 0);
  const dueTodayTotal = rows
    .filter((entry) => daysUntil(entry.due_date) === 0)
    .reduce((sum, entry) => sum + openBalance(entry), 0);

  return (
    <SectionChrome
      sectionLabel="Financeiro"
      tabLabel={activeTabLabel}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <form
          className="section-toolbar-content compact-filter-layout"
          onSubmit={(event) => {
            event.preventDefault();
            void onApplyFilters();
          }}
        >
          <label>
            Periodo inicial
            <input
              type="date"
              value={String(filters.date_from ?? "")}
              onChange={(event) => onChangeFilters({ ...filters, date_from: event.target.value, page: "1" })}
            />
          </label>
          <label>
            Periodo final
            <input
              type="date"
              value={String(filters.date_to ?? "")}
              onChange={(event) => onChangeFilters({ ...filters, date_to: event.target.value, page: "1" })}
            />
          </label>
          <label>
            Conta
            <select
              value={String(filters.account_id ?? "")}
              onChange={(event) => onChangeFilters({ ...filters, account_id: event.target.value, page: "1" })}
            >
              <option value="">Todas</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>
          <button className="primary-button" type="submit">
            Atualizar
          </button>
        </form>
      </section>

      <div className="quick-chip-row">
        <button className={`filter-chip ${openTab === "payables" ? "active" : ""}`} onClick={() => setOpenTab("payables")} type="button">A pagar</button>
        <button className={`filter-chip ${openTab === "receivables" ? "active" : ""}`} onClick={() => setOpenTab("receivables")} type="button">A receber</button>
        <button className={`filter-chip ${openTab === "overdue" ? "active" : ""}`} onClick={() => setOpenTab("overdue")} type="button">Vencidos</button>
        <button className={`filter-chip ${openTab === "today" ? "active" : ""}`} onClick={() => setOpenTab("today")} type="button">Hoje</button>
        <button className={`filter-chip ${openTab === "next7" ? "active" : ""}`} onClick={() => setOpenTab("next7")} type="button">Prox. 7 dias</button>
        <button className={`filter-chip ${openTab === "next30" ? "active" : ""}`} onClick={() => setOpenTab("next30")} type="button">Prox. 30 dias</button>
      </div>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Titulos em aberto</span><strong>{rows.length}</strong></article>
        <article className="kpi-card"><span>Valor em aberto</span><strong>{formatMoney(String(openTotal))}</strong></article>
        <article className="kpi-card"><span>Vencidos</span><strong>{formatMoney(String(overdueTotal))}</strong></article>
        <article className="kpi-card"><span>Vence hoje</span><strong>{formatMoney(String(dueTodayTotal))}</strong></article>
      </section>

      <section className="content-grid two-columns">
        <article className="panel">
          <div className="panel-title"><h3>Titulos em aberto</h3></div>
          <div className="table-shell">
            <table className="erp-table">
              <thead><tr><th>Titulo</th><th>Cliente/Fornecedor</th><th>Vencimento</th><th>Saldo</th></tr></thead>
              <tbody>
                {rows.slice(0, 25).map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.title}</td>
                    <td>{entry.counterparty_name ?? "-"}</td>
                    <td>{formatDate(entry.due_date)}</td>
                    <td>{formatMoney(String(openBalance(entry)))}</td>
                  </tr>
                ))}
                {!rows.length && <tr><td className="empty-cell" colSpan={4}>Nenhum titulo encontrado neste recorte.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>
        <article className="panel">
          <div className="panel-title"><h3>Painel de vencimentos</h3></div>
          <div className="summary-list">
            <div className="summary-row"><span>Hoje</span><strong>{formatMoney(String(rows.filter((entry) => daysUntil(entry.due_date) === 0).reduce((sum, entry) => sum + openBalance(entry), 0)))}</strong></div>
            <div className="summary-row"><span>Prox. 7 dias</span><strong>{formatMoney(String(rows.filter((entry) => { const diff = daysUntil(entry.due_date); return diff >= 0 && diff <= 7; }).reduce((sum, entry) => sum + openBalance(entry), 0)))}</strong></div>
            <div className="summary-row"><span>Prox. 30 dias</span><strong>{formatMoney(String(rows.filter((entry) => { const diff = daysUntil(entry.due_date); return diff >= 0 && diff <= 30; }).reduce((sum, entry) => sum + openBalance(entry), 0)))}</strong></div>
          </div>
        </article>
      </section>
    </SectionChrome>
  );
}

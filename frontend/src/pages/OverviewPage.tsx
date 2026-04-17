import { FormEvent } from "react";

import { PageHeader } from "../components/PageHeader";
import { formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";

type Props = {
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
};

function toInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

import { Skeleton } from "../components/Skeleton";

export function OverviewPage({ dashboard, filters, loading, onChangeFilters, onApplyFilters }: Props) {
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onApplyFilters();
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
    await onApplyFilters(nextFilters);
  }

  function getKpiTone(label: string, value: number) {
    const normalized = label.toLowerCase();
    const isExpense = normalized.includes("custo") || normalized.includes("despesa") || normalized.includes("imposto") || normalized.includes("venda");
    
    if (value === 0) return "is-neutral";
    if (isExpense) {
      return value > 0 ? "is-negative" : "is-positive";
    }
    return value > 0 ? "is-positive" : "is-negative";
  }

  return (
    <div className="page-layout">
      <PageHeader
        eyebrow="Visão Geral"
        title="Dashboard Executivo"
        description="Indicadores estratégicos do DRE acumulados no período selecionado."
        actions={
          <form className="toolbar dashboard-toolbar" onSubmit={handleSubmit}>
            <div className="quick-range-group">
              <button className="ghost-button compact" onClick={() => void applyQuickRange("month")} type="button">Mês atual</button>
              <button className="ghost-button compact" onClick={() => void applyQuickRange("previous")} type="button">Mês anterior</button>
              <button className="ghost-button compact" onClick={() => void applyQuickRange("year")} type="button">Ano atual</button>
            </div>
            <div className="toolbar-date-inputs">
              <label>
                Início
                <input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} />
              </label>
              <label>
                Fim
                <input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} />
              </label>
            </div>
            <button className={`primary-button ${loading ? "is-loading" : ""}`} disabled={loading} type="submit">
              Atualizar
            </button>
          </form>
        }
      />

      {loading ? (
        <section className="kpi-grid dashboard-kpis">
          {[...Array(8)].map((_, i) => (
            <div className="kpi-card" key={i}>
              <Skeleton width="60%" height="1rem" className="mb-2" />
              <Skeleton width="90%" height="2rem" />
            </div>
          ))}
        </section>
      ) : dashboard?.dre_cards?.length ? (
        <section className="kpi-grid dashboard-kpis">
          {dashboard.dre_cards.map((card) => (
            <article className={`kpi-card ${getKpiTone(card.label, card.value)}`} key={card.label}>
              <span>{card.label}</span>
              <strong>{formatMoney(card.value)}</strong>
            </article>
          ))}
        </section>
      ) : (
        <div className="premium-empty-state dashboard-empty">
          <div className="empty-state-icon">
            <svg aria-hidden="true" fill="none" height="32" viewBox="0 0 24 24" width="32">
              <path d="M9 19V5l12 7-12 7Z" fill="currentColor" />
            </svg>
          </div>
          <h4 className="empty-state-title">Dashboard Vazio</h4>
          <p className="empty-state-desc">Vá em <strong>Configurações > Categorias</strong> e marque as linhas do DRE que você deseja acompanhar aqui.</p>
        </div>
      )}
    </div>
  );
}

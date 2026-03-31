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

  return (
    <div className="page-layout">
      <PageHeader
        eyebrow="Visao geral"
        title="Dashboard do DRE"
        description="Exibe somente os indicadores do DRE marcados para aparecer no dashboard."
        actions={
          <form className="toolbar" onSubmit={handleSubmit}>
            <div className="quick-range-group">
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
            <label>
              Inicio
              <input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} />
            </label>
            <label>
              Fim
              <input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} />
            </label>
            <button className="primary-button" disabled={loading} type="submit">
              Atualizar
            </button>
          </form>
        }
      />

      {dashboard?.dre_cards?.length ? (
        <section className="kpi-grid dashboard-kpis">
          {dashboard.dre_cards.map((card) => (
            <article className="kpi-card" key={card.label}>
              <span>{card.label}</span>
              <strong>{formatMoney(card.value)}</strong>
            </article>
          ))}
        </section>
      ) : (
        <section className="panel">
          <div className="empty-panel">
            <p className="empty-state">Nenhuma linha do DRE esta marcada com "mostrar no Dashboard".</p>
          </div>
        </section>
      )}
    </div>
  );
}

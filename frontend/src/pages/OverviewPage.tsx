import { FormEvent } from "react";

import { PageHeader } from "../components/PageHeader";
import { Skeleton } from "../components/Skeleton";
import { formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";

const DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS = 5;

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

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function formatBirthdayDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  }).format(parseIsoDate(value));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parseIsoDate(value));
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

  function getKpiTone(label: string, value: number) {
    const normalized = label.toLowerCase();
    const isExpense = normalized.includes("custo") || normalized.includes("despesa") || normalized.includes("imposto") || normalized.includes("venda");
    
    if (value === 0) return "is-neutral";
    if (isExpense) {
      return value > 0 ? "is-negative" : "is-positive";
    }
    return value > 0 ? "is-positive" : "is-negative";
  }

  const birthdayPurchaseLookbackYears =
    dashboard?.week_birthdays.purchase_lookback_years ?? DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS;

  return (
    <div className="page-layout">
      <PageHeader
        title="Dashboard Executivo"
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
          {dashboard.dre_cards.map((card) => {
            const tone = getKpiTone(card.label, Number(card.value));
            const label = card.label.toLowerCase();
            const isRevenue = label.includes("receita") || label.includes("faturamento");
            const isExpense = label.includes("despesa") || label.includes("custo");
            const isProfit = label.includes("lucro") || label.includes("margem");
            
            return (
              <article className={`kpi-card ${tone}`} key={card.label}>
                <div className="kpi-card-icon">
                  {isRevenue && (
                    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
                      <line x1="12" x2="12" y1="1" y2="23" />
                      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                    </svg>
                  )}
                  {isExpense && (
                    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
                      <rect height="14" rx="2" ry="2" width="20" x="2" y="5" />
                      <line x1="2" x2="22" y1="10" y2="10" />
                    </svg>
                  )}
                  {isProfit && (
                    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
                      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                      <polyline points="17 6 23 6 23 12" />
                    </svg>
                  )}
                  {!isRevenue && !isExpense && !isProfit && (
                    <svg fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="24">
                      <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
                      <path d="M22 12A10 10 0 0 0 12 2v10z" />
                    </svg>
                  )}
                </div>
                <span>{card.label}</span>
                <strong className="tabular-nums">{formatMoney(card.value)}</strong>
              </article>
            );
          })}
        </section>
      ) : (
        <div className="premium-empty-state dashboard-empty">
          <div className="empty-state-icon">
            <svg aria-hidden="true" fill="none" height="32" viewBox="0 0 24 24" width="32">
              <path d="M9 19V5l12 7-12 7Z" fill="currentColor" />
            </svg>
          </div>
          <h4 className="empty-state-title">Dashboard Vazio</h4>
          <p className="empty-state-desc">Vá em <strong>Configurações &gt; Categorias</strong> e marque as linhas do DRE que você deseja acompanhar aqui.</p>
        </div>
      )}

      {loading ? (
        <section className="panel-card birthday-week-panel">
          <div className="panel-title">
            <div>
              <h3>Aniversariantes da semana</h3>
              <p className="birthday-week-subtitle">
                Clientes com compra nos {birthdayPurchaseLookbackYears} ultimos anos
              </p>
            </div>
          </div>
          <div className="birthday-week-list">
            {[...Array(3)].map((_, index) => (
              <div className="birthday-week-item" key={index}>
                <div className="birthday-week-copy">
                  <Skeleton width="55%" height="1rem" />
                  <Skeleton width="42%" height="0.8rem" />
                </div>
                <Skeleton width="26%" height="1.75rem" />
              </div>
            ))}
          </div>
        </section>
      ) : dashboard ? (
        <section className="panel-card birthday-week-panel">
          <div className="panel-title">
            <div>
              <h3>Aniversariantes da semana</h3>
              <p className="birthday-week-subtitle">
                {dashboard.week_birthdays.week_label ?? "Semana atual"} • clientes com compra nos{" "}
                {birthdayPurchaseLookbackYears} ultimos anos
              </p>
            </div>
          </div>

          {dashboard.week_birthdays.items.length ? (
            <div className="birthday-week-list">
              {dashboard.week_birthdays.items.map((item) => (
                <article className="birthday-week-item" key={`${item.linx_code}-${item.birthday_date}`}>
                  <div className="birthday-week-copy">
                    <strong>{item.customer_name}</strong>
                    <span>Ultima compra: {formatShortDate(item.last_purchase_date)}</span>
                  </div>
                  <div className="birthday-week-date">{formatBirthdayDate(item.birthday_date)}</div>
                </article>
              ))}
            </div>
          ) : (
            <p className="birthday-week-empty">Nenhum aniversariante elegivel nesta semana.</p>
          )}
        </section>
      ) : null}
    </div>
  );
}

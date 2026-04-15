import { BarChart } from "../components/BarChart";
import { RevenueComparisonChart } from "../components/RevenueComparisonChart";
import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatMoneyNumber } from "../lib/format";
import type { DashboardOverview } from "../types";

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
};

export function ResultsComparativesPage({ tabs, dashboard }: Props) {
  const currentTab = tabs.find((item) => item.key === "comparativos") ?? tabs[0];

  return (
    <SectionChrome
      sectionLabel="Resultados"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Visao
            <select defaultValue="mensal">
              <option value="mensal">Mensal</option>
              <option value="anual">Anual</option>
            </select>
          </label>
          <label>
            Conta
            <select defaultValue="">
              <option value="">Todas</option>
            </select>
          </label>
          <label>
            Categoria
            <select defaultValue="">
              <option value="">Todas</option>
            </select>
          </label>
          <button className="primary-button" type="button">
            Atualizar
          </button>
        </div>
      </section>

      <section className="content-grid two-columns">
        <RevenueComparisonChart
          comparison={dashboard?.revenue_comparison ?? {
            current_year: new Date().getFullYear(),
            previous_year: new Date().getFullYear() - 1,
            points: [],
          }}
          formatValue={formatMoneyNumber}
          title="Comparativo de faturamento mensal"
        />
        <BarChart data={dashboard?.dre_chart ?? []} formatValue={formatMoneyNumber} title="Comparativo de margem" tone="success" />
      </section>

      <section className="content-grid three-columns">
        <article className="panel">
          <div className="panel-title"><h3>Visoes rapidas</h3></div>
          <div className="summary-list">
            <div className="summary-row"><span>Faturamento x ano anterior</span><strong>+14,8%</strong></div>
            <div className="summary-row"><span>Despesa operacional</span><strong>+3,2%</strong></div>
            <div className="summary-row"><span>Margem liquida</span><strong>+1,9 p.p.</strong></div>
          </div>
        </article>
        <article className="panel">
          <div className="panel-title"><h3>Top categorias</h3></div>
          <div className="summary-list">
            <div className="summary-row"><span>Recebimento Vendas</span><strong>{formatMoneyNumber(dashboard?.kpis.net_revenue)}</strong></div>
            <div className="summary-row"><span>CMV</span><strong>{formatMoneyNumber(dashboard?.kpis.cmv)}</strong></div>
            <div className="summary-row"><span>Assessoria Contabil</span><strong>{formatMoneyNumber(dashboard?.kpis.financial_expenses)}</strong></div>
          </div>
        </article>
        <article className="panel">
          <div className="panel-title"><h3>Comparativo mensal</h3></div>
          <div className="table-shell">
            <table className="erp-table">
              <thead><tr><th>Mes</th><th>Atual</th><th>Ano anterior</th></tr></thead>
              <tbody>
                {(dashboard?.revenue_comparison.points ?? []).slice(0, 6).map((item) => (
                  <tr key={item.label}>
                    <td>{item.label}</td>
                    <td>{formatMoneyNumber(item.current_year_value)}</td>
                    <td>{formatMoneyNumber(item.previous_year_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </SectionChrome>
  );
}

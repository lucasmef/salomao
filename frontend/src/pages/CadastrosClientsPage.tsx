import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatMoney } from "../lib/format";
import type { BoletoDashboard } from "../types";

type Props = {
  tabs: MainNavChild[];
  dashboard: BoletoDashboard;
};

export function CadastrosClientsPage({ tabs, dashboard }: Props) {
  const currentTab = tabs.find((item) => item.key === "clientes") ?? tabs[0];

  return (
    <SectionChrome
      sectionLabel="Cadastros"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Busca
            <input placeholder="Cliente" />
          </label>
          <label>
            Usa boleto
            <select defaultValue="">
              <option value="">Todos</option>
              <option value="true">Sim</option>
              <option value="false">Nao</option>
            </select>
          </label>
          <label>
            Modo
            <select defaultValue="">
              <option value="">Todos</option>
              <option value="individual">Individual</option>
              <option value="mensal">Mensal</option>
            </select>
          </label>
          <button className="primary-button" type="button">
            Atualizar
          </button>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Clientes cadastrados</span><strong>{dashboard.clients.length}</strong></article>
        <article className="kpi-card"><span>Usam boleto</span><strong>{dashboard.clients.filter((item) => item.uses_boleto).length}</strong></article>
        <article className="kpi-card"><span>Com pendencia</span><strong>{dashboard.summary.overdue_invoice_client_count}</strong></article>
        <article className="kpi-card"><span>Baixas pendentes</span><strong>{dashboard.summary.paid_pending_count}</strong></article>
      </section>

      <section className="panel">
        <div className="table-shell tall">
          <table className="erp-table">
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Faturas</th>
                <th>Valor</th>
                <th>Usa boleto</th>
                <th>Modo</th>
                <th>Dia</th>
                <th>Baixas pendentes</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.clients.map((client) => (
                <tr key={client.client_key}>
                  <td>{client.client_name}</td>
                  <td>{client.receivable_count}</td>
                  <td>{formatMoney(client.total_amount)}</td>
                  <td>{client.uses_boleto ? "Sim" : "Nao"}</td>
                  <td>{client.mode}</td>
                  <td>{client.boleto_due_day ?? "-"}</td>
                  <td>{client.matched_paid_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

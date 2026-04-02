import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { LoanContract, RecurrenceRule } from "../types";

type Props = {
  tabs: MainNavChild[];
  recurrences: RecurrenceRule[];
  loans: LoanContract[];
};

export function CadastrosRulesPage({ tabs, recurrences, loans }: Props) {
  const currentTab = tabs.find((item) => item.key === "regras") ?? tabs[0];

  return (
    <SectionChrome
      sectionLabel="Sistema"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Tipo de regra
            <select defaultValue="">
              <option value="">Todos</option>
              <option value="recorrencia">Recorrencia</option>
              <option value="emprestimo">Emprestimo</option>
            </select>
          </label>
          <button className="primary-button" type="button">
            Atualizar
          </button>
        </div>
      </section>

      <section className="content-grid two-columns">
        <article className="panel">
          <div className="panel-title"><h3>Regras recorrentes</h3></div>
          <div className="table-shell">
            <table className="erp-table">
              <thead><tr><th>Regra</th><th>Tipo</th><th>Frequencia</th><th>Proxima execucao</th></tr></thead>
              <tbody>
                {recurrences.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.name}</td>
                    <td>{rule.entry_type}</td>
                    <td>{rule.frequency}</td>
                    <td>{formatDate(rule.next_run_date)}</td>
                  </tr>
                ))}
                {!recurrences.length && <tr><td className="empty-cell" colSpan={4}>Nenhuma regra cadastrada.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>
        <article className="panel">
          <div className="panel-title"><h3>Contratos e financiamentos</h3></div>
          <div className="table-shell">
            <table className="erp-table">
              <thead><tr><th>Contrato</th><th>Credor</th><th>Parcelas</th><th>Valor</th></tr></thead>
              <tbody>
                {loans.map((loan) => (
                  <tr key={loan.id}>
                    <td>{loan.title}</td>
                    <td>{loan.lender_name}</td>
                    <td>{loan.installments_count}</td>
                    <td>{formatMoney(loan.installment_amount)}</td>
                  </tr>
                ))}
                {!loans.length && <tr><td className="empty-cell" colSpan={4}>Nenhum contrato cadastrado.</td></tr>}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </SectionChrome>
  );
}

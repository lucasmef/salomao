import { FormEvent, useState } from "react";

import { MoneyInput } from "../components/MoneyInput";
import { PageHeader } from "../components/PageHeader";
import { formatDate, formatMoney } from "../lib/format";
import { formatPtBrMoneyInput, normalizePtBrMoneyInput } from "../lib/money";
import type { Account, Category, LoanContract, RecurrenceRule, Transfer } from "../types";

type Props = {
  submitting: boolean;
  accounts: Account[];
  categories: Category[];
  transfers: Transfer[];
  recurrences: RecurrenceRule[];
  loans: LoanContract[];
  onCreateRecurrence: (payload: Record<string, unknown>) => Promise<void>;
  onGenerateRecurrences: (untilDate: string) => Promise<void>;
  onCreateLoan: (payload: Record<string, unknown>) => Promise<void>;
  embedded?: boolean;
};

export function OperationsPage({
  submitting,
  accounts,
  categories,
  transfers,
  recurrences,
  loans,
  onCreateRecurrence,
  onGenerateRecurrences,
  onCreateLoan,
  embedded = false,
}: Props) {
  const zeroMoneyInput = formatPtBrMoneyInput(0);
  const [recurrenceForm, setRecurrenceForm] = useState({
    name: "",
    title_template: "",
    entry_type: "expense",
    frequency: "monthly",
    interval_value: "1",
    day_of_month: "",
    start_date: "",
    end_date: "",
    amount: zeroMoneyInput,
    principal_amount: zeroMoneyInput,
    interest_amount: zeroMoneyInput,
    discount_amount: zeroMoneyInput,
    penalty_amount: zeroMoneyInput,
    account_id: "",
    category_id: "",
    interest_category_id: "",
    counterparty_name: "",
    document_number: "",
    description: "",
    notes: "",
  });
  const [loanForm, setLoanForm] = useState({
    account_id: "",
    category_id: "",
    interest_category_id: "",
    lender_name: "",
    contract_number: "",
    title: "",
    start_date: "",
    first_due_date: "",
    installments_count: "12",
    principal_total: zeroMoneyInput,
    interest_total: zeroMoneyInput,
    notes: "",
  });
  const [untilDate, setUntilDate] = useState("");

  async function handleRecurrence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateRecurrence({
      ...recurrenceForm,
      amount: normalizePtBrMoneyInput(recurrenceForm.amount),
      principal_amount: normalizePtBrMoneyInput(recurrenceForm.principal_amount),
      interest_amount: normalizePtBrMoneyInput(recurrenceForm.interest_amount),
      discount_amount: normalizePtBrMoneyInput(recurrenceForm.discount_amount),
      penalty_amount: normalizePtBrMoneyInput(recurrenceForm.penalty_amount),
      interval_value: Number(recurrenceForm.interval_value),
      day_of_month: recurrenceForm.day_of_month ? Number(recurrenceForm.day_of_month) : null,
      end_date: recurrenceForm.end_date || null,
      title_template: recurrenceForm.title_template || null,
      account_id: recurrenceForm.account_id || null,
      category_id: recurrenceForm.category_id || null,
      interest_category_id: recurrenceForm.interest_category_id || null,
      counterparty_name: recurrenceForm.counterparty_name || null,
      document_number: recurrenceForm.document_number || null,
      description: recurrenceForm.description || null,
      notes: recurrenceForm.notes || null,
    });
  }

  async function handleLoan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateLoan({
      ...loanForm,
      account_id: loanForm.account_id || null,
      category_id: loanForm.category_id || null,
      interest_category_id: loanForm.interest_category_id || null,
      contract_number: loanForm.contract_number || null,
      installments_count: Number(loanForm.installments_count),
      principal_total: normalizePtBrMoneyInput(loanForm.principal_total),
      interest_total: normalizePtBrMoneyInput(loanForm.interest_total),
      notes: loanForm.notes || null,
    });
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Financeiro"
          title="Operações estruturais"
          description="Recorrências, contratos parcelados e histórico das transferências internas."
        />
      )}
      <section className="interactive-grid">
        <article className="panel-card">
          <div className="panel-heading">
            <p className="eyebrow">Recorrência</p>
            <h3>Gerar previsões futuras</h3>
          </div>
          <form className="form-grid" onSubmit={handleRecurrence}>
            <label>
              Nome
              <input value={recurrenceForm.name} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, name: event.target.value })} required />
            </label>
            <label>
              Título gerado
              <input value={recurrenceForm.title_template} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, title_template: event.target.value })} />
            </label>
            <label>
              Tipo
              <select value={recurrenceForm.entry_type} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, entry_type: event.target.value })}>
                <option value="expense">Despesa</option>
                <option value="income">Receita</option>
              </select>
            </label>
            <label>
              Frequência
              <select value={recurrenceForm.frequency} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, frequency: event.target.value })}>
                <option value="monthly">Mensal</option>
                <option value="weekly">Semanal</option>
                <option value="daily">Diária</option>
              </select>
            </label>
            <label>
              Intervalo
              <input type="number" min="1" value={recurrenceForm.interval_value} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, interval_value: event.target.value })} />
            </label>
            <label>
              Dia do mês
              <input type="number" min="1" max="31" value={recurrenceForm.day_of_month} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, day_of_month: event.target.value })} />
            </label>
            <label>
              Inicio
              <input type="date" value={recurrenceForm.start_date} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, start_date: event.target.value })} required />
            </label>
            <label>
              Fim
              <input type="date" value={recurrenceForm.end_date} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, end_date: event.target.value })} />
            </label>
            <label>
              Conta
              <select value={recurrenceForm.account_id} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, account_id: event.target.value })}>
                <option value="">Selecionar</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Categoria
              <select value={recurrenceForm.category_id} onChange={(event) => setRecurrenceForm({ ...recurrenceForm, category_id: event.target.value })}>
                <option value="">Selecionar</option>
                {categories
                  .filter((category) => category.entry_kind === recurrenceForm.entry_type)
                  .map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Valor principal
              <MoneyInput value={recurrenceForm.principal_amount} onValueChange={(value) => setRecurrenceForm({ ...recurrenceForm, principal_amount: value, amount: value })} />
            </label>
            <label>
              Juros
              <MoneyInput value={recurrenceForm.interest_amount} onValueChange={(value) => setRecurrenceForm({ ...recurrenceForm, interest_amount: value })} />
            </label>
            <button className="primary-button" disabled={submitting} type="submit">
              Salvar recorrência
            </button>
          </form>
          <div className="inline-tools">
            <input type="date" value={untilDate} onChange={(event) => setUntilDate(event.target.value)} />
            <button className="secondary-button" disabled={submitting || !untilDate} onClick={() => void onGenerateRecurrences(untilDate)} type="button">
              Gerar até a data
            </button>
          </div>
        </article>
      </section>

      <section className="interactive-grid single-column">
        <article className="panel-card">
          <div className="panel-heading">
            <p className="eyebrow">Empréstimos e financiamentos</p>
            <h3>Parcelas com principal e juros separados</h3>
          </div>
          <form className="form-grid wide" onSubmit={handleLoan}>
            <label>
              Título
              <input value={loanForm.title} onChange={(event) => setLoanForm({ ...loanForm, title: event.target.value })} required />
            </label>
            <label>
              Credor
              <input value={loanForm.lender_name} onChange={(event) => setLoanForm({ ...loanForm, lender_name: event.target.value })} required />
            </label>
            <label>
              Contrato
              <input value={loanForm.contract_number} onChange={(event) => setLoanForm({ ...loanForm, contract_number: event.target.value })} />
            </label>
            <label>
              Conta
              <select value={loanForm.account_id} onChange={(event) => setLoanForm({ ...loanForm, account_id: event.target.value })}>
                <option value="">Selecionar</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Categoria principal
              <select value={loanForm.category_id} onChange={(event) => setLoanForm({ ...loanForm, category_id: event.target.value })}>
                <option value="">Selecionar</option>
                {categories.filter((category) => category.entry_kind === "expense").map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Categoria juros
              <select value={loanForm.interest_category_id} onChange={(event) => setLoanForm({ ...loanForm, interest_category_id: event.target.value })}>
                <option value="">Selecionar</option>
                {categories.filter((category) => category.entry_kind === "expense").map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inicio
              <input type="date" value={loanForm.start_date} onChange={(event) => setLoanForm({ ...loanForm, start_date: event.target.value })} required />
            </label>
            <label>
              Primeiro vencimento
              <input type="date" value={loanForm.first_due_date} onChange={(event) => setLoanForm({ ...loanForm, first_due_date: event.target.value })} required />
            </label>
            <label>
              Parcelas
              <input type="number" min="1" value={loanForm.installments_count} onChange={(event) => setLoanForm({ ...loanForm, installments_count: event.target.value })} required />
            </label>
            <label>
              Principal total
              <MoneyInput value={loanForm.principal_total} onValueChange={(value) => setLoanForm({ ...loanForm, principal_total: value })} required />
            </label>
            <label>
              Juros total
              <MoneyInput value={loanForm.interest_total} onValueChange={(value) => setLoanForm({ ...loanForm, interest_total: value })} />
            </label>
            <button className="primary-button" disabled={submitting} type="submit">
              Criar contrato
            </button>
          </form>
        </article>
      </section>

      <section className="interactive-grid">
        <article className="panel-card">
          <div className="panel-heading">
            <p className="eyebrow">Transferencias recentes</p>
            <h3>{transfers.length} registros</h3>
          </div>
          <div className="table-list">
            {transfers.map((transfer) => (
              <div key={transfer.id} className="entry-row">
                <div>
                  <strong>{transfer.source_account_name} → {transfer.destination_account_name}</strong>
                  <p>{formatDate(transfer.transfer_date)} • {transfer.status}</p>
                  <p>{transfer.description ?? "Sem descricao"}</p>
                </div>
                <div className="entry-aside">
                  <strong>{formatMoney(transfer.amount)}</strong>
                </div>
              </div>
            ))}
            {!transfers.length && <p className="empty-state">Nenhuma transferencia cadastrada.</p>}
          </div>
        </article>

        <article className="panel-card">
          <div className="panel-heading">
            <p className="eyebrow">Recorrencias ativas</p>
            <h3>{recurrences.length} regras</h3>
          </div>
          <div className="table-list">
            {recurrences.map((rule) => (
              <div key={rule.id} className="list-row">
                <div>
                  <strong>{rule.name}</strong>
                  <p>{rule.frequency} • proxima geracao {formatDate(rule.next_run_date)}</p>
                </div>
                <span>{formatMoney(rule.amount)}</span>
              </div>
            ))}
            {!recurrences.length && <p className="empty-state">Nenhuma recorrencia cadastrada.</p>}
          </div>
        </article>
      </section>

      <section className="interactive-grid single-column">
        <article className="panel-card">
          <div className="panel-heading">
            <p className="eyebrow">Contratos</p>
            <h3>{loans.length} emprestimos/financiamentos</h3>
          </div>
          <div className="table-list">
            {loans.map((loan) => (
              <div key={loan.id} className="report-card">
                <div className="entry-row">
                  <div>
                    <strong>{loan.title}</strong>
                    <p>{loan.lender_name} • {loan.installments_count} parcelas</p>
                    <p>Inicio {formatDate(loan.start_date)} • Primeiro vencimento {formatDate(loan.first_due_date)}</p>
                  </div>
                  <div className="entry-aside">
                    <strong>{formatMoney(loan.installment_amount)}</strong>
                    <p>parcela</p>
                  </div>
                </div>
                <div className="report-grid">
                  <div>
                    <span>Principal</span>
                    <strong>{formatMoney(loan.principal_total)}</strong>
                  </div>
                  <div>
                    <span>Juros</span>
                    <strong>{formatMoney(loan.interest_total)}</strong>
                  </div>
                  <div>
                    <span>Parcelas geradas</span>
                    <strong>{loan.installments.length}</strong>
                  </div>
                </div>
              </div>
            ))}
            {!loans.length && <p className="empty-state">Nenhum contrato criado ainda.</p>}
          </div>
        </article>
      </section>
    </div>
  );
}

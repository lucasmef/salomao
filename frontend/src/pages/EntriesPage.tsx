import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { MoneyInput } from "../components/MoneyInput";
import { PageHeader } from "../components/PageHeader";
import { TablePagination } from "../components/TablePagination";
import { formatDate, formatEntryStatus, formatMoney } from "../lib/format";
import { formatPtBrMoneyInput, normalizePtBrMoneyInput } from "../lib/money";
import type { Account, Category, FinancialEntry, FinancialEntryListResponse, Supplier } from "../types";

const todayInput = new Date().toISOString().slice(0, 10);
const zeroMoneyInput = formatPtBrMoneyInput(0);

type Props = {
  accounts: Account[];
  categories: Category[];
  suppliers: Supplier[];
  entryList: FinancialEntryListResponse;
  payables: FinancialEntryListResponse;
  receivables: FinancialEntryListResponse;
  filters: Record<string, string | boolean>;
  submitting: boolean;
  onChangeFilters: (filters: Record<string, string | boolean>) => void;
  onApplyFilters: () => Promise<void>;
  onCreateSupplier: (payload: Record<string, unknown>) => Promise<Supplier>;
  onCreateEntry: (payload: Record<string, unknown>) => Promise<void>;
  onCreateTransfer: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateEntry: (entryId: string, payload: Record<string, unknown>) => Promise<void>;
  onBulkUpdateCategory: (entryIds: string[], categoryId: string) => Promise<void>;
  onBulkDeleteEntries: (entryIds: string[]) => Promise<void>;
  onDeleteEntry: (entryId: string) => Promise<void>;
  onSettleEntry: (entryId: string, payload: Record<string, unknown>) => Promise<void>;
  onCancelEntry: (entryId: string) => Promise<void>;
  onReverseEntry: (entryId: string) => Promise<void>;
  onChangePage: (page: number) => Promise<void>;
  onChangePageSize: (pageSize: number) => Promise<void>;
  embedded?: boolean;
};

const emptyForm = {
  title: "",
  entry_type: "expense",
  status: "planned",
  account_id: "",
  category_id: "",
  supplier_id: "",
  counterparty_name: "",
  document_number: "",
  issue_date: todayInput,
  competence_date: "",
  due_date: "",
  principal_amount: zeroMoneyInput,
  interest_amount: zeroMoneyInput,
  discount_amount: zeroMoneyInput,
  penalty_amount: zeroMoneyInput,
  description: "",
  notes: "",
};

const emptySettlementPrompt = {
  entryId: "",
  account_id: "",
  paid_amount: "",
  title: "",
};

const emptyTransferForm = {
  source_account_id: "",
  destination_account_id: "",
  transfer_date: todayInput,
  amount: zeroMoneyInput,
  status: "settled",
  description: "",
  notes: "",
};

const entryTypeChipOptions = [
  { key: "expense", label: "Pagar" },
  { key: "income", label: "Receber" },
] as const;

const entryStatusChipOptions = [
  { key: "open", label: "Em aberto" },
  { key: "settled", label: "Pago" },
] as const;

export function EntriesPage({
  accounts,
  categories,
  suppliers,
  entryList,
  payables,
  receivables,
  filters,
  submitting,
  onChangeFilters,
  onApplyFilters,
  onCreateSupplier,
  onCreateEntry,
  onCreateTransfer,
  onUpdateEntry,
  onBulkUpdateCategory,
  onBulkDeleteEntries,
  onDeleteEntry,
  onSettleEntry,
  onCancelEntry,
  onReverseEntry,
  onChangePage,
  onChangePageSize,
  embedded = false,
}: Props) {
  const hasMountedAutoApplyRef = useRef(false);
  const hasMountedSearchAutoApplyRef = useRef(false);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [quickPaidAmounts, setQuickPaidAmounts] = useState<Record<string, string>>({});
  const [showFilters, setShowFilters] = useState(false);
  const [showEntryModal, setShowEntryModal] = useState(false);
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [showSettlementPrompt, setShowSettlementPrompt] = useState(false);
  const [settlementPrompt, setSettlementPrompt] = useState(emptySettlementPrompt);
  const [inlineSupplierName, setInlineSupplierName] = useState("");
  const [transferForm, setTransferForm] = useState(emptyTransferForm);
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const [bulkCategoryId, setBulkCategoryId] = useState("");

  const availableCategories = useMemo(
    () =>
      categories
        .filter((item) => item.entry_kind === form.entry_type)
        .sort((left, right) => left.name.localeCompare(right.name)),
    [categories, form.entry_type],
  );
  const categoryGroups = useMemo(
    () => [...new Set(categories.map((item) => item.report_group).filter((item): item is string => Boolean(item)))].sort(),
    [categories],
  );
  const totalPages = Math.max(1, Math.ceil(entryList.total / entryList.page_size));
  const entryPageSizeOptions = useMemo(() => {
    const baseOptions = [
      { value: 50, label: "50" },
      { value: 100, label: "100" },
      { value: 500, label: "500" },
    ];
    const options = [...baseOptions];
    if (!options.some((option) => option.value === entryList.page_size)) {
      options.unshift({ value: entryList.page_size, label: String(entryList.page_size) });
    }
    if (entryList.total > 0 && !options.some((option) => option.value === entryList.total)) {
      options.push({ value: entryList.total, label: "Todos" });
    }
    return options;
  }, [entryList.page_size, entryList.total]);
  const sortedSuppliers = useMemo(
    () => [...suppliers].sort((left, right) => left.name.localeCompare(right.name)),
    [suppliers],
  );
  const selectedCategory = useMemo(
    () => categories.find((item) => item.id === form.category_id) ?? null,
    [categories, form.category_id],
  );
  const selectedEntries = useMemo(
    () => entryList.items.filter((entry) => selectedEntryIds.includes(entry.id)),
    [entryList.items, selectedEntryIds],
  );
  const selectedEntryKind = useMemo(() => {
    if (!selectedEntries.length) {
      return "";
    }
    const kinds = new Set(
      selectedEntries.map((entry) => {
        if (entry.transfer_id || entry.entry_type === "transfer") {
          return "transfer";
        }
        if (entry.entry_type === "income" || entry.entry_type === "historical_receipt" || entry.entry_type === "historical_purchase_return") {
          return "income";
        }
        return "expense";
      }),
    );
    const [kind] = Array.from(kinds);
    return kinds.size === 1 && kind !== "transfer" ? kind : "";
  }, [selectedEntries]);
  const bulkCategoryOptions = useMemo(
    () =>
      selectedEntryKind
        ? categories
            .filter((item) => item.entry_kind === selectedEntryKind)
            .sort((left, right) => left.name.localeCompare(right.name))
        : [],
    [categories, selectedEntryKind],
  );
  const selectedDeletableEntries = useMemo(
    () => selectedEntries.filter((entry) => canDeleteEntry(entry)),
    [selectedEntries],
  );
  const selectedNonDeletableCount = selectedEntries.length - selectedDeletableEntries.length;
  const allPageSelected = entryList.items.length > 0 && entryList.items.every((entry) => selectedEntryIds.includes(entry.id));
  const activeEntryTypes = useMemo(
    () =>
      String(filters.entry_types ?? filters.entry_type ?? "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [filters.entry_type, filters.entry_types],
  );
  const activeStatuses = useMemo(
    () =>
      String(filters.statuses ?? filters.status ?? "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [filters.status, filters.statuses],
  );
  const reconciledOnly = Boolean(filters.reconciled);
  const supplierRequired = useMemo(() => {
    if (!selectedCategory || form.entry_type !== "expense") {
      return false;
    }
    const normalizedGroup = normalizeText(selectedCategory.report_group ?? "");
    const normalizedName = normalizeText(selectedCategory.name);
    return normalizedGroup.includes("compr") || normalizedName.includes("compra");
  }, [form.entry_type, selectedCategory]);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void onApplyFilters();
  }, [filters.date_from, filters.date_to, filters.date_field, filters.entry_types, filters.statuses, filters.reconciled]);

  useEffect(() => {
    if (!hasMountedSearchAutoApplyRef.current) {
      hasMountedSearchAutoApplyRef.current = true;
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void onApplyFilters();
    }, 500);

    return () => window.clearTimeout(timeoutId);
  }, [filters.search]);

  useEffect(() => {
    setSelectedEntryIds((current) => current.filter((entryId) => entryList.items.some((entry) => entry.id === entryId)));
  }, [entryList.items]);

  useEffect(() => {
    if (!bulkCategoryId) {
      return;
    }
    if (!bulkCategoryOptions.some((category) => category.id === bulkCategoryId)) {
      setBulkCategoryId("");
    }
  }, [bulkCategoryId, bulkCategoryOptions]);

  function normalizeText(value: string) {
    return value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function quickAmount(entry: FinancialEntry) {
    return quickPaidAmounts[entry.id] || formatPtBrMoneyInput(Math.max(Number(entry.total_amount) - Number(entry.paid_amount), 0));
  }

  function formatEntryFlow(entry: FinancialEntry) {
    if (entry.transfer_id) {
      if (entry.transfer_direction === "outflow") {
        return "Saida";
      }
      if (entry.transfer_direction === "inflow") {
        return "Entrada";
      }
      return "Transferencia";
    }
    if (entry.entry_type === "expense") {
      return "Pagar";
    }
    if (entry.entry_type === "income") {
      return "Receber";
    }
    return "Transferencia";
  }

  function canDeleteEntry(entry: FinancialEntry) {
    return (
      (entry.status === "planned" || entry.status === "cancelled") &&
      Number(entry.paid_amount) <= 0 &&
      !entry.settled_at &&
      !entry.transfer_id &&
      !entry.loan_installment_id &&
      !entry.purchase_installment_id &&
      !entry.is_recurring_generated
    );
  }

  function isTransferEntry(entry: FinancialEntry) {
    return Boolean(entry.transfer_id);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      ...form,
      account_id: form.account_id || null,
      category_id: form.category_id || null,
      supplier_id: form.supplier_id || null,
      counterparty_name: form.counterparty_name || null,
      document_number: form.document_number || null,
      issue_date: form.issue_date || null,
      competence_date: form.competence_date || null,
      due_date: form.due_date || null,
      principal_amount: normalizePtBrMoneyInput(form.principal_amount),
      interest_amount: normalizePtBrMoneyInput(form.interest_amount),
      discount_amount: normalizePtBrMoneyInput(form.discount_amount),
      penalty_amount: normalizePtBrMoneyInput(form.penalty_amount),
      description: form.description || null,
      notes: form.notes || null,
    };
    if (editingId) {
      await onUpdateEntry(editingId, payload);
    } else {
      await onCreateEntry(payload);
    }
    setShowEntryModal(false);
    setEditingId(null);
    setForm(emptyForm);
    setInlineSupplierName("");
  }

  async function handleTransferSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateTransfer({
      ...transferForm,
      amount: normalizePtBrMoneyInput(transferForm.amount),
      description: transferForm.description || null,
      notes: transferForm.notes || null,
    });
    setShowTransferModal(false);
    setTransferForm(emptyTransferForm);
  }

  async function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onApplyFilters();
  }

  function toggleChipFilter(kind: "entry_types" | "statuses", value: string) {
    const currentValues = kind === "entry_types" ? activeEntryTypes : activeStatuses;
    const nextValues = currentValues.includes(value)
      ? currentValues.filter((item) => item !== value)
      : [...currentValues, value];
    const nextReconciled =
      kind === "statuses" && reconciledOnly && nextValues.some((item) => item !== "settled")
        ? false
        : kind === "statuses" && reconciledOnly && !nextValues.includes("settled")
          ? false
          : reconciledOnly;

    onChangeFilters({
      ...filters,
      page: "1",
      status: "",
      statuses: kind === "statuses" ? nextValues.join(",") : activeStatuses.join(","),
      entry_type: "",
      entry_types: kind === "entry_types" ? nextValues.join(",") : activeEntryTypes.join(","),
      reconciled: nextReconciled,
    });
  }

  function toggleReconciledFilter() {
    const nextReconciled = !reconciledOnly;
    onChangeFilters({
      ...filters,
      page: "1",
      status: "",
      statuses: nextReconciled ? "settled" : String(filters.statuses ?? ""),
      reconciled: nextReconciled,
    });
  }

  function toggleEntrySelection(entryId: string) {
    setSelectedEntryIds((current) =>
      current.includes(entryId) ? current.filter((item) => item !== entryId) : [...current, entryId],
    );
  }

  function toggleAllPageEntries() {
    if (allPageSelected) {
      setSelectedEntryIds([]);
      return;
    }
    setSelectedEntryIds(entryList.items.map((entry) => entry.id));
  }

  function startEditing(entry: FinancialEntry) {
    setShowEntryModal(true);
    setInlineSupplierName("");
    setEditingId(entry.id);
    setForm({
      title: entry.title,
      entry_type: entry.entry_type,
      status: entry.status,
      account_id: entry.account_id ?? "",
      category_id: entry.category_id ?? "",
      supplier_id: entry.supplier_id ?? "",
      counterparty_name: entry.counterparty_name ?? "",
      document_number: entry.document_number ?? "",
      issue_date: entry.issue_date ?? "",
      competence_date: entry.competence_date ?? "",
      due_date: entry.due_date ?? "",
      principal_amount: formatPtBrMoneyInput(entry.principal_amount),
      interest_amount: formatPtBrMoneyInput(entry.interest_amount),
      discount_amount: formatPtBrMoneyInput(entry.discount_amount),
      penalty_amount: formatPtBrMoneyInput(entry.penalty_amount),
      description: entry.description ?? "",
      notes: entry.notes ?? "",
    });
  }

  async function handleInlineSupplierCreate() {
    const cleanName = inlineSupplierName.trim();
    if (!cleanName) {
      return;
    }
    const existing = sortedSuppliers.find((item) => normalizeText(item.name) === normalizeText(cleanName));
    if (existing) {
      setForm((current) => ({
        ...current,
        supplier_id: existing.id,
        counterparty_name: current.counterparty_name || existing.name,
      }));
      setInlineSupplierName("");
      return;
    }
    const supplier = await onCreateSupplier({
      name: cleanName,
      document_number: null,
      default_payment_term: null,
      payment_basis: "delivery",
      notes: null,
      is_active: true,
    });
    setForm((current) => ({
      ...current,
      supplier_id: supplier.id,
      counterparty_name: current.counterparty_name || supplier.name,
    }));
    setInlineSupplierName("");
  }

  async function requestSettlement(entry: FinancialEntry) {
    const amount = quickAmount(entry);
    if (entry.account_id) {
      await onSettleEntry(entry.id, { paid_amount: normalizePtBrMoneyInput(amount) });
      return;
    }
    setSettlementPrompt({
      entryId: entry.id,
      account_id: "",
      paid_amount: amount,
      title: entry.title,
    });
    setShowSettlementPrompt(true);
  }

  async function confirmSettlementWithAccount() {
    await onSettleEntry(settlementPrompt.entryId, {
      paid_amount: normalizePtBrMoneyInput(settlementPrompt.paid_amount),
      account_id: settlementPrompt.account_id,
    });
    setShowSettlementPrompt(false);
    setSettlementPrompt(emptySettlementPrompt);
  }

  async function handleBulkCategoryUpdate() {
    if (!selectedEntryIds.length || !bulkCategoryId || !selectedEntryKind) {
      return;
    }
    const selectedCategoryOption = categories.find((item) => item.id === bulkCategoryId);
    const confirmMessage = `Alterar a categoria de ${selectedEntryIds.length} lancamento(s) para ${selectedCategoryOption?.name ?? "a categoria selecionada"}?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    await onBulkUpdateCategory(selectedEntryIds, bulkCategoryId);
    setSelectedEntryIds([]);
    setBulkCategoryId("");
  }

  async function handleBulkDelete() {
    if (!selectedDeletableEntries.length || selectedNonDeletableCount > 0) {
      return;
    }
    const confirmMessage = `Excluir ${selectedDeletableEntries.length} lançamento(s) selecionado(s)? Essa ação não remove lançamentos com baixa, conciliação ou vínculo com outros processos.`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    await onBulkDeleteEntries(selectedDeletableEntries.map((entry) => entry.id));
    setSelectedEntryIds([]);
    setBulkCategoryId("");
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Financeiro"
          title="Lançamentos"
          description="Pagar, receber e consulta financeira do período."
          actions={
            <div className="toolbar entries-toolbar-compact">
              <label>
                De
                <input
                  type="date"
                  value={String(filters.date_from ?? "")}
                  onChange={(event) => onChangeFilters({ ...filters, date_from: event.target.value, page: "1" })}
                />
              </label>
              <label>
                Até
                <input
                  type="date"
                  value={String(filters.date_to ?? "")}
                  onChange={(event) => onChangeFilters({ ...filters, date_to: event.target.value, page: "1" })}
                />
              </label>
              <label>
                Busca textual
                <input
                  placeholder="Título, documento ou contraparte"
                  value={String(filters.search ?? "")}
                  onChange={(event) => onChangeFilters({ ...filters, search: event.target.value, page: "1" })}
                />
              </label>
              <button className="secondary-button" onClick={() => setShowFilters((current) => !current)} type="button">
                {showFilters ? "Ocultar filtros" : "Mais filtros"}
              </button>
              <button
                className="secondary-button"
                onClick={() => {
                  setTransferForm(emptyTransferForm);
                  setShowTransferModal(true);
                }}
                type="button"
              >
                Transferir entre contas
              </button>
              <button
                className="primary-button"
                onClick={() => {
                  setEditingId(null);
                  setForm({ ...emptyForm, issue_date: todayInput });
                  setInlineSupplierName("");
                  setShowEntryModal(true);
                }}
                type="button"
              >
                Novo lançamento
              </button>
            </div>
          }
        />
      )}

      {embedded && (
        <section className="section-toolbar-panel">
          <div className="section-toolbar-content entries-toolbar-compact">
            <label>
              De
              <input
                type="date"
                value={String(filters.date_from ?? "")}
                onChange={(event) => onChangeFilters({ ...filters, date_from: event.target.value, page: "1" })}
              />
            </label>
            <label>
              Até
              <input
                type="date"
                value={String(filters.date_to ?? "")}
                onChange={(event) => onChangeFilters({ ...filters, date_to: event.target.value, page: "1" })}
              />
            </label>
            <label>
              Busca textual
                <input
                  placeholder="Título, documento ou contraparte"
                  value={String(filters.search ?? "")}
                  onChange={(event) => onChangeFilters({ ...filters, search: event.target.value, page: "1" })}
                />
              </label>
            <button className="secondary-button" onClick={() => setShowFilters((current) => !current)} type="button">
              {showFilters ? "Ocultar filtros" : "Mais filtros"}
            </button>
            <button
              className="secondary-button"
              onClick={() => {
                setTransferForm(emptyTransferForm);
                setShowTransferModal(true);
              }}
              type="button"
            >
              Transferir entre contas
            </button>
            <button
              className="primary-button"
              onClick={() => {
                setEditingId(null);
                setForm({ ...emptyForm, issue_date: todayInput });
                setInlineSupplierName("");
                setShowEntryModal(true);
              }}
              type="button"
            >
              Novo lançamento
            </button>
          </div>
        </section>
      )}

      {showFilters && (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Filtros da consulta</h3>
          </div>
          <form className="form-grid dense entries-filter-grid" onSubmit={handleFilterSubmit}>
            <label>
              Conta
              <select value={String(filters.account_id ?? "")} onChange={(event) => onChangeFilters({ ...filters, account_id: event.target.value, page: "1" })}>
                <option value="">Todas</option>
                {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
              </select>
            </label>
            <label>
              Categoria
              <select value={String(filters.category_id ?? "")} onChange={(event) => onChangeFilters({ ...filters, category_id: event.target.value, page: "1" })}>
                <option value="">Todas</option>
                {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select>
            </label>
            <label>
              Grupo
              <select value={String(filters.report_group ?? "")} onChange={(event) => onChangeFilters({ ...filters, report_group: event.target.value, page: "1" })}>
                <option value="">Todos</option>
                {categoryGroups.map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </label>
            <label>
              Origem
              <select value={String(filters.source_system ?? "")} onChange={(event) => onChangeFilters({ ...filters, source_system: event.target.value, page: "1" })}>
                <option value="">Todas</option>
                <option value="manual">Manual</option>
                <option value="historical_cashbook">Histórico</option>
                <option value="loan">Empréstimo</option>
                <option value="recurrence">Recorrência</option>
              </select>
            </label>
            <label>
              Considerar data por
              <select value={String(filters.date_field ?? "due_date")} onChange={(event) => onChangeFilters({ ...filters, date_field: event.target.value, page: "1" })}>
                <option value="due_date">Vencimento</option>
                <option value="issue_date">Emissão</option>
              </select>
            </label>
            <label>De<input type="date" value={String(filters.date_from ?? "")} onChange={(event) => onChangeFilters({ ...filters, date_from: event.target.value, page: "1" })} /></label>
            <label>Ate<input type="date" value={String(filters.date_to ?? "")} onChange={(event) => onChangeFilters({ ...filters, date_to: event.target.value, page: "1" })} /></label>
            <label className="checkbox-line">
              <input type="checkbox" checked={Boolean(filters.include_legacy)} onChange={(event) => onChangeFilters({ ...filters, include_legacy: event.target.checked, page: "1" })} />
              Mostrar histórico antigo
            </label>
            <div className="action-row">
              <button className="primary-button" disabled={submitting} type="submit">Aplicar filtros</button>
            </div>
          </form>
        </section>
      )}

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Registros</span><strong>{entryList.total}</strong></article>
        <article className="kpi-card"><span>Total</span><strong>{formatMoney(entryList.total_amount)}</strong></article>
        <article className="kpi-card"><span>Baixado</span><strong>{formatMoney(entryList.paid_amount)}</strong></article>
        <article className="kpi-card"><span>Em aberto</span><strong>{(payables.total ?? 0) + (receivables.total ?? 0)}</strong></article>
      </section>

      <section className="panel compact-panel-card">
        <div className="panel-title compact-title-row">
          <div>
            <h3>Filtro rapido</h3>
            <p className="panel-subtitle">Combine tipo, situacao e conciliacao na mesma consulta.</p>
          </div>
        </div>
        <div className="quick-chip-row">
          {entryTypeChipOptions.map((chip) => (
            <button
              key={chip.key}
              className={`filter-chip ${activeEntryTypes.includes(chip.key) ? "active" : ""}`}
              onClick={() => toggleChipFilter("entry_types", chip.key)}
              type="button"
            >
              {chip.label}
            </button>
          ))}
          {entryStatusChipOptions.map((chip) => (
            <button
              key={chip.key}
              className={`filter-chip ${activeStatuses.includes(chip.key) ? "active" : ""}`}
              disabled={reconciledOnly && chip.key !== "settled"}
              onClick={() => toggleChipFilter("statuses", chip.key)}
              type="button"
            >
              {chip.label}
            </button>
          ))}
          <button
            className={`filter-chip ${reconciledOnly ? "active" : ""}`}
            onClick={toggleReconciledFilter}
            type="button"
          >
            Conciliado
          </button>
        </div>
      </section>

      <section className="panel compact-panel-card">
        <div className="panel-title is-column-mobile compact-title-row">
          <div>
            <h3>Lançamentos</h3>
            <p className="panel-subtitle">Consulta paginada conforme os chips e filtros selecionados.</p>
          </div>
          <TablePagination
            loading={submitting}
            onPageChange={onChangePage}
            onPageSizeChange={onChangePageSize}
            page={entryList.page}
            pageSize={entryList.page_size}
            pageSizeOptions={entryPageSizeOptions}
            totalItems={entryList.total}
            totalPages={totalPages}
          />
        </div>
        <div className="bulk-entry-toolbar">
          <label className="bulk-entry-select-all">
            <input checked={allPageSelected} onChange={toggleAllPageEntries} type="checkbox" />
            Selecionar todos desta pagina
          </label>
          <span className="bulk-entry-count">
            {selectedEntryIds.length ? `${selectedEntryIds.length} selecionado(s)` : "Nenhum lançamento selecionado"}
          </span>
          <label className="bulk-entry-category">
            Categoria em massa
            <select
              disabled={!selectedEntryIds.length || !selectedEntryKind || submitting}
              value={bulkCategoryId}
              onChange={(event) => setBulkCategoryId(event.target.value)}
            >
              <option value="">{selectedEntryIds.length ? "Selecionar categoria" : "Selecione lançamentos"}</option>
              {bulkCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary-button"
            disabled={!selectedEntryIds.length}
            onClick={() => {
              setSelectedEntryIds([]);
              setBulkCategoryId("");
            }}
            type="button"
          >
            Limpar selecao
          </button>
          <button
            className="secondary-button"
            disabled={!selectedDeletableEntries.length || selectedNonDeletableCount > 0 || submitting}
            onClick={() => void handleBulkDelete()}
            type="button"
          >
            Excluir em lote
          </button>
          <button
            className="primary-button"
            disabled={!selectedEntryIds.length || !bulkCategoryId || !selectedEntryKind || submitting}
            onClick={() => void handleBulkCategoryUpdate()}
            type="button"
          >
            Alterar categoria
          </button>
        </div>
        {selectedEntryIds.length > 0 && !selectedEntryKind && (
          <p className="bulk-entry-warning">
            Selecione apenas lançamentos da mesma natureza. Transferências e combinações de receita/despesa não entram na alteração em massa.
          </p>
        )}
        {selectedNonDeletableCount > 0 && (
          <p className="bulk-entry-warning">
            {selectedNonDeletableCount} item(ns) selecionado(s) não podem ser excluídos em lote porque já foram baixados, conciliados ou estão vinculados a outro processo.
          </p>
        )}
        <div className="table-shell tall">
          <table className="erp-table">
            <thead>
              <tr>
                <th className="checkbox-cell">Sel.</th>
                <th>Título</th>
                <th>Fluxo</th>
                <th>Conta</th>
                <th>Categoria</th>
                <th>Status</th>
                <th>Vencimento</th>
                <th className="numeric-cell">Total</th>
                <th>Acoes</th>
              </tr>
            </thead>
            <tbody>
              {entryList.items.map((entry) => (
                <tr key={entry.id}>
                  <td className="checkbox-cell">
                    <input
                      checked={selectedEntryIds.includes(entry.id)}
                      onChange={() => toggleEntrySelection(entry.id)}
                      type="checkbox"
                    />
                  </td>
                  <td>
                    <div className="cell-stack">
                      <strong>{entry.title}</strong>
                      <span>{entry.counterparty_name ?? entry.document_number ?? entry.source_system ?? "-"}</span>
                    </div>
                  </td>
                  <td>{formatEntryFlow(entry)}</td>
                  <td>{entry.account_name ?? "-"}</td>
                  <td>
                    <div className="cell-stack">
                      <strong>{entry.category_name ?? "-"}</strong>
                      <span>{entry.category_group ?? "-"}</span>
                    </div>
                  </td>
                  <td>{formatEntryStatus(entry.status)}</td>
                  <td>{formatDate(entry.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(entry.total_amount)}</td>
                  <td className="row-actions">
                    {!isTransferEntry(entry) && (
                      <>
                        <button className="table-button" type="button" onClick={() => startEditing(entry)}>Editar</button>
                        {entry.status !== "settled" && <button className="table-button" type="button" onClick={() => void requestSettlement(entry)}>Baixar</button>}
                        {entry.status === "settled" && <button className="table-button" type="button" onClick={() => void onReverseEntry(entry.id)}>Estornar</button>}
                        {canDeleteEntry(entry) && (
                          <button
                            className="table-button"
                            type="button"
                            onClick={() => {
                              if (window.confirm("Excluir este lancamento em aberto?")) {
                                void onDeleteEntry(entry.id);
                              }
                            }}
                          >
                            Excluir
                          </button>
                        )}
                        {(entry.status === "planned" || entry.status === "partial") && (
                          <button className="table-button" type="button" onClick={() => void onCancelEntry(entry.id)}>
                            Cancelar
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {!entryList.items.length && <tr><td colSpan={9} className="empty-cell">Nenhum lançamento encontrado para os filtros atuais.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {showEntryModal && (
        <div className="modal-backdrop">
          <div className="modal-card compact-entry-modal">
            <div className="panel-title compact-title-row">
              <h3>{editingId ? "Editar lançamento" : "Novo lançamento"}</h3>
              <button
                className="ghost-button"
                onClick={() => {
                  setShowEntryModal(false);
                  setEditingId(null);
                  setForm(emptyForm);
                  setInlineSupplierName("");
                }}
                type="button"
              >
                Fechar
              </button>
            </div>
            <form className="form-grid dense wide" onSubmit={handleSubmit}>
              <label>Título<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label>
              <label>
                Tipo
                <select value={form.entry_type} onChange={(event) => setForm({ ...form, entry_type: event.target.value, category_id: "" })}>
                  <option value="expense">Despesa</option>
                  <option value="income">Receita</option>
                </select>
              </label>
              <label>
                Status
                <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                  <option value="planned">Em aberto</option>
                  <option value="settled">Pago</option>
                </select>
              </label>
              <label>
                Conta
                <select value={form.account_id} onChange={(event) => setForm({ ...form, account_id: event.target.value })} required>
                  <option value="">Selecionar</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <label>
                Categoria
                <select value={form.category_id} onChange={(event) => setForm({ ...form, category_id: event.target.value })}>
                  <option value="">Selecionar</option>
                  {availableCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
                </select>
              </label>
              <label className="field-note-only">
                Juros
                <span className="field-help-text">Juros informados aqui vao para despesas financeiras automaticamente.</span>
              </label>
              <label>
                Fornecedor {supplierRequired ? "*" : ""}
                <select
                  required={supplierRequired}
                  value={form.supplier_id}
                  onChange={(event) => {
                    const supplier = sortedSuppliers.find((item) => item.id === event.target.value);
                    setForm({
                      ...form,
                      supplier_id: event.target.value,
                      counterparty_name: form.counterparty_name || supplier?.name || "",
                    });
                  }}
                >
                  <option value="">Selecionar</option>
                  {sortedSuppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}
                </select>
              </label>
              <label className="span-two">
                Adicionar fornecedor daqui mesmo
                <div className="inline-entry-row">
                  <input value={inlineSupplierName} onChange={(event) => setInlineSupplierName(event.target.value)} placeholder="Novo fornecedor" />
                  <button className="secondary-button" onClick={() => void handleInlineSupplierCreate()} type="button">
                    Criar e usar
                  </button>
                </div>
              </label>
              <label>Contraparte<input value={form.counterparty_name} onChange={(event) => setForm({ ...form, counterparty_name: event.target.value })} /></label>
              <label>Documento<input value={form.document_number} onChange={(event) => setForm({ ...form, document_number: event.target.value })} /></label>
              <label>Emissão<input type="date" value={form.issue_date} onChange={(event) => setForm({ ...form, issue_date: event.target.value })} /></label>
              <label>Competência<input type="date" value={form.competence_date} onChange={(event) => setForm({ ...form, competence_date: event.target.value })} /></label>
              <label>Vencimento<input type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></label>
              <label className="span-two amount-primary-field">Principal<MoneyInput value={form.principal_amount} onValueChange={(value) => setForm({ ...form, principal_amount: value })} /></label>
              <label>Juros<MoneyInput value={form.interest_amount} onValueChange={(value) => setForm({ ...form, interest_amount: value })} /></label>
              <label>Desconto<MoneyInput value={form.discount_amount} onValueChange={(value) => setForm({ ...form, discount_amount: value })} /></label>
              <label>Multa<MoneyInput value={form.penalty_amount} onValueChange={(value) => setForm({ ...form, penalty_amount: value })} /></label>
              <label className="span-three">Descrição<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
              <label className="span-three">Notas<textarea rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></label>
              <div className="action-row">
                <button className="primary-button" disabled={submitting} type="submit">{editingId ? "Salvar alterações" : "Criar lançamento"}</button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setShowEntryModal(false);
                    setEditingId(null);
                    setForm({ ...emptyForm, issue_date: todayInput });
                    setInlineSupplierName("");
                  }}
                  type="button"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showTransferModal && (
        <div className="modal-backdrop">
          <div className="modal-card compact-entry-modal">
            <div className="panel-title compact-title-row">
              <h3>Transferir entre contas</h3>
              <button
                className="ghost-button"
                onClick={() => {
                  setShowTransferModal(false);
                  setTransferForm(emptyTransferForm);
                }}
                type="button"
              >
                Fechar
              </button>
            </div>
            <form className="form-grid dense wide" onSubmit={handleTransferSubmit}>
              <label>
                Conta origem
                <select
                  required
                  value={transferForm.source_account_id}
                  onChange={(event) => setTransferForm((current) => ({ ...current, source_account_id: event.target.value }))}
                >
                  <option value="">Selecionar</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Conta destino
                <select
                  required
                  value={transferForm.destination_account_id}
                  onChange={(event) => setTransferForm((current) => ({ ...current, destination_account_id: event.target.value }))}
                >
                  <option value="">Selecionar</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Data
                <input
                  required
                  type="date"
                  value={transferForm.transfer_date}
                  onChange={(event) => setTransferForm((current) => ({ ...current, transfer_date: event.target.value }))}
                />
              </label>
              <label>
                Valor
                <MoneyInput
                  required
                  value={transferForm.amount}
                  onValueChange={(value) => setTransferForm((current) => ({ ...current, amount: value }))}
                />
              </label>
              <label>
                Status
                <select
                  value={transferForm.status}
                  onChange={(event) => setTransferForm((current) => ({ ...current, status: event.target.value }))}
                >
                  <option value="planned">Previsto</option>
                  <option value="settled">Realizado</option>
                </select>
              </label>
              <label className="span-two">
                Descricao
                <textarea
                  rows={2}
                  value={transferForm.description}
                  onChange={(event) => setTransferForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>
              <label className="span-three">
                Notas
                <textarea
                  rows={3}
                  value={transferForm.notes}
                  onChange={(event) => setTransferForm((current) => ({ ...current, notes: event.target.value }))}
                />
              </label>
              <div className="action-row">
                <button
                  className="primary-button"
                  disabled={
                    submitting ||
                    !transferForm.source_account_id ||
                    !transferForm.destination_account_id ||
                    transferForm.source_account_id === transferForm.destination_account_id
                  }
                  type="submit"
                >
                  Salvar transferencia
                </button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setShowTransferModal(false);
                    setTransferForm(emptyTransferForm);
                  }}
                  type="button"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showSettlementPrompt && (
        <div className="modal-backdrop">
          <div className="modal-card compact-entry-modal">
            <div className="panel-title compact-title-row">
              <h3>Selecione a conta para baixar</h3>
              <button
                className="ghost-button"
                onClick={() => {
                  setShowSettlementPrompt(false);
                  setSettlementPrompt(emptySettlementPrompt);
                }}
                type="button"
              >
                Fechar
              </button>
            </div>
            <form
              className="form-grid dense"
              onSubmit={(event) => {
                event.preventDefault();
                void confirmSettlementWithAccount();
              }}
            >
              <label className="span-two">
                Lancamento
                <input value={settlementPrompt.title} disabled />
              </label>
              <label>
                Valor
                <input value={formatMoney(settlementPrompt.paid_amount)} disabled />
              </label>
              <label>
                Conta *
                <select
                  required
                  value={settlementPrompt.account_id}
                  onChange={(event) => setSettlementPrompt((current) => ({ ...current, account_id: event.target.value }))}
                >
                  <option value="">Selecionar</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="action-row">
                <button className="primary-button" disabled={submitting || !settlementPrompt.account_id} type="submit">
                  Confirmar baixa
                </button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setShowSettlementPrompt(false);
                    setSettlementPrompt(emptySettlementPrompt);
                  }}
                  type="button"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

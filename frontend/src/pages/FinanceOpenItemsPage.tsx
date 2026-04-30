import { useEffect, useMemo, useRef, useState } from "react";

import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { Account, FinancialEntry, FinancialEntryListResponse } from "../types";

type OpenTab = "payables" | "receivables" | "overdue" | "today" | "next7" | "next30";
type OpenItemsTableColumnKey = "title" | "counterparty" | "due_date" | "balance";
type OpenItemsTableSortState = {
  key: OpenItemsTableColumnKey;
  direction: "asc" | "desc";
};
type OpenItemsCounterpartyFilterOption = {
  key: string;
  label: string;
};

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

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" fill="currentColor" />
    </svg>
  );
}

function SortDirectionIcon({ direction }: { direction: "asc" | "desc" | null }) {
  if (direction === "asc") {
    return (
      <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
        <path d="M8 12V4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        <path d="m4.75 7.25 3.25-3.25 3.25 3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  if (direction === "desc") {
    return (
      <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
        <path d="M8 4v8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        <path d="m4.75 8.75 3.25 3.25 3.25-3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return null;
}

function getCounterpartyFilterKey(entry: FinancialEntry) {
  return entry.counterparty_name?.trim() || "-";
}

function getOpenItemsSortValue(entry: FinancialEntry, column: OpenItemsTableColumnKey) {
  switch (column) {
    case "title":
      return entry.title ?? "";
    case "counterparty":
      return entry.counterparty_name ?? "";
    case "due_date":
      return entry.due_date ?? "";
    case "balance":
      return openBalance(entry);
    default:
      return "";
  }
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
  const counterpartyFilterPopoverRef = useRef<HTMLDivElement | null>(null);
  const selectAllCounterpartyCheckboxRef = useRef<HTMLInputElement | null>(null);
  const [tableSort, setTableSort] = useState<OpenItemsTableSortState | null>(null);
  const [showCounterpartyFilter, setShowCounterpartyFilter] = useState(false);
  const [excludedCounterpartyKeys, setExcludedCounterpartyKeys] = useState<string[]>([]);
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

  const counterpartyFilterOptions = useMemo(() => {
    const options = new Map<string, OpenItemsCounterpartyFilterOption>();
    rows.forEach((entry) => {
      const key = getCounterpartyFilterKey(entry);
      if (!options.has(key)) {
        options.set(key, {
          key,
          label: key,
        });
      }
    });
    return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label, "pt-BR"));
  }, [rows]);

  const allCounterpartyKeys = useMemo(
    () => counterpartyFilterOptions.map((option) => option.key),
    [counterpartyFilterOptions],
  );
  const allCounterpartiesSelected = excludedCounterpartyKeys.length === 0;
  const someCounterpartiesSelected =
    excludedCounterpartyKeys.length > 0 && excludedCounterpartyKeys.length < allCounterpartyKeys.length;

  useEffect(() => {
    setExcludedCounterpartyKeys((current) => current.filter((key) => allCounterpartyKeys.includes(key)));
  }, [allCounterpartyKeys]);

  useEffect(() => {
    if (selectAllCounterpartyCheckboxRef.current) {
      selectAllCounterpartyCheckboxRef.current.indeterminate = someCounterpartiesSelected;
    }
  }, [someCounterpartiesSelected]);

  useEffect(() => {
    if (!showCounterpartyFilter) {
      return undefined;
    }

    function handleClickOutside(event: MouseEvent) {
      const target = event.target;
      if (target instanceof Node && counterpartyFilterPopoverRef.current && !counterpartyFilterPopoverRef.current.contains(target)) {
        setShowCounterpartyFilter(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showCounterpartyFilter]);

  const filteredRows = useMemo(
    () => rows.filter((entry) => !excludedCounterpartyKeys.includes(getCounterpartyFilterKey(entry))),
    [excludedCounterpartyKeys, rows],
  );

  const visibleRows = useMemo(() => {
    const nextRows = [...filteredRows];
    if (!tableSort) {
      return nextRows;
    }

    nextRows.sort((left, right) => {
      const leftValue = getOpenItemsSortValue(left, tableSort.key);
      const rightValue = getOpenItemsSortValue(right, tableSort.key);
      let comparison = 0;

      if (typeof leftValue === "number" && typeof rightValue === "number") {
        comparison = leftValue - rightValue;
      } else {
        comparison = String(leftValue).localeCompare(String(rightValue), "pt-BR", {
          numeric: true,
          sensitivity: "base",
        });
      }

      return tableSort.direction === "asc" ? comparison : -comparison;
    });

    return nextRows;
  }, [filteredRows, tableSort]);

  function toggleTableSort(column: OpenItemsTableColumnKey) {
    setTableSort((current) => {
      if (!current || current.key !== column) {
        return { key: column, direction: "asc" };
      }
      if (current.direction === "asc") {
        return { key: column, direction: "desc" };
      }
      return null;
    });
  }

  function toggleAllCounterpartyFilters(checked: boolean) {
    setExcludedCounterpartyKeys(checked ? [] : allCounterpartyKeys);
  }

  function toggleCounterpartyFilterOption(counterpartyKey: string) {
    setExcludedCounterpartyKeys((current) =>
      current.includes(counterpartyKey)
        ? current.filter((item) => item !== counterpartyKey)
        : [...current, counterpartyKey],
    );
  }

  function renderTableHeader(label: string, column: OpenItemsTableColumnKey, numeric = false) {
    const sortDirection = tableSort?.key === column ? tableSort.direction : null;
    const showCounterpartyFilterTrigger = column === "counterparty";
    const isCounterpartyFilterActive = excludedCounterpartyKeys.length > 0;

    return (
      <div
        className={`entries-table-header finance-open-items-table-header ${numeric ? "is-numeric" : ""}`.trim()}
        ref={showCounterpartyFilterTrigger && showCounterpartyFilter ? counterpartyFilterPopoverRef : null}
      >
        <button
          className={`table-sort-button ${numeric ? "numeric" : ""}`.trim()}
          onClick={() => toggleTableSort(column)}
          type="button"
        >
          <strong>{label}</strong>
          {sortDirection ? (
            <span className="table-sort-indicator is-active">
              <SortDirectionIcon direction={sortDirection} />
            </span>
          ) : null}
        </button>
        {showCounterpartyFilterTrigger ? (
          <>
            <button
              aria-expanded={showCounterpartyFilter}
              aria-label={`Filtrar coluna ${label}`}
              className={`entries-column-filter-trigger ${isCounterpartyFilterActive ? "is-active" : ""}`.trim()}
              onClick={() => setShowCounterpartyFilter((current) => !current)}
              title={isCounterpartyFilterActive ? `${label} filtrada` : `Filtrar ${label.toLowerCase()}`}
              type="button"
            >
              <FilterFunnelIcon />
            </button>
            {showCounterpartyFilter ? (
              <div className="entries-floating-panel entries-column-filter-popover finance-open-items-filter-popover">
                <div className="entries-category-filter-head">
                  <label className="entries-category-filter-option is-all">
                    <input
                      checked={allCounterpartiesSelected}
                      onChange={(event) => toggleAllCounterpartyFilters(event.target.checked)}
                      ref={selectAllCounterpartyCheckboxRef}
                      type="checkbox"
                    />
                    <span>Selecionar tudo</span>
                  </label>
                </div>
                <div className="entries-category-filter-list">
                  {counterpartyFilterOptions.length ? (
                    counterpartyFilterOptions.map((option) => (
                      <label className="entries-category-filter-option" key={option.key}>
                        <input
                          checked={!excludedCounterpartyKeys.includes(option.key)}
                          onChange={() => toggleCounterpartyFilterOption(option.key)}
                          type="checkbox"
                        />
                        <span title={option.label}>{option.label}</span>
                      </label>
                    ))
                  ) : (
                    <p className="entries-category-filter-empty">Nenhum cliente ou fornecedor encontrado nesta aba.</p>
                  )}
                </div>
                <div className="entries-column-filter-popover-actions">
                  <button
                    className="secondary-button compact-button"
                    onClick={() => toggleAllCounterpartyFilters(true)}
                    type="button"
                  >
                    Restaurar
                  </button>
                  <button className="ghost-button compact" onClick={() => setShowCounterpartyFilter(false)} type="button">
                    Fechar
                  </button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    );
  }

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
          <div className="table-shell table-shell--scroll entries-table-shell finance-open-items-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table finance-open-items-table" data-mobile-width="compact">
              <colgroup>
                <col className="finance-open-items-col-title" />
                <col className="finance-open-items-col-counterparty col-hide-md" />
                <col className="finance-open-items-col-due-date" />
                <col className="finance-open-items-col-balance" />
              </colgroup>
              <thead>
                <tr>
                  <th>{renderTableHeader("Titulo", "title")}</th>
                  <th className="col-hide-md">{renderTableHeader("Cliente/Fornecedor", "counterparty")}</th>
                  <th>{renderTableHeader("Vencimento", "due_date")}</th>
                  <th className="numeric-cell">{renderTableHeader("Saldo", "balance", true)}</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.slice(0, 25).map((entry) => (
                  <tr key={entry.id}>
                    <td className="finance-open-items-cell-title">
                      <strong title={entry.title}>{entry.title}</strong>
                    </td>
                    <td className="finance-open-items-cell-counterparty col-hide-md">
                      <span title={entry.counterparty_name ?? "-"}>{entry.counterparty_name ?? "-"}</span>
                    </td>
                    <td>{formatDate(entry.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(String(openBalance(entry)))}</td>
                  </tr>
                ))}
                {!visibleRows.length ? (
                  <tr>
                    <td className="empty-cell" colSpan={4}>Nenhum titulo encontrado para os filtros atuais.</td>
                  </tr>
                ) : null}
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

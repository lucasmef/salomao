import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Select, { type MultiValue, type SingleValue } from "react-select";
import { useConfirm } from "../components/ConfirmContext";
import { MoneyInput } from "../components/MoneyInput";
import { ModalCloseButton } from "../components/ModalCloseButton";
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
  payables?: FinancialEntryListResponse;
  receivables?: FinancialEntryListResponse;
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
  competence_date: todayInput,
  due_date: todayInput,
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

const entryQuickFilterOptions = [
  { value: "open", label: "Aberto" },
  { value: "settled", label: "Pago" },
  { value: "expense", label: "Pagar" },
  { value: "income", label: "Receber" },
  { value: "reconciled", label: "Conciliado" },
] as const;

const entryFilterSelectStyles = {
  control: (base: Record<string, unknown>, state: { isFocused: boolean }) => ({
    ...base,
    minHeight: 36,
    borderRadius: 10,
    borderColor: state.isFocused ? "#c5d0df" : "#d7e1ef",
    boxShadow: "none",
    backgroundColor: "#ffffff",
    fontSize: "0.84rem",
    ":hover": {
      borderColor: "#c5d0df",
    },
  }),
  valueContainer: (base: Record<string, unknown>) => ({
    ...base,
    padding: "0 10px",
  }),
  placeholder: (base: Record<string, unknown>) => ({
    ...base,
    color: "#607087",
  }),
  input: (base: Record<string, unknown>) => ({
    ...base,
    margin: 0,
    padding: 0,
  }),
  option: (base: Record<string, unknown>, state: { isFocused: boolean; isSelected: boolean }) => ({
    ...base,
    fontSize: "0.82rem",
    backgroundColor: state.isSelected ? "#2f5be7" : state.isFocused ? "#eef4ff" : "#fff",
    color: state.isSelected ? "#fff" : "#24364f",
  }),
  menuPortal: (base: Record<string, unknown>) => ({
    ...base,
    zIndex: 9999,
  }),
};

type QuickFilterOption = (typeof entryQuickFilterOptions)[number];
type EntryFormOption = { value: string; label: string };
type EntryTableColumnKey = "title" | "flow" | "account" | "category" | "status" | "due_date" | "total_amount";
type EntryTableSortState = {
  key: EntryTableColumnKey;
  direction: "asc" | "desc";
};
const entryTableColumnLabels: Record<EntryTableColumnKey, string> = {
  title: "Título",
  flow: "Fluxo",
  account: "Conta",
  category: "Categoria",
  status: "Status",
  due_date: "Vencimento",
  total_amount: "Total",
};
type EntryCategoryFilterOption = {
  key: string;
  label: string;
  group: string;
};

function CalendarRangeIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M4 1.75a.75.75 0 0 1 1.5 0V3h5V1.75a.75.75 0 0 1 1.5 0V3h.75A2.25 2.25 0 0 1 15 5.25v7.5A2.25 2.25 0 0 1 12.75 15h-9.5A2.25 2.25 0 0 1 1 12.75v-7.5A2.25 2.25 0 0 1 3.25 3H4V1.75ZM2.5 6.5v6.25c0 .414.336.75.75.75h9.5a.75.75 0 0 0 .75-.75V6.5h-11Zm11-1.5v-.75a.75.75 0 0 0-.75-.75h-.75v.5a.75.75 0 0 1-1.5 0v-.5h-5v.5a.75.75 0 0 1-1.5 0v-.5h-.75a.75.75 0 0 0-.75.75V5h11Z" fill="currentColor" />
    </svg>
  );
}

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" fill="currentColor" />
    </svg>
  );
}

function SlidersIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M3 4a2 2 0 1 1 3.874.7h6.376a.75.75 0 0 1 0 1.5H6.874A2.001 2.001 0 0 1 3 6a1.99 1.99 0 0 1-.874-.2H1.75a.75.75 0 0 1 0-1.5h.376C2.301 4.11 2.637 4 3 4Zm0 1.5a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1Zm10 4.5a2 2 0 1 1-3.874-.7H1.75a.75.75 0 0 1 0-1.5h7.376A2.001 2.001 0 0 1 13 8a1.99 1.99 0 0 1 .874.2h.376a.75.75 0 0 1 0 1.5h-.376A1.99 1.99 0 0 1 13 10Zm0-1.5a.5.5 0 1 0 0 1 .5.5 0 0 0 0-1Z" fill="currentColor" />
    </svg>
  );
}

function TransferIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M3.22 5.03a.75.75 0 0 1 0-1.06l2-2a.75.75 0 1 1 1.06 1.06L5.56 3.75h6.69a.75.75 0 0 1 0 1.5H5.56l.72.72a.75.75 0 0 1-1.06 1.06l-2-2Zm9.56 5.94a.75.75 0 0 1 0 1.06l-2 2a.75.75 0 1 1-1.06-1.06l.72-.72H3.75a.75.75 0 0 1 0-1.5h6.69l-.72-.72a.75.75 0 0 1 1.06-1.06l2 2Z" fill="currentColor" />
    </svg>
  );
}

function PlusSquareIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M3.25 2A2.25 2.25 0 0 0 1 4.25v7.5A2.25 2.25 0 0 0 3.25 14h9.5A2.25 2.25 0 0 0 15 11.75v-7.5A2.25 2.25 0 0 0 12.75 2h-9.5ZM2.5 4.25a.75.75 0 0 1 .75-.75h9.5a.75.75 0 0 1 .75.75v7.5a.75.75 0 0 1-.75.75h-9.5a.75.75 0 0 1-.75-.75v-7.5ZM8 5a.75.75 0 0 1 .75.75v1.5h1.5a.75.75 0 0 1 0 1.5h-1.5v1.5a.75.75 0 0 1-1.5 0v-1.5h-1.5a.75.75 0 0 1 0-1.5h1.5v-1.5A.75.75 0 0 1 8 5Z" fill="currentColor" />
    </svg>
  );
}

function StackEditIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M3.75 2h5.19a.75.75 0 0 1 0 1.5H3.75a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25V7.06a.75.75 0 0 1 1.5 0v5.19A1.75 1.75 0 0 1 12.25 14h-8.5A1.75 1.75 0 0 1 2 12.25v-8.5C2 2.784 2.784 2 3.75 2Zm8.78-.53a.75.75 0 0 1 0 1.06l-.634.634 1.06 1.06.634-.634a.75.75 0 1 1 1.06 1.06l-.634.634.514.514a.75.75 0 0 1-1.06 1.06l-.514-.514-4.36 4.36a.75.75 0 0 1-.344.193l-2 .5a.75.75 0 0 1-.91-.91l.5-2a.75.75 0 0 1 .193-.344l4.36-4.36-.514-.514a.75.75 0 0 1 1.06-1.06l.514.514.634-.634a.75.75 0 0 1 1.06 0ZM7.06 9.47l-.22.878.878-.22 4.03-4.03-1.06-1.06-4.03 4.03Z" fill="currentColor" />
    </svg>
  );
}

function MoreVerticalIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M8 3.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5Zm0 5.75a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5ZM9.25 13.5a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" fill="currentColor" />
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
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path d="M8 12V4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      <path d="m5.3 6.2 2.7-2.7 2.7 2.7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      <path d="m5.3 9.8 2.7 2.7 2.7-2.7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}

function getEntryCategoryFilterKey(entry: FinancialEntry) {
  return `${entry.category_name ?? "Sem categoria"}__${entry.category_group ?? ""}`;
}

function getEntrySortValue(entry: FinancialEntry, column: EntryTableColumnKey) {
  switch (column) {
    case "title":
      return `${entry.title} ${entry.counterparty_name ?? ""} ${entry.document_number ?? ""} ${entry.source_system ?? ""}`.trim();
    case "flow":
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
    case "account":
      return entry.account_name ?? "";
    case "category":
      return `${entry.category_name ?? ""} ${entry.category_group ?? ""}`.trim();
    case "status":
      return formatEntryStatus(entry.status);
    case "due_date":
      return entry.due_date ?? "";
    case "total_amount":
      return Number(entry.total_amount);
    default:
      return "";
  }
}

export function EntriesPage({
  accounts,
  categories,
  suppliers,
  entryList,
  payables: _payables,
  receivables: _receivables,
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
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const categoryFilterPopoverRef = useRef<HTMLDivElement | null>(null);
  const selectAllCategoryCheckboxRef = useRef<HTMLInputElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);
  const bulkMenuRef = useRef<HTMLDivElement | null>(null);
  const rowMenuRef = useRef<HTMLDivElement | null>(null);
  const [focusedRowIndex, setFocusedRowIndex] = useState<number>(-1);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [quickPaidAmounts, setQuickPaidAmounts] = useState<Record<string, string>>({});
  const [showFilters, setShowFilters] = useState(false);
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);
  const [showBulkActions, setShowBulkActions] = useState(false);
  const [showEntryModal, setShowEntryModal] = useState(false);
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [showSettlementPrompt, setShowSettlementPrompt] = useState(false);
  const [settlementPrompt, setSettlementPrompt] = useState(emptySettlementPrompt);
  const [transferForm, setTransferForm] = useState(emptyTransferForm);
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const [tableSort, setTableSort] = useState<EntryTableSortState | null>(null);
  const [showCategoryFilter, setShowCategoryFilter] = useState(false);
  const [selectedCategoryFilterKeys, setSelectedCategoryFilterKeys] = useState<string[]>([]);
  const [bulkCategoryId, setBulkCategoryId] = useState("");
  const [activeRowMenuId, setActiveRowMenuId] = useState<string | null>(null);
  const portalTarget = typeof document !== "undefined" ? document.body : null;

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
  const supplierSelectOptions = useMemo<EntryFormOption[]>(
    () => sortedSuppliers.map((supplier) => ({ value: supplier.id, label: supplier.name })),
    [sortedSuppliers],
  );
  const selectedCategory = useMemo(
    () => categories.find((item) => item.id === form.category_id) ?? null,
    [categories, form.category_id],
  );
  const categorySelectOptions = useMemo<EntryFormOption[]>(
    () =>
      availableCategories.map((category) => ({
        value: category.id,
        label: category.name,
      })),
    [availableCategories],
  );
  const selectedSupplierOption = useMemo(
    () => supplierSelectOptions.find((option) => option.value === form.supplier_id) ?? null,
    [form.supplier_id, supplierSelectOptions],
  );
  const selectedCategoryOption = useMemo(
    () => categorySelectOptions.find((option) => option.value === form.category_id) ?? null,
    [categorySelectOptions, form.category_id],
  );
  const entryCategoryFilterOptions = useMemo(() => {
    const categoryMap = new Map<string, EntryCategoryFilterOption>();
    entryList.items.forEach((entry) => {
      const key = getEntryCategoryFilterKey(entry);
      if (!categoryMap.has(key)) {
        categoryMap.set(key, {
          key,
          label: entry.category_name ?? "Sem categoria",
          group: entry.category_group ?? "",
        });
      }
    });
    return Array.from(categoryMap.values()).sort((left, right) => {
      const labelComparison = left.label.localeCompare(right.label, "pt-BR", { numeric: true });
      if (labelComparison !== 0) {
        return labelComparison;
      }
      return left.group.localeCompare(right.group, "pt-BR", { numeric: true });
    });
  }, [entryList.items]);
  const allCategoryFilterKeys = useMemo(
    () => entryCategoryFilterOptions.map((option) => option.key),
    [entryCategoryFilterOptions],
  );
  const someCategoriesSelected =
    selectedCategoryFilterKeys.length > 0 && selectedCategoryFilterKeys.length < allCategoryFilterKeys.length;
  const allCategoriesSelected =
    allCategoryFilterKeys.length === 0 || selectedCategoryFilterKeys.length === allCategoryFilterKeys.length;
  const filteredEntries = useMemo(
    () =>
      entryList.items.filter((entry) => {
        if (!allCategoryFilterKeys.length) {
          return true;
        }
        return selectedCategoryFilterKeys.includes(getEntryCategoryFilterKey(entry));
      }),
    [allCategoryFilterKeys.length, entryList.items, selectedCategoryFilterKeys],
  );
  const visibleEntries = useMemo(() => {
    if (!tableSort) {
      return filteredEntries;
    }
    const sortedEntries = [...filteredEntries];
    sortedEntries.sort((left, right) => {
      const leftValue = getEntrySortValue(left, tableSort.key);
      const rightValue = getEntrySortValue(right, tableSort.key);
      const result =
        tableSort.key === "total_amount"
          ? Number(leftValue) - Number(rightValue)
          : String(leftValue).localeCompare(String(rightValue), "pt-BR", { numeric: true });
      return tableSort.direction === "asc" ? result : -result;
    });
    return sortedEntries;
  }, [filteredEntries, tableSort]);
  const selectedEntries = useMemo(
    () => visibleEntries.filter((entry) => selectedEntryIds.includes(entry.id)),
    [selectedEntryIds, visibleEntries],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if an input is focused, unless it's the Escape key
      const activeEl = document.activeElement?.tagName;
      const isInputFocused = ["INPUT", "TEXTAREA", "SELECT"].includes(activeEl ?? "");
      
      if (e.key === "Escape") {
        setShowPeriodPopover(false);
        setShowPresetMenu(false);
        setShowEntryModal(false);
        setShowTransferModal(false);
        setShowBulkMenu(false);
        setShowCategoryFilterPopover(false);
        setActiveRowMenuId(null);
        return;
      }

      if (isInputFocused) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedRowIndex((prev) => Math.min(prev + 1, visibleEntries.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedRowIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === " ") {
        if (focusedRowIndex >= 0) {
          e.preventDefault();
          const entryId = visibleEntries[focusedRowIndex].id;
          toggleEntrySelection(entryId);
        }
      } else if (e.key === "Enter") {
        if (focusedRowIndex >= 0) {
          e.preventDefault();
          startEditing(visibleEntries[focusedRowIndex]);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [visibleEntries, focusedRowIndex, selectedEntryIds]);

  useEffect(() => {
    // Reset focus when filters change or data is reloaded
    setFocusedRowIndex(-1);
  }, [filters, entryList]);
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
  const allPageSelected = visibleEntries.length > 0 && visibleEntries.every((entry) => selectedEntryIds.includes(entry.id));
  const visibleTotalAmount = useMemo(
    () => visibleEntries.reduce((total, entry) => total + Number(entry.total_amount), 0),
    [visibleEntries],
  );
  const visiblePaidAmount = useMemo(
    () => visibleEntries.reduce((total, entry) => total + Number(entry.paid_amount), 0),
    [visibleEntries],
  );
  const visibleOpenAmount = useMemo(
    () => Math.max(visibleTotalAmount - visiblePaidAmount, 0).toFixed(2),
    [visiblePaidAmount, visibleTotalAmount],
  );
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
  const selectedQuickFilterValues = useMemo(() => {
    const values = new Set<string>();
    activeEntryTypes.forEach((value) => values.add(value));
    activeStatuses.forEach((value) => values.add(value));
    if (reconciledOnly) {
      values.add("reconciled");
      values.delete("open");
      values.add("settled");
    }
    return Array.from(values);
  }, [activeEntryTypes, activeStatuses, reconciledOnly]);
  const selectedQuickFilterOptions = useMemo(
    () => entryQuickFilterOptions.filter((option) => selectedQuickFilterValues.includes(option.value)),
    [selectedQuickFilterValues],
  );
  const quickFilterPlaceholder =
    selectedQuickFilterOptions.length === 0
      ? "Filtro rápido"
      : selectedQuickFilterOptions.length === 1
        ? selectedQuickFilterOptions[0]?.label ?? "1 filtro"
        : `${selectedQuickFilterOptions.length} filtros selecionados`;
  const openAmount = useMemo(
    () => Math.max(Number(entryList.total_amount) - Number(entryList.paid_amount), 0).toFixed(2),
    [entryList.paid_amount, entryList.total_amount],
  );
  const entryPreviewTotal = useMemo(() => {
    const principal = Number(normalizePtBrMoneyInput(form.principal_amount) || "0");
    const interest = Number(normalizePtBrMoneyInput(form.interest_amount) || "0");
    const discount = Number(normalizePtBrMoneyInput(form.discount_amount) || "0");
    const penalty = Number(normalizePtBrMoneyInput(form.penalty_amount) || "0");
    return principal + interest + discount + penalty;
  }, [form.discount_amount, form.interest_amount, form.penalty_amount, form.principal_amount]);
  const supplierRequired = useMemo(() => {
    if (!selectedCategory || form.entry_type !== "expense") {
      return false;
    }
    const normalizedGroup = normalizeText(selectedCategory.report_group ?? "");
    const normalizedName = normalizeText(selectedCategory.name);
    return normalizedGroup.includes("compr") || normalizedName.includes("compra");
  }, [form.entry_type, selectedCategory]);

  useEffect(() => {
    setSelectedCategoryFilterKeys(allCategoryFilterKeys);
  }, [allCategoryFilterKeys]);

  useEffect(() => {
    if (!selectAllCategoryCheckboxRef.current) {
      return;
    }
    selectAllCategoryCheckboxRef.current.indeterminate = someCategoriesSelected;
  }, [someCategoriesSelected]);

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
    setSelectedEntryIds((current) => current.filter((entryId) => visibleEntries.some((entry) => entry.id === entryId)));
  }, [visibleEntries]);

  useEffect(() => {
    if (!bulkCategoryId) {
      return;
    }
    if (!bulkCategoryOptions.some((category) => category.id === bulkCategoryId)) {
      setBulkCategoryId("");
    }
  }, [bulkCategoryId, bulkCategoryOptions]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
      if (showCategoryFilter && categoryFilterPopoverRef.current && !categoryFilterPopoverRef.current.contains(target)) {
        setShowCategoryFilter(false);
      }
      if (showPresetMenu && presetMenuRef.current && !presetMenuRef.current.contains(target)) {
        setShowPresetMenu(false);
      }
      if (showBulkActions && bulkMenuRef.current && !bulkMenuRef.current.contains(target)) {
        setShowBulkActions(false);
      }
      if (activeRowMenuId && rowMenuRef.current && !rowMenuRef.current.contains(target)) {
        setActiveRowMenuId(null);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [activeRowMenuId, showBulkActions, showCategoryFilter, showPeriodPopover, showPresetMenu]);

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

  function mergeObservation(description?: string | null, notes?: string | null) {
    return [description, notes]
      .map((value) => value?.trim())
      .filter((value): value is string => Boolean(value))
      .join("\n\n");
  }

  function formatRangeLabel(start: string, end: string) {
    if (!start && !end) {
      return "Selecionar período";
    }
    if (start && end) {
      return `${formatDate(start)} - ${formatDate(end)}`;
    }
    return start ? `${formatDate(start)} - ...` : `... - ${formatDate(end)}`;
  }

  function setDateRange(dateFrom: string, dateTo: string) {
    onChangeFilters({
      ...filters,
      date_from: dateFrom,
      date_to: dateTo,
      page: "1",
    });
  }

  function applyPresetRange(kind: "today" | "current_month" | "previous_month" | "current_year") {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const formatValue = (value: Date) => value.toISOString().slice(0, 10);

    if (kind === "today") {
      const current = formatValue(today);
      setDateRange(current, current);
      return;
    }

    if (kind === "current_month") {
      const start = new Date(year, month, 1);
      const end = new Date(year, month + 1, 0);
      setDateRange(formatValue(start), formatValue(end));
      return;
    }

    if (kind === "previous_month") {
      const start = new Date(year, month - 1, 1);
      const end = new Date(year, month, 0);
      setDateRange(formatValue(start), formatValue(end));
      return;
    }

    const start = new Date(year, 0, 1);
    const end = new Date(year, 11, 31);
    setDateRange(formatValue(start), formatValue(end));
  }

  function normalizeQuickFilters(values: string[]) {
    const normalized = new Set(values);
    if (normalized.has("reconciled")) {
      normalized.delete("open");
      normalized.add("settled");
    }
    return Array.from(normalized);
  }

  function applyQuickFilters(options: MultiValue<QuickFilterOption>) {
    const normalizedValues = normalizeQuickFilters(options.map((option) => option.value));
    const nextEntryTypes = normalizedValues.filter((value) => value === "expense" || value === "income");
    const nextStatuses = normalizedValues.filter((value) => value === "open" || value === "settled");
    const nextReconciled = normalizedValues.includes("reconciled");

    onChangeFilters({
      ...filters,
      page: "1",
      entry_type: "",
      status: "",
      entry_types: nextEntryTypes.join(","),
      statuses: nextStatuses.join(","),
      reconciled: nextReconciled,
    });
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
      (entry.status === "planned" || entry.status === "cancelled" || entry.status === "open") &&
      Number(entry.paid_amount) <= 0 &&
      !entry.settled_at &&
      !entry.transfer_id &&
      !entry.loan_installment_id &&
      !entry.is_recurring_generated
    );
  }

  function isPurchaseInvoiceEntry(entry: FinancialEntry) {
    return Boolean(entry.purchase_invoice_id || entry.purchase_installment_id);
  }

  function isTransferEntry(entry: FinancialEntry) {
    return Boolean(entry.transfer_id);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (supplierRequired && !form.supplier_id) {
      window.alert("Selecione o fornecedor.");
      return;
    }
    const selectedSupplier = sortedSuppliers.find((supplier) => supplier.id === form.supplier_id);
    const normalizedTitle = form.title.trim() || selectedCategory?.name?.trim() || selectedSupplier?.name?.trim() || "Lançamento";
    const observation = form.notes.trim();
    const payload = {
      ...form,
      title: normalizedTitle,
      account_id: form.account_id || null,
      category_id: form.category_id || null,
      supplier_id: form.supplier_id || null,
      counterparty_name: selectedSupplier?.name || form.counterparty_name || null,
      document_number: form.document_number || null,
      issue_date: form.issue_date || null,
      competence_date: form.competence_date || null,
      due_date: form.due_date || null,
      principal_amount: normalizePtBrMoneyInput(form.principal_amount),
      interest_amount: normalizePtBrMoneyInput(form.interest_amount),
      discount_amount: normalizePtBrMoneyInput(form.discount_amount),
      penalty_amount: normalizePtBrMoneyInput(form.penalty_amount),
      description: null,
      notes: observation || null,
    };
    if (editingId) {
      await onUpdateEntry(editingId, payload);
    } else {
      await onCreateEntry(payload);
    }
    setShowEntryModal(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  async function handleTransferSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateTransfer({
      ...transferForm,
      status: "settled",
      amount: normalizePtBrMoneyInput(transferForm.amount),
      description: transferForm.description || null,
      notes: null,
    });
    setShowTransferModal(false);
    setTransferForm(emptyTransferForm);
  }

  async function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onApplyFilters();
  }

  function toggleTableSort(column: EntryTableColumnKey) {
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

  function toggleAllCategoryFilters(checked: boolean) {
    setSelectedCategoryFilterKeys(checked ? allCategoryFilterKeys : []);
  }

  function toggleCategoryFilterOption(categoryKey: string) {
    setSelectedCategoryFilterKeys((current) =>
      current.includes(categoryKey) ? current.filter((item) => item !== categoryKey) : [...current, categoryKey],
    );
  }

  function renderTableHeader(label: string, column: EntryTableColumnKey, numeric = false) {
    const sortDirection = tableSort?.key === column ? tableSort.direction : null;
    const showCategoryFilterTrigger = column === "category";
    const isCategoryFilterActive = !allCategoriesSelected;
    return (
      <div
        className={`entries-table-header ${numeric ? "is-numeric" : ""}`.trim()}
        ref={showCategoryFilterTrigger && showCategoryFilter ? categoryFilterPopoverRef : null}
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
        {showCategoryFilterTrigger ? (
          <>
            <button
              aria-expanded={showCategoryFilter}
              aria-label={`Filtrar coluna ${label}`}
              className={`entries-column-filter-trigger ${isCategoryFilterActive ? "is-active" : ""}`.trim()}
              onClick={() => setShowCategoryFilter((current) => !current)}
              title={isCategoryFilterActive ? `${label} filtrada` : `Filtrar ${label.toLowerCase()}`}
              type="button"
            >
              <FilterFunnelIcon />
              <span className="entries-toolbar-icon-label">Atalhos</span>
            </button>
            {showCategoryFilter && (
              <div className="entries-floating-panel entries-column-filter-popover" id="entries-category-filter">
                <div className="entries-category-filter-head">
                  <label className="entries-category-filter-option is-all">
                    <input
                      checked={allCategoriesSelected}
                      ref={selectAllCategoryCheckboxRef}
                      onChange={(event) => toggleAllCategoryFilters(event.target.checked)}
                      type="checkbox"
                    />
                    <span>Selecionar tudo</span>
                  </label>
                </div>
                <div className="entries-category-filter-list">
                  {entryCategoryFilterOptions.length ? (
                    entryCategoryFilterOptions.map((option) => (
                      <label className="entries-category-filter-option" key={option.key}>
                        <input
                          checked={selectedCategoryFilterKeys.includes(option.key)}
                          onChange={() => toggleCategoryFilterOption(option.key)}
                          type="checkbox"
                        />
                        <span className="entries-category-filter-text">
                          <strong>{option.label}</strong>
                          <small>{option.group || "Sem grupo"}</small>
                        </span>
                      </label>
                    ))
                  ) : (
                    <p className="entries-category-filter-empty">Nenhuma categoria encontrada nesta página.</p>
                  )}
                </div>
                <div className="entries-column-filter-popover-actions">
                  <button
                    className="secondary-button compact-button"
                    onClick={() => toggleAllCategoryFilters(true)}
                    type="button"
                  >
                    Restaurar
                  </button>
                  <button
                    className="ghost-button compact"
                    onClick={() => setShowCategoryFilter(false)}
                    type="button"
                  >
                    Fechar
                  </button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    );
  }

  function toggleEntrySelection(entryId: string) {
    setSelectedEntryIds((current) =>
      current.includes(entryId) ? current.filter((item) => item !== entryId) : [...current, entryId],
    );
  }

  function toggleAllPageEntries() {
    if (allPageSelected) {
      setSelectedEntryIds((current) =>
        current.filter((entryId) => !visibleEntries.some((entry) => entry.id === entryId)),
      );
      return;
    }
    setSelectedEntryIds((current) => Array.from(new Set([...current, ...visibleEntries.map((entry) => entry.id)])));
  }

  function startEditing(entry: FinancialEntry) {
    setShowEntryModal(true);
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
      description: "",
      notes: mergeObservation(entry.description, entry.notes),
    });
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

  const { confirm } = useConfirm();

  async function handleBulkCategoryUpdate() {
    if (!selectedEntryIds.length || !bulkCategoryId || !selectedEntryKind) {
      return;
    }
    const selectedCategoryOption = categories.find((item) => item.id === bulkCategoryId);
    
    const confirmed = await confirm({
      title: "Alterar Categoria em Lote",
      message: `Deseja alterar a categoria de ${selectedEntryIds.length} lançamento(s) para "${selectedCategoryOption?.name}"?`,
      confirmLabel: "Alterar em Lote",
      tone: "info"
    });

    if (!confirmed) return;

    await onBulkUpdateCategory(selectedEntryIds, bulkCategoryId);
    setSelectedEntryIds([]);
    setBulkCategoryId("");
  }

  async function handleBulkDelete() {
    if (!selectedDeletableEntries.length || selectedNonDeletableCount > 0) {
      return;
    }
    
    const confirmed = await confirm({
      title: "Confirmar Exclusão em Lote",
      message: `Deseja excluir permanentemente ${selectedDeletableEntries.length} lançamento(s) selecionado(s)? Esta ação não pode ser desfeita.`,
      confirmLabel: "Excluir Tudo",
      tone: "danger"
    });

    if (!confirmed) return;

    await onBulkDeleteEntries(selectedDeletableEntries.map((entry) => entry.id));
    setSelectedEntryIds([]);
    setBulkCategoryId("");
  }

  function openEntryModal() {
    setEditingId(null);
    setForm({ ...emptyForm });
    setShowEntryModal(true);
  }

  function openTransferModal() {
    setTransferForm(emptyTransferForm);
    setShowTransferModal(true);
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Financeiro"
          title="Lançamentos"
          description="Pagar, receber e consulta financeira do período."
        />
      )}

      <section className="section-toolbar-panel entries-top-panel">
        <div className="entries-toolbar-bar">
          <div className="entries-period-group" ref={periodPopoverRef}>
            <button
              aria-expanded={showPeriodPopover}
              aria-label="Selecionar período"
              className={`entries-period-trigger ${showPeriodPopover ? "is-active" : ""}`}
              onClick={() => {
                setShowPresetMenu(false);
                setShowPeriodPopover((current) => !current);
              }}
              type="button"
            >
              <CalendarRangeIcon />
              <span>{formatRangeLabel(String(filters.date_from ?? ""), String(filters.date_to ?? ""))}</span>
            </button>
            {showPeriodPopover && (
              <div className="entries-floating-panel entries-period-popover">
                <div className="entries-period-fields">
                  <label>
                    Início
                    <input
                      type="date"
                      value={String(filters.date_from ?? "")}
                      onChange={(event) => setDateRange(event.target.value, String(filters.date_to ?? ""))}
                    />
                  </label>
                  <label>
                    Fim
                    <input
                      type="date"
                      value={String(filters.date_to ?? "")}
                      onChange={(event) => setDateRange(String(filters.date_from ?? ""), event.target.value)}
                    />
                  </label>
                </div>
                <div className="entries-period-footer">
                  <button
                    className="secondary-button compact-button"
                    onClick={() => {
                      setDateRange("", "");
                      setShowPeriodPopover(false);
                    }}
                    type="button"
                  >
                    Limpar
                  </button>
                  <button
                    className="primary-button compact-button"
                    onClick={() => setShowPeriodPopover(false)}
                    type="button"
                  >
                    Concluir
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="entries-toolbar-icon-wrap" ref={presetMenuRef}>
            <button
              aria-expanded={showPresetMenu}
              aria-label="Filtros pré-definidos de data"
              className={`entries-toolbar-icon ${showPresetMenu ? "is-active" : ""}`}
              onClick={() => {
                setShowPeriodPopover(false);
                setShowPresetMenu((current) => !current);
              }}
              title="Períodos pré-definidos"
              type="button"
            >
              <FilterFunnelIcon />
            </button>
            {showPresetMenu && (
              <div className="entries-floating-panel entries-icon-menu">
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    applyPresetRange("today");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Hoje
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    applyPresetRange("current_month");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês atual
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    applyPresetRange("previous_month");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês anterior
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    applyPresetRange("current_year");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Ano atual
                </button>
              </div>
            )}
          </div>

          <label className="entries-toolbar-search">
            <input
              aria-label="Busca textual"
              placeholder="Buscar título, documento ou contraparte"
              value={String(filters.search ?? "")}
              onChange={(event) => onChangeFilters({ ...filters, search: event.target.value, page: "1" })}
            />
          </label>

          <div className="entries-quick-select-field">
            <Select
              closeMenuOnSelect={false}
              controlShouldRenderValue={false}
              hideSelectedOptions={false}
              inputId="entries-quick-filter"
              isMulti
              menuPortalTarget={portalTarget ?? undefined}
              onChange={applyQuickFilters}
              options={entryQuickFilterOptions}
              placeholder={quickFilterPlaceholder}
              styles={entryFilterSelectStyles}
              value={selectedQuickFilterOptions}
            />
          </div>

          <div className="entries-toolbar-icon-group">
            <button
              aria-label={showFilters ? "Ocultar filtros avançados" : "Mostrar filtros avançados"}
              className={`entries-toolbar-icon ${showFilters ? "is-active" : ""}`}
              onClick={() => setShowFilters((current) => !current)}
              title="Mais filtros"
              type="button"
            >
              <SlidersIcon />
              <span className="entries-toolbar-icon-label">Filtros</span>
            </button>

            <div className="entries-toolbar-icon-wrap" ref={bulkMenuRef}>
              <button
                aria-expanded={showBulkActions}
                aria-label="Ações em lote"
                className={`entries-toolbar-icon ${showBulkActions ? "is-active" : ""}`}
                onClick={() => setShowBulkActions((current) => !current)}
                title="Alterar categoria e exclusão em lote"
                type="button"
              >
                <StackEditIcon />
                <span className="entries-toolbar-icon-label">Lote</span>
              </button>
              {showBulkActions && (
                <div className="entries-floating-panel entries-bulk-panel">
                  <div className="entries-bulk-panel-header">
                    <strong>Ações em lote</strong>
                    {selectedEntryIds.length > 0 && <span>{selectedEntryIds.length} selecionado(s)</span>}
                  </div>
                  <div className="entries-bulk-panel-body">
                    <div className="bulk-entry-category">
                      <select
                        aria-label="Categoria para alteração em lote"
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
                    </div>
                    <div className="entries-bulk-panel-actions">
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
                  </div>
                </div>
              )}
            </div>

            <button
              aria-label="Transferir entre contas"
              className="entries-toolbar-icon"
              onClick={openTransferModal}
              title="Transferência"
              type="button"
            >
              <TransferIcon />
              <span className="entries-toolbar-icon-label">Transferir</span>
            </button>
            <button
              aria-label="Novo lançamento"
              className="entries-toolbar-icon entries-toolbar-icon-primary"
              onClick={openEntryModal}
              title="Novo lançamento"
              type="button"
            >
              <PlusSquareIcon />
              <span className="entries-toolbar-icon-label">Novo</span>
            </button>
          </div>
        </div>
      </section>
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

      <section className="panel compact-panel-card">
        <div className="panel-title is-column-mobile compact-title-row">
          <div>
            <h3>Lançamentos</h3>
            <p className="panel-subtitle">Consulta paginada com ordenação e filtro por categoria nos registros carregados na página.</p>
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
        <div className="table-shell entries-table-shell">
          <table className="erp-table entries-list-table">
            <colgroup>
              <col className="entries-col-select" />
              <col className="entries-col-title" />
              <col className="entries-col-flow" />
              <col className="entries-col-account" />
              <col className="entries-col-category" />
              <col className="entries-col-status" />
              <col className="entries-col-due-date" />
              <col className="entries-col-total" />
              <col className="entries-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th className="checkbox-cell">
                  <input
                    aria-label={allPageSelected ? "Desselecionar registros da página" : "Selecionar registros da página"}
                    checked={allPageSelected}
                    onChange={toggleAllPageEntries}
                    type="checkbox"
                  />
                </th>
                <th>{renderTableHeader(entryTableColumnLabels.title, "title")}</th>
                <th>{renderTableHeader(entryTableColumnLabels.flow, "flow")}</th>
                <th>{renderTableHeader(entryTableColumnLabels.account, "account")}</th>
                <th>{renderTableHeader(entryTableColumnLabels.category, "category")}</th>
                <th>{renderTableHeader(entryTableColumnLabels.status, "status")}</th>
                <th>{renderTableHeader(entryTableColumnLabels.due_date, "due_date")}</th>
                <th className="numeric-cell">{renderTableHeader(entryTableColumnLabels.total_amount, "total_amount", true)}</th>
                <th className="entries-actions-column">Ações</th>
              </tr>
            </thead>
            <tbody>
              {visibleEntries.map((entry, index) => (
                <tr className={index === focusedRowIndex ? "is-keyboard-focused" : ""} key={entry.id}>
                  <td className="checkbox-cell">
                    <input
                      checked={selectedEntryIds.includes(entry.id)}
                      onChange={() => toggleEntrySelection(entry.id)}
                      type="checkbox"
                    />
                  </td>
                  <td className="entries-cell-title">
                    <div className="cell-stack">
                      <strong>{entry.title}</strong>
                      <span>{entry.counterparty_name ?? entry.document_number ?? entry.source_system ?? "-"}</span>
                    </div>
                  </td>
                  <td>{formatEntryFlow(entry)}</td>
                  <td>{entry.account_name ?? "-"}</td>
                  <td className="entries-cell-category">
                    <div className="cell-stack">
                      <strong>{entry.category_name ?? "-"}</strong>
                    </div>
                  </td>
                  <td>{formatEntryStatus(entry.status)}</td>
                  <td>{formatDate(entry.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(entry.total_amount)}</td>
                  <td className="entries-row-actions-cell">
                    {!isTransferEntry(entry) ? (
                      <div className="entries-row-menu-wrap" ref={activeRowMenuId === entry.id ? rowMenuRef : undefined}>
                        <button
                          aria-expanded={activeRowMenuId === entry.id}
                          aria-label={`Ações do lançamento ${entry.title}`}
                          className="entries-row-menu-trigger"
                          onClick={() => setActiveRowMenuId((current) => (current === entry.id ? null : entry.id))}
                          type="button"
                        >
                          <MoreVerticalIcon />
                        </button>
                        {activeRowMenuId === entry.id && (
                          <div className="entries-row-menu">
                            <button
                              className="entries-row-menu-item"
                              onClick={() => {
                                setActiveRowMenuId(null);
                                startEditing(entry);
                              }}
                              type="button"
                            >
                              Editar
                            </button>
                            {entry.status !== "settled" ? (
                              <button
                                className="entries-row-menu-item"
                                onClick={() => {
                                  setActiveRowMenuId(null);
                                  void requestSettlement(entry);
                                }}
                                type="button"
                              >
                                Baixar
                              </button>
                            ) : (
                              <button
                                className="entries-row-menu-item"
                                onClick={() => {
                                  setActiveRowMenuId(null);
                                  void onReverseEntry(entry.id);
                                }}
                                type="button"
                              >
                                Estornar
                              </button>
                            )}
                            {canDeleteEntry(entry) && (
                              <button
                                className="entries-row-menu-item is-danger"
                                onClick={() => {
                                  setActiveRowMenuId(null);
                                  if (window.confirm("Excluir este lançamento em aberto?")) {
                                    void onDeleteEntry(entry.id);
                                  }
                                }}
                                type="button"
                              >
                                Excluir
                              </button>
                            )}
                            {!isPurchaseInvoiceEntry(entry) && (entry.status === "planned" || entry.status === "partial") && (
                              <button
                                className="entries-row-menu-item is-danger"
                                onClick={() => {
                                  setActiveRowMenuId(null);
                                  void onCancelEntry(entry.id);
                                }}
                                type="button"
                              >
                                Cancelar
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="entries-row-menu-placeholder">-</span>
                    )}
                  </td>
                </tr>
              ))}
              {!visibleEntries.length && (
                <tr>
                  <td colSpan={9}>
                    <div className="premium-empty-state">
                      <div className="empty-state-icon">
                        <svg aria-hidden="true" fill="none" height="32" viewBox="0 0 24 24" width="32">
                          <path d="M4 7h16M4 12h16M4 17h10" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
                        </svg>
                      </div>
                      <h4 className="empty-state-title">Nenhum lançamento encontrado</h4>
                      <p className="empty-state-desc">Tente ajustar seus filtros ou período de consulta para localizar os registros desejados.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr className="entries-total-row">
                <td colSpan={9}>
                  <div className="entries-total-summary">
                    <div>
                      <span>Total visível</span>
                      <strong>{formatMoney(visibleTotalAmount.toFixed(2))}</strong>
                    </div>
                    <div>
                      <span>Baixado visível</span>
                      <strong>{formatMoney(visiblePaidAmount.toFixed(2))}</strong>
                    </div>
                    <div>
                      <span>Em aberto visível</span>
                      <strong>{formatMoney(visibleOpenAmount)}</strong>
                    </div>
                    <div>
                      <span>Registros visíveis</span>
                      <strong>{visibleEntries.length}</strong>
                    </div>
                  </div>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
      {showEntryModal && (
        <div className="modal-backdrop">
          <div className="modal-card compact-entry-modal">
            <div className="panel-title compact-title-row">
              <h3>{editingId ? "Editar lançamento" : "Novo lançamento"}</h3>
              <ModalCloseButton
                onClick={() => {
                  setShowEntryModal(false);
                  setEditingId(null);
                  setForm(emptyForm);
                }}
              />
            </div>
            <form className="form-grid dense wide entry-form-grid" onSubmit={handleSubmit}>
              <label>Emissão<input autoFocus type="date" value={form.issue_date} onChange={(event) => setForm({ ...form, issue_date: event.target.value })} /></label>
              <label>Competência<input type="date" value={form.competence_date} onChange={(event) => setForm({ ...form, competence_date: event.target.value })} /></label>
              <label>Vencimento<input type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></label>
              <label>
                Status
                <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                  <option value="planned">Em aberto</option>
                  <option value="settled">Pago</option>
                </select>
              </label>
              <label>
                Tipo
                <select value={form.entry_type} onChange={(event) => setForm({ ...form, entry_type: event.target.value, category_id: "" })}>
                  <option value="expense">Despesa</option>
                  <option value="income">Receita</option>
                </select>
              </label>
              <label>Título<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Se vazio, usa a categoria" /></label>
              <label>
                Fornecedor {supplierRequired ? "*" : ""}
                <Select<EntryFormOption, false>
                  classNamePrefix="react-select"
                  inputId="entry-supplier"
                  isClearable={!supplierRequired}
                  menuPortalTarget={portalTarget ?? undefined}
                  onChange={(option: SingleValue<EntryFormOption>) => {
                    const supplier = sortedSuppliers.find((item) => item.id === option?.value);
                    setForm({
                      ...form,
                      supplier_id: option?.value ?? "",
                      counterparty_name: supplier?.name || "",
                    });
                  }}
                  options={supplierSelectOptions}
                  placeholder="Selecionar"
                  styles={entryFilterSelectStyles}
                  value={selectedSupplierOption}
                />
              </label>
              <label>
                Documento
                <input value={form.document_number} onChange={(event) => setForm({ ...form, document_number: event.target.value })} />
              </label>
              <label>
                Categoria
                <Select<EntryFormOption, false>
                  classNamePrefix="react-select"
                  inputId="entry-category"
                  isClearable
                  menuPortalTarget={portalTarget ?? undefined}
                  onChange={(option: SingleValue<EntryFormOption>) =>
                    setForm({ ...form, category_id: option?.value ?? "" })}
                  options={categorySelectOptions}
                  placeholder="Selecionar"
                  styles={entryFilterSelectStyles}
                  value={selectedCategoryOption}
                />
              </label>
              <label>
                Conta
                <select value={form.account_id} onChange={(event) => setForm({ ...form, account_id: event.target.value })} required>
                  <option value="">Selecionar</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <label className="amount-primary-field">Principal<MoneyInput value={form.principal_amount} onValueChange={(value) => setForm({ ...form, principal_amount: value })} /></label>
              <label>Juros<MoneyInput value={form.interest_amount} onValueChange={(value) => setForm({ ...form, interest_amount: value })} /></label>
              <label>Desconto<MoneyInput value={form.discount_amount} onValueChange={(value) => setForm({ ...form, discount_amount: value })} /></label>
              <label>Multa<MoneyInput value={form.penalty_amount} onValueChange={(value) => setForm({ ...form, penalty_amount: value })} /></label>
              <label>
                Total
                <input value={formatMoney(entryPreviewTotal)} disabled readOnly />
              </label>
              <label className="span-three entry-form-observation">Observação<textarea rows={4} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value, description: "" })} /></label>
              <div className="action-row">
                <button className={`primary-button ${submitting ? "is-loading" : ""}`} disabled={submitting} type="submit">{editingId ? "Salvar alterações" : "Criar lançamento"}</button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setShowEntryModal(false);
                    setEditingId(null);
                    setForm({ ...emptyForm });
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
              <ModalCloseButton
                onClick={() => {
                  setShowTransferModal(false);
                  setTransferForm(emptyTransferForm);
                }}
              />
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
              <label className="span-two">
                Descrição
                <textarea
                  rows={2}
                  value={transferForm.description}
                  onChange={(event) => setTransferForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>
              <div className="action-row">
                <button
                  className={`primary-button ${submitting ? "is-loading" : ""}`}
                  disabled={
                    submitting ||
                    !transferForm.source_account_id ||
                    !transferForm.destination_account_id ||
                    transferForm.source_account_id === transferForm.destination_account_id
                  }
                  type="submit"
                >
                  Salvar transferência
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
              <ModalCloseButton
                onClick={() => {
                  setShowSettlementPrompt(false);
                  setSettlementPrompt(emptySettlementPrompt);
                }}
              />
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
                <button className={`primary-button ${submitting ? "is-loading" : ""}`} disabled={submitting || !settlementPrompt.account_id} type="submit">
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

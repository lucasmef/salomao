import { useEffect, useMemo, useRef, useState } from "react";
import CreatableSelect from "react-select/creatable";

import { MoneyInput } from "../components/MoneyInput";
import { formatDate, formatMoney, normalizeDisplayText } from "../lib/format";
import { formatPtBrMoneyInput, normalizePtBrMoneyInput } from "../lib/money";
import type {
  Account,
  Category,
  FinancialEntry,
  FinancialEntryListResponse,
  ImportSummary,
  ReconciliationWorklist,
  Supplier,
} from "../types";

type ReconciliationFilters = {
  account_id: string;
  start: string;
  end: string;
};

type Props = {
  accounts: Account[];
  categories: Category[];
  suppliers: Supplier[];
  importSummary: ImportSummary;
  worklist: ReconciliationWorklist | null;
  filters: ReconciliationFilters;
  loading: boolean;
  submitting: boolean;
  onChangeFilters: (filters: ReconciliationFilters) => void;
  onApplyFilters: (filters?: ReconciliationFilters) => Promise<void>;
  onSyncInterStatement: () => Promise<void>;
  onReconcile: (
    bankTransactionIds: string[],
    financialEntryIds: string[],
    adjustments?: Record<string, string | null>,
  ) => Promise<void>;
  onUnreconcile: (bankTransactionId: string, deleteGeneratedEntries?: boolean) => Promise<void>;
  onQuickAction: (payload: Record<string, unknown>) => Promise<void>;
  onSearchEntries: (params: Record<string, string | boolean>) => Promise<FinancialEntryListResponse>;
  onCreateCategory?: (payload: Record<string, unknown>) => Promise<Category | void>;
  onCreateSupplier?: (payload: Record<string, unknown>) => Promise<Supplier>;
  embedded?: boolean;
};

type ModalState = "create" | "transfer" | null;

type CategoryCreationDraft = {
  name: string;
  report_group: string;
};

type CreateDraft = {
  category_id: string;
  supplier_id: string;
  title: string;
  notes: string;
  destination_account_id: string;
};

type ReconcileAdjustmentDraft = {
  principal_amount: string;
  interest_amount: string;
  discount_amount: string;
  penalty_amount: string;
};

const emptyDraft: CreateDraft = {
  category_id: "",
  supplier_id: "",
  title: "",
  notes: "",
  destination_account_id: "",
};

const emptyAdjustmentDraft: ReconcileAdjustmentDraft = {
  principal_amount: "",
  interest_amount: "",
  discount_amount: "",
  penalty_amount: "",
};

const emptyCategoryCreationDraft: CategoryCreationDraft = {
  name: "",
  report_group: "",
};

const RECONCILIATION_ENTRY_FETCH_LIMIT = 200;

function compactSingleLine(value: string | null | undefined, fallback = "-") {
  const normalized = normalizeDisplayText(value)?.replace(/\s+/g, " ").trim();
  return normalized || fallback;
}

function normalizeStatementKey(value: string | null | undefined) {
  return compactSingleLine(value, "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function limitStatementPreview(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function trimStatementDetail(detail: string, description: string) {
  const normalizedDetail = normalizeStatementKey(detail);
  const normalizedDescription = normalizeStatementKey(description);
  if (!normalizedDetail || normalizedDetail === normalizedDescription) {
    return "";
  }

  const escapedDescription = description.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const duplicateSuffixMatch = detail.match(new RegExp(`^(.+?)\\s*[:|-]\\s*["“]?${escapedDescription}["”]?$`, "i"));
  if (duplicateSuffixMatch?.[1]) {
    return compactSingleLine(duplicateSuffixMatch[1], "");
  }

  if (normalizedDetail.startsWith(normalizedDescription)) {
    return compactSingleLine(detail.slice(description.length).replace(/^[\s:|,-]+/, ""), "");
  }

  return detail;
}

function buildStatementCell(item: ReconciliationWorklist["items"][number]) {
  const memoParts = compactSingleLine(item.memo, "")
    .split("|")
    .map((part) => compactSingleLine(part, ""))
    .filter(Boolean);
  const description = compactSingleLine(item.name, "") || memoParts[0] || compactSingleLine(item.fit_id);
  const details = memoParts
    .map((part) => trimStatementDetail(part, description))
    .filter((part) => normalizeStatementKey(part) !== normalizeStatementKey(description));
  const fallbackDetails = !details.length ? trimStatementDetail(compactSingleLine(item.memo, ""), description) : "";
  const fullDetails = [...details, fallbackDetails].filter(Boolean).join(" | ");
  const tooltip = [description, fullDetails].filter(Boolean).join(" | ");

  return {
    description: limitStatementPreview(description, 52),
    details: fullDetails ? limitStatementPreview(fullDetails, 72) : "",
    tooltip: tooltip || undefined,
  };
}

function formatReconciliationAmount(value: string | number | null | undefined) {
  const numeric = Number(value ?? 0);
  const absolute = Math.abs(Number.isFinite(numeric) ? numeric : 0);
  const formatted = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(absolute);
  return numeric < 0 ? `- ${formatted}` : formatted;
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

function formatDecimalInput(value: string | number | null | undefined) {
  return formatPtBrMoneyInput(value);
}

function parseDecimalInput(value: string) {
  const numeric = Number(normalizePtBrMoneyInput(value));
  return Number.isFinite(numeric) ? numeric : 0;
}

function toApiDecimal(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return normalizePtBrMoneyInput(trimmed);
}

function buildGroupedEntryTitle(items: ReconciliationWorklist["items"], netAmount?: number) {
  if (!items.length) {
    return "";
  }

  const referenceAmount = typeof netAmount === "number" ? netAmount : Number(items[0].amount);
  const kind = referenceAmount >= 0 ? "Recebimento agrupado" : "Pagamento agrupado";
  return items.length > 1 ? `${kind} (${items.length} movimentos)` : compactSingleLine(items[0].name ?? items[0].memo ?? items[0].fit_id);
}

function buildGroupedEntryNotes(items: ReconciliationWorklist["items"]) {
  return items
    .map((item) =>
      [
        `${formatDate(item.posted_at)} | ${formatReconciliationAmount(item.amount)}`,
        compactSingleLine(item.name ?? item.memo ?? item.fit_id),
        compactSingleLine(item.memo ?? item.fit_id),
      ].join(" | "),
    )
    .join("\n");
}

function buildFinderAmountRange(item: ReconciliationWorklist["items"][number] | null) {
  if (!item) {
    return null;
  }

  const amount = Math.abs(Number(item.amount));
  if (!Number.isFinite(amount) || amount <= 0) {
    return null;
  }

  return {
    min: (amount * 0.99).toFixed(2),
    max: (amount * 1.1).toFixed(2),
  };
}

function SelectionIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <rect height="10" rx="2" stroke="currentColor" strokeWidth="1.4" width="10" x="3" y="3" />
      <path d="M5.5 8l1.6 1.6L10.7 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <path d="M13 5.25V2.75m0 0h-2.5m2.5 0-2.1 2.1a4.75 4.75 0 1 0 1.2 4.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function CalendarRangeIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M4 1.75a.75.75 0 0 1 1.5 0V3h5V1.75a.75.75 0 0 1 1.5 0V3h.75A2.25 2.25 0 0 1 15 5.25v7.5A2.25 2.25 0 0 1 12.75 15h-9.5A2.25 2.25 0 0 1 1 12.75v-7.5A2.25 2.25 0 0 1 3.25 3H4V1.75ZM2.5 6.5v6.25c0 .414.336.75.75.75h9.5a.75.75 0 0 0 .75-.75V6.5h-11Zm11-1.5v-.75a.75.75 0 0 0-.75-.75h-.75v.5a.75.75 0 0 1-1.5 0v-.5h-5v.5a.75.75 0 0 1-1.5 0v-.5h-.75a.75.75 0 0 0-.75.75V5h11Z" />
    </svg>
  );
}

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" />
    </svg>
  );
}

function TransferIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M3.22 5.03a.75.75 0 0 1 0-1.06l2-2a.75.75 0 1 1 1.06 1.06L5.56 3.75h6.69a.75.75 0 0 1 0 1.5H5.56l.72.72a.75.75 0 0 1-1.06 1.06l-2-2Zm9.56 5.94a.75.75 0 0 1 0 1.06l-2 2a.75.75 0 1 1-1.06-1.06l.72-.72H3.75a.75.75 0 0 1 0-1.5h6.69l-.72-.72a.75.75 0 0 1 1.06-1.06l2 2Z" />
    </svg>
  );
}

function PlusSquareIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M3.25 2A2.25 2.25 0 0 0 1 4.25v7.5A2.25 2.25 0 0 0 3.25 14h9.5A2.25 2.25 0 0 0 15 11.75v-7.5A2.25 2.25 0 0 0 12.75 2h-9.5ZM2.5 4.25a.75.75 0 0 1 .75-.75h9.5a.75.75 0 0 1 .75.75v7.5a.75.75 0 0 1-.75.75h-9.5a.75.75 0 0 1-.75-.75v-7.5ZM8 5a.75.75 0 0 1 .75.75v1.5h1.5a.75.75 0 0 1 0 1.5h-1.5v1.5a.75.75 0 0 1-1.5 0v-1.5h-1.5a.75.75 0 0 1 0-1.5h1.5v-1.5A.75.75 0 0 1 8 5Z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <circle cx="7" cy="7" r="4.75" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.5 10.5 14 14" stroke="currentColor" strokeLinecap="round" strokeWidth="1.4" />
    </svg>
  );
}

function CheckActionIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
      <path d="m5.25 8.15 1.7 1.7 3.8-4.1" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <path d="M5 4h8M5 8h8M5 12h8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.4" />
      <circle cx="2.5" cy="4" fill="currentColor" r="1" />
      <circle cx="2.5" cy="8" fill="currentColor" r="1" />
      <circle cx="2.5" cy="12" fill="currentColor" r="1" />
    </svg>
  );
}

function ChevronDownIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="14"
      viewBox="0 0 16 16"
      width="14"
      style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.16s ease" }}
    >
      <path d="m4 6 4 4 4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function PaidStatusIcon({ active }: { active: boolean }) {
  return (
    <span className={`reconciliation-status-indicator ${active ? "is-active" : ""}`} aria-label={active ? "Pago" : "Não pago"} title={active ? "Pago" : "Não pago"}>
      <svg aria-hidden="true" fill="none" height="12" viewBox="0 0 12 12" width="12">
        <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
        <path d="m3.7 6.2 1.5 1.5 3.1-3.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.2" />
      </svg>
    </span>
  );
}

function inferSupplierIdFromTexts(suppliers: Supplier[], texts: Array<string | null | undefined>) {
  const normalizedTexts = texts
    .map((value) =>
      (value ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toLowerCase(),
    )
    .filter(Boolean);

  if (!normalizedTexts.length) {
    return "";
  }

  let bestMatch: { id: string; score: number } | null = null;

  for (const supplier of suppliers) {
    const normalizedSupplier = supplier.name
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();

    if (!normalizedSupplier) {
      continue;
    }

    for (const text of normalizedTexts) {
      let score = 0;
      if (text === normalizedSupplier) {
        score = 1000;
      } else if (text.includes(normalizedSupplier)) {
        score = 700 + normalizedSupplier.length;
      } else if (normalizedSupplier.includes(text) && text.length >= 6) {
        score = 500 + text.length;
      }

      if (!bestMatch || score > bestMatch.score) {
        bestMatch = { id: supplier.id, score };
      }
    }
  }

  return bestMatch?.score ? bestMatch.id : "";
}

export function ReconciliationPage({
  accounts,
  categories,
  suppliers,
  importSummary,
  worklist,
  filters,
  loading,
  submitting,
  onChangeFilters,
  onApplyFilters,
  onSyncInterStatement,
  onReconcile,
  onUnreconcile,
  onQuickAction,
  onSearchEntries,
  onCreateCategory,
  onCreateSupplier,
  embedded = false,
}: Props) {
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);
  const balancePopoverRef = useRef<HTMLDivElement | null>(null);
  const [selectedBankIds, setSelectedBankIds] = useState<string[]>([]);
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const [bankSearch, setBankSearch] = useState("");
  const [hideMatchedBankItems, setHideMatchedBankItems] = useState(true);
  const [bankDirectionFilter, setBankDirectionFilter] = useState("all");
  const [entryRows, setEntryRows] = useState<FinancialEntry[]>([]);
  const [entryTotal, setEntryTotal] = useState(0);
  const [entryLoading, setEntryLoading] = useState(false);
  const [entrySearch, setEntrySearch] = useState("");
  const [entryStatus, setEntryStatus] = useState("");
  const [finderModeActive, setFinderModeActive] = useState(false);
  const [finderSnapshot, setFinderSnapshot] = useState<{
    search: string;
    status: string;
  } | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [createDraft, setCreateDraft] = useState<CreateDraft>(emptyDraft);
  const [reconcileAdjustmentDraft, setReconcileAdjustmentDraft] = useState<ReconcileAdjustmentDraft>(emptyAdjustmentDraft);
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [creatingSupplier, setCreatingSupplier] = useState(false);
  const [categoryCreationModalOpen, setCategoryCreationModalOpen] = useState(false);
  const [categoryCreationDraft, setCategoryCreationDraft] = useState<CategoryCreationDraft>(emptyCategoryCreationDraft);
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);
  const [showBalancePopover, setShowBalancePopover] = useState(false);
  const hasMountedFilterAutoApplyRef = useRef(false);
  const entryRequestIdRef = useRef(0);

  const filteredBankItems = useMemo(() => {
    const query = bankSearch.trim().toLowerCase();
    const items = worklist?.items ?? [];
    return items.filter((item) => {
      if (hideMatchedBankItems && item.reconciliation_status === "matched") {
        return false;
      }

      if (bankDirectionFilter === "in" && Number(item.amount) < 0) {
        return false;
      }

      if (bankDirectionFilter === "out" && Number(item.amount) > 0) {
        return false;
      }

      if (!query) {
        return true;
      }

      return [item.name, item.memo, item.fit_id]
        .filter(Boolean)
        .some((value) => compactSingleLine(String(value)).toLowerCase().includes(query));
    });
  }, [bankDirectionFilter, bankSearch, hideMatchedBankItems, worklist]);

  const selectedBankItems = useMemo(
    () => (worklist?.items ?? []).filter((item) => selectedBankIds.includes(item.bank_transaction_id)),
    [selectedBankIds, worklist],
  );

  const selectedBankNetAmount = selectedBankItems.reduce((total, item) => total + Number(item.amount), 0);
  const selectedBankTotal = Math.abs(selectedBankNetAmount);
  const selectedBankGrossAmount = selectedBankItems.reduce((total, item) => total + Math.abs(Number(item.amount)), 0);
  const overallPendingCount = worklist?.overall_unreconciled_count ?? 0;
  const selectableFilteredBankIds = useMemo(
    () =>
      filteredBankItems
        .filter((item) => item.reconciliation_status !== "matched")
        .map((item) => item.bank_transaction_id),
    [filteredBankItems],
  );
  const allFilteredBankSelected = selectableFilteredBankIds.length > 0
    && selectableFilteredBankIds.every((id) => selectedBankIds.includes(id));
  const hasInterApiAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const ofxAccounts = useMemo(
    () => accounts.filter((account) => account.is_active && account.import_ofx_enabled),
    [accounts],
  );

  const selectedEntryRows = entryRows.filter((entry) => selectedEntryIds.includes(entry.id));
  const selectableEntryIds = useMemo(
    () => entryRows.filter((entry) => canSelectEntry(entry)).map((entry) => entry.id),
    [entryRows],
  );
  const allVisibleEntriesSelected = selectableEntryIds.length > 0
    && selectableEntryIds.every((id) => selectedEntryIds.includes(id));
  const selectedEntryTotal = selectedEntryRows.reduce(
    (total, entry) => total + Number(entry.total_amount),
    0,
  );
  const selectedReconciliationEntry = selectedEntryRows.length === 1 ? selectedEntryRows[0] : null;
  const selectedReconciliationTransaction = selectedBankItems.length === 1 ? selectedBankItems[0] : null;
  const adjustmentPreviewTotal =
    parseDecimalInput(reconcileAdjustmentDraft.principal_amount)
    + parseDecimalInput(reconcileAdjustmentDraft.interest_amount)
    + parseDecimalInput(reconcileAdjustmentDraft.penalty_amount)
    - parseDecimalInput(reconcileAdjustmentDraft.discount_amount);
  const currentReconciliationDifference =
    selectedReconciliationTransaction && selectedReconciliationEntry
      ? Math.abs(Number(selectedReconciliationTransaction.amount)) - Number(selectedReconciliationEntry.total_amount)
      : 0;
  const adjustedReconciliationDifference =
    selectedReconciliationTransaction && selectedReconciliationEntry
      ? Math.abs(Number(selectedReconciliationTransaction.amount)) - adjustmentPreviewTotal
      : 0;

  const consolidatedEntryKind = useMemo(() => {
    if (!selectedBankItems.length || Math.abs(selectedBankNetAmount) < 0.0001) {
      return null;
    }
    return selectedBankNetAmount >= 0 ? "income" : "expense";
  }, [selectedBankItems, selectedBankNetAmount]);
  const selectedBankAccountCount = useMemo(
    () => new Set(selectedBankItems.map((item) => item.account_id).filter(Boolean)).size,
    [selectedBankItems],
  );
  const selectedBankDirectionCount = useMemo(
    () => new Set(selectedBankItems.map((item) => (Number(item.amount) >= 0 ? "in" : "out"))).size,
    [selectedBankItems],
  );
  const createEntryValidationMessage = useMemo(() => {
    if (!selectedBankItems.length) {
      return "";
    }
    if (Math.abs(selectedBankNetAmount) < 0.0001) {
      return "Os movimentos selecionados resultam em valor liquido zero.";
    }
    if (selectedBankAccountCount > 1) {
      return "Selecione apenas movimentos da mesma conta para criar um lançamento consolidado.";
    }
    if (selectedBankDirectionCount > 1) {
      return "Selecione apenas entradas ou apenas saídas para criar um lançamento consolidado.";
    }
    return "";
  }, [selectedBankAccountCount, selectedBankDirectionCount, selectedBankItems, selectedBankNetAmount]);
  const selectedTransferItem = selectedBankItems[0] ?? null;
  const transferIsIncoming = selectedBankItems.length ? selectedBankNetAmount >= 0 : true;
  const selectedTransferAccountName = useMemo(() => {
    const accountNames = [...new Set(selectedBankItems.map((item) => compactSingleLine(item.account_name)).filter((value) => value !== "-"))];
    if (!accountNames.length) {
      return "Conta do movimento selecionado";
    }
    if (accountNames.length === 1) {
      return accountNames[0];
    }
    return "Multiplas contas selecionadas";
  }, [selectedBankItems]);
  const transferFixedAccountLabel = transferIsIncoming ? "Conta de destino (extrato)" : "Conta de origem (extrato)";
  const transferSelectableAccountLabel = transferIsIncoming ? "Conta de origem" : "Conta de destino";

  const availableCategories = useMemo(() => {
    const eligible = categories.filter((category) => {
      if (category.entry_kind === "transfer") {
        return false;
      }
      if (!consolidatedEntryKind) {
        return true;
      }
      return category.entry_kind === consolidatedEntryKind;
    });

    return eligible.sort((left, right) => compactSingleLine(left.name).localeCompare(compactSingleLine(right.name), "pt-BR"));
  }, [categories, consolidatedEntryKind]);
  const categoryOptions = useMemo(
    () =>
      availableCategories.map((category) => ({
        value: category.id,
        label: category.name,
      })),
    [availableCategories],
  );
  const selectedCategoryOption = useMemo(
    () => categoryOptions.find((option) => option.value === createDraft.category_id) ?? null,
    [categoryOptions, createDraft.category_id],
  );
  const categoryGroupOptions = useMemo(() => {
    if (!consolidatedEntryKind) {
      return [];
    }
    return [...new Set(
      categories
        .filter((category) => category.entry_kind === consolidatedEntryKind)
        .map((category) => (category.report_group ?? "").trim())
        .filter(Boolean),
    )].sort((left, right) => left.localeCompare(right, "pt-BR"));
  }, [categories, consolidatedEntryKind]);
  const categorySelectStyles = useMemo(
    () => ({
      control: (base: Record<string, unknown>, state: { isFocused: boolean }) => ({
        ...base,
        minHeight: 32,
        borderRadius: 10,
        borderColor: state.isFocused ? "#2f5be7" : "#cfd9e8",
        boxShadow: "none",
        fontSize: "0.82rem",
      }),
      valueContainer: (base: Record<string, unknown>) => ({
        ...base,
        padding: "0 10px",
      }),
      input: (base: Record<string, unknown>) => ({
        ...base,
        margin: 0,
        padding: 0,
      }),
      indicatorsContainer: (base: Record<string, unknown>) => ({
        ...base,
        minHeight: 30,
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
    }),
    [],
  );
  const sortedSuppliers = useMemo(
    () => [...suppliers].sort((left, right) => compactSingleLine(left.name, "").localeCompare(compactSingleLine(right.name, ""), "pt-BR")),
    [suppliers],
  );
  const supplierOptions = useMemo(
    () =>
      sortedSuppliers.map((supplier) => ({
        value: supplier.id,
        label: supplier.name,
      })),
    [sortedSuppliers],
  );
  const selectedSupplierOption = useMemo(
    () => supplierOptions.find((option) => option.value === createDraft.supplier_id) ?? null,
    [supplierOptions, createDraft.supplier_id],
  );
  const selectedCreateCategory = useMemo(
    () => categories.find((item) => item.id === createDraft.category_id) ?? null,
    [categories, createDraft.category_id],
  );
  const supplierRequired = useMemo(() => {
    if (!selectedCreateCategory || consolidatedEntryKind !== "expense") {
      return false;
    }
    const normalizedGroup = normalizeText(selectedCreateCategory.report_group ?? "");
    const normalizedName = normalizeText(selectedCreateCategory.name);
    return normalizedGroup.includes("compr") || normalizedName.includes("compra");
  }, [consolidatedEntryKind, selectedCreateCategory]);
  const canCreateConsolidatedEntry =
    !createEntryValidationMessage &&
    Boolean(createDraft.category_id) &&
    Boolean(selectedBankIds.length) &&
    Boolean(consolidatedEntryKind) &&
    (!supplierRequired || Boolean(createDraft.supplier_id));
  const transferSelectableAccounts = useMemo(() => {
    if (!selectedTransferItem) {
      return accounts;
    }
    return accounts.filter((account) => account.id !== selectedTransferItem.account_id);
  }, [accounts, selectedTransferItem]);
  const inferredSupplierId = useMemo(
    () =>
      inferSupplierIdFromTexts(
        sortedSuppliers,
        selectedBankItems.flatMap((item) => [item.name, item.memo]).concat(createDraft.title),
      ),
    [createDraft.title, selectedBankItems, sortedSuppliers],
  );

  function normalizeText(value: string) {
    return value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function setDateRange(start: string, end: string) {
    onChangeFilters({ ...filters, start, end });
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
      setDateRange(formatValue(new Date(year, month, 1)), formatValue(new Date(year, month + 1, 0)));
      return;
    }

    if (kind === "previous_month") {
      setDateRange(formatValue(new Date(year, month - 1, 1)), formatValue(new Date(year, month, 0)));
      return;
    }

    setDateRange(formatValue(new Date(year, 0, 1)), formatValue(new Date(year, 11, 31)));
  }

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
      if (showPresetMenu && presetMenuRef.current && !presetMenuRef.current.contains(target)) {
        setShowPresetMenu(false);
      }
      if (showBalancePopover && balancePopoverRef.current && !balancePopoverRef.current.contains(target)) {
        setShowBalancePopover(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showBalancePopover, showPeriodPopover, showPresetMenu]);

  useEffect(() => {
    setSelectedBankIds([]);
    setSelectedEntryIds([]);
    setBankSearch("");
  }, [worklist]);

  useEffect(() => {
    if (!hasMountedFilterAutoApplyRef.current) {
      hasMountedFilterAutoApplyRef.current = true;
      return;
    }
    void onApplyFilters(filters);
  }, [filters.account_id, filters.end, filters.start]);

  useEffect(() => {
    if (!finderModeActive || selectedBankItems.length !== 1) {
      return;
    }

    setSelectedEntryIds([]);
    setEntrySearch("");
    setEntryStatus("open");
  }, [finderModeActive, selectedBankItems]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadPeriodEntries(entrySearch, entryStatus);
    }, 220);

    return () => window.clearTimeout(timeoutId);
  }, [entrySearch, entryStatus, filters.end, filters.start, finderModeActive, selectedBankItems]);

  useEffect(() => {
    if (!supplierRequired || createDraft.supplier_id || !inferredSupplierId) {
      return;
    }
    setCreateDraft((current) => ({ ...current, supplier_id: inferredSupplierId }));
  }, [createDraft.supplier_id, inferredSupplierId, supplierRequired]);

  useEffect(() => {
    if (!selectedReconciliationEntry || !selectedReconciliationTransaction) {
      setReconcileAdjustmentDraft(emptyAdjustmentDraft);
      return;
    }
    setReconcileAdjustmentDraft({
      principal_amount: formatDecimalInput(selectedReconciliationEntry.principal_amount),
      interest_amount: formatDecimalInput(selectedReconciliationEntry.interest_amount),
      discount_amount: formatDecimalInput(selectedReconciliationEntry.discount_amount),
      penalty_amount: formatDecimalInput(selectedReconciliationEntry.penalty_amount),
    });
  }, [selectedReconciliationEntry, selectedReconciliationTransaction]);

  async function loadPeriodEntries(search = entrySearch, status = entryStatus) {
    const requestId = entryRequestIdRef.current + 1;
    entryRequestIdRef.current = requestId;
    setEntryLoading(true);
    try {
      const finderRange =
        finderModeActive && selectedBankItems.length === 1
          ? buildFinderAmountRange(selectedBankItems[0])
          : null;
      const response = await onSearchEntries({
        date_from: filters.start,
        date_to: filters.end,
        status,
        search,
        amount_min: finderRange?.min ?? "",
        amount_max: finderRange?.max ?? "",
        page: "1",
        page_size: String(RECONCILIATION_ENTRY_FETCH_LIMIT),
      });
      if (entryRequestIdRef.current === requestId) {
        setEntryRows(response.items);
        setEntryTotal(response.total);
      }
    } finally {
      if (entryRequestIdRef.current === requestId) {
        setEntryLoading(false);
      }
    }
  }

  function toggleBankSelection(bankTransactionId: string) {
    setSelectedBankIds((current) =>
      current.includes(bankTransactionId)
        ? current.filter((item) => item !== bankTransactionId)
        : [...current, bankTransactionId],
    );
  }

  function toggleEntrySelection(entryId: string) {
    setSelectedEntryIds((current) =>
      current.includes(entryId)
        ? current.filter((item) => item !== entryId)
        : [...current, entryId],
    );
  }

  async function handleBulkReconcile() {
    const adjustments =
      selectedReconciliationEntry && selectedReconciliationTransaction
        ? {
            principal_amount: toApiDecimal(reconcileAdjustmentDraft.principal_amount),
            interest_amount: toApiDecimal(reconcileAdjustmentDraft.interest_amount),
            discount_amount: toApiDecimal(reconcileAdjustmentDraft.discount_amount),
            penalty_amount: toApiDecimal(reconcileAdjustmentDraft.penalty_amount),
          }
        : undefined;
    await onReconcile(selectedBankIds, selectedEntryIds, adjustments);
    setSelectedBankIds([]);
    setSelectedEntryIds([]);
    setReconcileAdjustmentDraft(emptyAdjustmentDraft);
    await loadPeriodEntries();
  }

  async function handleUnreconcile(bankTransactionId: string, undoMode: string | null) {
    const needsDeleteConfirmation = undoMode === "delete_entry" || undoMode === "mixed";
    if (needsDeleteConfirmation) {
      const confirmed = window.confirm(
        "Esta desconciliação vai excluir o lançamento criado na conciliação e reabrir as faturas vinculadas. Deseja continuar?",
      );
      if (!confirmed) {
        return;
      }
    }

    await onUnreconcile(bankTransactionId, needsDeleteConfirmation);
    setSelectedBankIds((current) => current.filter((item) => item !== bankTransactionId));
    setSelectedEntryIds([]);
    await loadPeriodEntries();
  }

  async function toggleFinderMode() {
    if (finderModeActive) {
      const snapshot = finderSnapshot ?? { search: "", status: "" };
      setFinderModeActive(false);
      setFinderSnapshot(null);
      setEntrySearch(snapshot.search);
      setEntryStatus(snapshot.status);
      setSelectedEntryIds([]);
      return;
    }

    setFinderSnapshot({
      search: entrySearch,
      status: entryStatus,
    });
    setFinderModeActive(true);
  }

  function useBankAmountAsPrincipal() {
    if (!selectedReconciliationTransaction) {
      return;
    }
    setReconcileAdjustmentDraft({
      principal_amount: formatDecimalInput(Math.abs(Number(selectedReconciliationTransaction.amount))),
      interest_amount: "0,00",
      discount_amount: "0,00",
      penalty_amount: "0,00",
    });
  }

  async function handleCreateEntry() {
    if (!canCreateConsolidatedEntry) {
      return;
    }
    await onQuickAction({
      bank_transaction_ids: selectedBankIds,
      action_type: "create_entry",
      category_id: createDraft.category_id || null,
      supplier_id: createDraft.supplier_id || null,
      title: createDraft.title || null,
      notes: createDraft.notes || null,
      destination_account_id: createDraft.destination_account_id || null,
    });
    setCreateDraft(emptyDraft);
    setModal(null);
    setSelectedBankIds([]);
    await loadPeriodEntries();
  }

  async function handleCreateCategory(inputValue: string) {
    if (!onCreateCategory || !consolidatedEntryKind) {
      return;
    }
    const trimmedName = inputValue.trim();
    if (!trimmedName) {
      return;
    }
    setCategoryCreationDraft({
      name: trimmedName,
      report_group: categoryGroupOptions[0] ?? "",
    });
    setCategoryCreationModalOpen(true);
  }

  async function confirmCategoryCreation() {
    if (!onCreateCategory || !consolidatedEntryKind) {
      return;
    }
    const trimmedName = categoryCreationDraft.name.trim();
    const trimmedGroup = categoryCreationDraft.report_group.trim();
    if (!trimmedName || !trimmedGroup) {
      return;
    }

    setCreatingCategory(true);
    try {
      const createdCategory = await onCreateCategory({
        code: null,
        name: trimmedName,
        entry_kind: consolidatedEntryKind,
        report_group: trimmedGroup,
        is_financial_expense: false,
        is_active: true,
      });

      if (createdCategory?.id) {
        setCreateDraft((current) => ({ ...current, category_id: createdCategory.id }));
      }
      setCategoryCreationModalOpen(false);
      setCategoryCreationDraft(emptyCategoryCreationDraft);
    } finally {
      setCreatingCategory(false);
    }
  }

  async function handleInlineSupplierCreate(inputValue: string) {
    if (!onCreateSupplier) {
      return;
    }
    const cleanName = inputValue.trim();
    if (!cleanName) {
      return;
    }
    const existing = sortedSuppliers.find((item) => normalizeText(item.name) === normalizeText(cleanName));
    if (existing) {
      setCreateDraft((current) => ({ ...current, supplier_id: existing.id }));
      return;
    }
    setCreatingSupplier(true);
    try {
      const supplier = await onCreateSupplier({
        name: cleanName,
        document_number: null,
        default_payment_term: null,
        payment_basis: "delivery",
        notes: null,
        is_active: true,
      });
      setCreateDraft((current) => ({ ...current, supplier_id: supplier.id }));
    } finally {
      setCreatingSupplier(false);
    }
  }

  async function handleCreateTransfer() {
    await onQuickAction({
      bank_transaction_ids: selectedBankIds,
      action_type: "mark_transfer",
      destination_account_id: createDraft.destination_account_id || null,
      title: createDraft.title || null,
      notes: createDraft.notes || null,
    });
    setCreateDraft(emptyDraft);
    setModal(null);
    setSelectedBankIds([]);
    await loadPeriodEntries();
  }

  function canSelectEntry(entry: FinancialEntry) {
    return entry.status === "planned" || entry.status === "partial";
  }

  function toggleAllFilteredBankItems() {
    setSelectedBankIds(allFilteredBankSelected ? [] : selectableFilteredBankIds);
  }

  function toggleAllVisibleEntries() {
    setSelectedEntryIds(allVisibleEntriesSelected ? [] : selectableEntryIds);
  }

  function openCreateModal() {
    const inferredSupplier = inferSupplierIdFromTexts(
      sortedSuppliers,
      selectedBankItems.flatMap((item) => [item.name, item.memo]),
    );
    setCreateDraft((current) => ({
      ...current,
      supplier_id: inferredSupplier,
      title: buildGroupedEntryTitle(selectedBankItems, selectedBankNetAmount),
      notes: buildGroupedEntryNotes(selectedBankItems),
      destination_account_id: "",
    }));
    setModal("create");
  }

  function openTransferModal() {
    setCreateDraft((current) => ({
      ...current,
      title: buildGroupedEntryTitle(selectedBankItems, selectedBankNetAmount) || "Transferência entre contas",
      notes: buildGroupedEntryNotes(selectedBankItems),
      destination_account_id: "",
    }));
    setModal("transfer");
  }

  const reconciliationFiltersContent = (
    <div className="reconciliation-top-toolbar">
      <select
        aria-label="Conta do extrato"
        className="reconciliation-top-select"
        value={filters.account_id}
        onChange={(event) => onChangeFilters({ ...filters, account_id: event.target.value })}
        disabled={!ofxAccounts.length}
      >
        {!ofxAccounts.length && <option value="">Nenhuma conta OFX</option>}
        {ofxAccounts.map((account) => (
          <option key={account.id} value={account.id}>
            {account.name}
          </option>
        ))}
      </select>
      <div className="entries-period-group reconciliation-period-group" ref={periodPopoverRef}>
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
          <span>{formatRangeLabel(filters.start, filters.end)}</span>
        </button>
        {showPeriodPopover && (
          <div className="entries-floating-panel entries-period-popover">
            <div className="entries-period-fields">
              <label>
                Início
                <input type="date" value={filters.start} onChange={(event) => setDateRange(event.target.value, filters.end)} />
              </label>
              <label>
                Fim
                <input type="date" value={filters.end} onChange={(event) => setDateRange(filters.start, event.target.value)} />
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
              <button className="primary-button compact-button" onClick={() => setShowPeriodPopover(false)} type="button">
                Concluir
              </button>
            </div>
          </div>
        )}
      </div>
      <div className="entries-toolbar-icon-wrap" ref={presetMenuRef}>
        <button
          aria-expanded={showPresetMenu}
          aria-label="Períodos pré-definidos"
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
            <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("today"); setShowPresetMenu(false); }} type="button">Hoje</button>
            <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("current_month"); setShowPresetMenu(false); }} type="button">Mês atual</button>
            <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("previous_month"); setShowPresetMenu(false); }} type="button">Mês anterior</button>
            <button className="entries-icon-menu-item" onClick={() => { applyPresetRange("current_year"); setShowPresetMenu(false); }} type="button">Ano atual</button>
          </div>
        )}
      </div>
      <div className="reconciliation-inline-meta">
        <span className="reconciliation-import-meta">
          Pendentes: <strong>{overallPendingCount}</strong> Último lançamento importado: {importSummary.latest_ofx_transaction_date ? formatDate(importSummary.latest_ofx_transaction_date) : "nenhum"}
        </span>
        <div className="reconciliation-balance-wrap" ref={balancePopoverRef}>
          <button
            aria-expanded={showBalancePopover}
            className={`reconciliation-balance-trigger ${showBalancePopover ? "is-active" : ""}`}
            onClick={() => setShowBalancePopover((current) => !current)}
            type="button"
          >
            <span>Saldo total</span>
            <strong>{formatMoney(worklist?.total_account_balance ?? 0)}</strong>
            <ChevronDownIcon expanded={showBalancePopover} />
          </button>
          {showBalancePopover && (
            <div className="reconciliation-balance-popover">
              {(worklist?.account_balances ?? []).map((account) => (
                <div className="reconciliation-balance-row" key={account.account_id}>
                  <span title={compactSingleLine(account.account_name)}>{compactSingleLine(account.account_name)}</span>
                  <strong>{formatMoney(account.current_balance)}</strong>
                </div>
              ))}
              {!worklist?.account_balances?.length && (
                <div className="reconciliation-balance-empty">Nenhum saldo disponível.</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
  return (
    <div className="page-layout">
      {!embedded && (
        <section className="page-header">
          <div>
            <p className="section-label">Conciliação</p>
            <h2>Extrato bancário x lançamentos do sistema</h2>
          </div>
          {reconciliationFiltersContent}
        </section>
      )}

      {embedded && (
        <section className="section-toolbar-panel reconciliation-filter-panel">
          {reconciliationFiltersContent}
        </section>
      )}

      <section className="reconciliation-erp-grid">
        <article className="panel reconciliation-panel">
          <div className="panel-title reconciliation-panel-title">
            <div className="reconciliation-panel-heading">
              <h3>Extrato</h3>
              <div className="reconciliation-panel-inline-filters">
                <input aria-label="Buscar no extrato" placeholder="Buscar no extrato" value={bankSearch} onChange={(event) => setBankSearch(event.target.value)} />
                <select aria-label="Tipo do extrato" value={bankDirectionFilter} onChange={(event) => setBankDirectionFilter(event.target.value)}>
                  <option value="all">Todos</option>
                  <option value="in">Entradas</option>
                  <option value="out">Saídas</option>
                </select>
              </div>
            </div>
            <div className="panel-mini-actions reconciliation-panel-icon-actions">
              <button
                aria-label={hideMatchedBankItems ? "Mostrar conciliados" : "Ocultar conciliados"}
                className={`entries-toolbar-icon ${hideMatchedBankItems ? "is-active" : ""}`}
                onClick={() => setHideMatchedBankItems((current) => !current)}
                title={hideMatchedBankItems ? "Mostrar conciliados" : "Ocultar conciliados"}
                type="button"
              >
                <ListIcon />
              </button>
              <button className="entries-toolbar-icon" disabled={submitting || !hasInterApiAccount} onClick={() => void onSyncInterStatement()} title="Atualizar extrato do Inter" type="button">
                <RefreshIcon />
              </button>
              <button aria-label="Nova transferência" className="entries-toolbar-icon" disabled={!selectedBankIds.length} onClick={openTransferModal} title="Nova transferência" type="button">
                <TransferIcon />
              </button>
              <button aria-label="Novo lançamento" className="entries-toolbar-icon" disabled={!selectedBankIds.length} onClick={openCreateModal} title="Novo lançamento" type="button">
                <PlusSquareIcon />
              </button>
            </div>
          </div>
          <div className="table-shell tall compact-table-shell">
            <table className="erp-table compact-table reconciliation-bank-table">
              <thead>
                <tr>
                  <th className="checkbox-cell">
                    <input
                      aria-label={allFilteredBankSelected ? "Desselecionar extrato visível" : "Selecionar extrato visível"}
                      checked={allFilteredBankSelected}
                      disabled={!selectableFilteredBankIds.length}
                      onChange={toggleAllFilteredBankItems}
                      type="checkbox"
                    />
                  </th>
                  <th>Data</th>
                  <th>Extrato</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {filteredBankItems.map((item) => {
                  const isMatched = item.reconciliation_status === "matched";
                  const entryTitles = item.applied_entries.map((entry) => compactSingleLine(entry.title)).join(", ");
                  const statementCell = buildStatementCell(item);
                  return (
                    <tr key={item.bank_transaction_id}>
                      <td className="checkbox-cell">
                        <input
                          type="checkbox"
                          checked={selectedBankIds.includes(item.bank_transaction_id)}
                          disabled={isMatched}
                          onChange={() => toggleBankSelection(item.bank_transaction_id)}
                        />
                      </td>
                      <td>{formatDate(item.posted_at)}</td>
                      <td title={statementCell.tooltip}>
                        <div className="reconciliation-cell-stack">
                          <span className="single-line-cell">{statementCell.description}</span>
                          {statementCell.details ? <span className="compact-detail-line reconciliation-statement-detail">{statementCell.details}</span> : null}
                        </div>
                      </td>
                      <td className="numeric-cell compact-amount-cell">{formatReconciliationAmount(item.amount)}</td>
                      <td title={entryTitles || undefined}>
                        <div className="reconciliation-inline-status">
                          <span className="single-line-cell">{isMatched ? "Conciliado" : "Pendente"}</span>
                          {isMatched && (
                            <button className="text-action-button reconciliation-inline-link" type="button" onClick={() => void handleUnreconcile(item.bank_transaction_id, item.undo_mode)}>
                              Desconciliar
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!filteredBankItems.length && (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      Nenhum movimento encontrado para o periodo.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="table-footer reconciliation-table-footer reconciliation-table-footer-simple">
            <div className="table-footer-meta">
              <span>{filteredBankItems.length} item(ns) no extrato filtrado</span>
            </div>
          </div>
        </article>

        <article className="panel reconciliation-panel">
          <div className="panel-title reconciliation-panel-title">
            <div className="reconciliation-panel-heading">
              <h3>Lançamentos</h3>
              <div className="reconciliation-panel-inline-filters">
                <input aria-label="Buscar lançamentos" placeholder="Buscar lançamentos" value={entrySearch} onChange={(event) => setEntrySearch(event.target.value)} />
                <select aria-label="Status dos lançamentos" value={entryStatus} onChange={(event) => setEntryStatus(event.target.value)}>
                  <option value="">Todos</option>
                  <option value="open">Em aberto</option>
                  <option value="settled">Pago</option>
                </select>
              </div>
            </div>
            <div className="panel-mini-actions reconciliation-panel-icon-actions">
              <button
                aria-label={finderModeActive ? "Busca por extrato ativa" : "Encontrar fatura"}
                className={`entries-toolbar-icon ${finderModeActive ? "is-active" : ""}`}
                type="button"
                onClick={() => void toggleFinderMode()}
                title={finderModeActive ? "Busca por extrato ativa" : "Encontrar fatura"}
              >
                <SearchIcon />
              </button>
              <button
                aria-label="Conciliar lançamentos"
                className="entries-toolbar-icon entries-toolbar-icon-primary"
                type="button"
                disabled={!selectedBankIds.length || !selectedEntryIds.length || loading}
                onClick={() => void handleBulkReconcile()}
                title="Conciliar lançamentos"
              >
                <CheckActionIcon />
              </button>
            </div>
          </div>
          {selectedReconciliationEntry && selectedReconciliationTransaction && (
            <div className="inline-adjustment-panel">
              <div className="inline-adjustment-header">
                <strong>Ajuste da baixa</strong>
                <div className="inline-adjustment-summary">
                  <span className="compact-muted">
                    Extrato {formatMoney(Math.abs(Number(selectedReconciliationTransaction.amount)))} | Valor atual{" "}
                      {formatMoney(Number(selectedReconciliationEntry.total_amount))}
                      {" "} | Total após ajuste {formatMoney(adjustmentPreviewTotal)}
                  </span>
                  <button className="secondary-button compact-inline-button" type="button" onClick={useBankAmountAsPrincipal}>
                    Usar valor do extrato
                  </button>
                </div>
              </div>
              <div className="inline-adjustment-selection-metrics">
                <div className="inline-adjustment-metric">
                  <span>Extrato selecionado</span>
                  <strong>{formatMoney(selectedBankTotal)}</strong>
                </div>
                <div className="inline-adjustment-metric">
                  <span>Lançamentos selecionados</span>
                  <strong>{formatMoney(selectedEntryTotal)}</strong>
                </div>
              </div>
              <div className="inline-adjustment-difference">
                <span>
                  Diferença atual: <strong>{formatMoney(currentReconciliationDifference)}</strong>
                </span>
                <span>
                  Diferença após ajuste: <strong>{formatMoney(adjustedReconciliationDifference)}</strong>
                </span>
              </div>
              <div className="inline-adjustment-grid">
                <label>
                  Principal
                  <MoneyInput
                    value={reconcileAdjustmentDraft.principal_amount}
                    onValueChange={(value) => setReconcileAdjustmentDraft((current) => ({ ...current, principal_amount: value }))}
                  />
                </label>
                <label>
                  Juros
                  <MoneyInput
                    value={reconcileAdjustmentDraft.interest_amount}
                    onValueChange={(value) => setReconcileAdjustmentDraft((current) => ({ ...current, interest_amount: value }))}
                  />
                </label>
                <label>
                  Desconto
                  <MoneyInput
                    value={reconcileAdjustmentDraft.discount_amount}
                    onValueChange={(value) => setReconcileAdjustmentDraft((current) => ({ ...current, discount_amount: value }))}
                  />
                </label>
                <label>
                  Multa
                  <MoneyInput
                    value={reconcileAdjustmentDraft.penalty_amount}
                    onValueChange={(value) => setReconcileAdjustmentDraft((current) => ({ ...current, penalty_amount: value }))}
                  />
                </label>
              </div>
            </div>
          )}

          <div className="table-shell tall compact-table-shell">
            <table className="erp-table compact-table reconciliation-entry-table">
              <thead>
                <tr>
                  <th className="checkbox-cell">
                    <input
                      aria-label={allVisibleEntriesSelected ? "Desselecionar lançamentos visíveis" : "Selecionar lançamentos visíveis"}
                      checked={allVisibleEntriesSelected}
                      disabled={!selectableEntryIds.length}
                      onChange={toggleAllVisibleEntries}
                      type="checkbox"
                    />
                  </th>
                  <th>Vencimento</th>
                  <th>Lançamentos</th>
                  <th>Categoria</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Pago</th>
                </tr>
              </thead>
              <tbody>
                {entryRows.map((entry) => (
                  <tr key={entry.id}>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={selectedEntryIds.includes(entry.id)}
                        disabled={!canSelectEntry(entry)}
                        onChange={() => toggleEntrySelection(entry.id)}
                      />
                    </td>
                    <td>{formatDate(entry.due_date)}</td>
                    <td title={compactSingleLine(entry.title)}><span className="single-line-cell">{compactSingleLine(entry.title)}</span></td>
                    <td title={compactSingleLine(entry.category_name ?? "-")}><span className="single-line-cell">{compactSingleLine(entry.category_name ?? "-")}</span></td>
                    <td className="numeric-cell compact-amount-cell">{formatReconciliationAmount(entry.total_amount)}</td>
                    <td><PaidStatusIcon active={entry.status === "settled"} /></td>
                  </tr>
                ))}
                {!entryRows.length && (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      {entryLoading ? "Carregando..." : "Nenhum lançamento encontrado."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="table-footer reconciliation-table-footer reconciliation-table-footer-simple">
            <div className="table-footer-meta">
              <span>
                {entryRows.length} de {entryTotal} lançamento(s) carregados
                {entryTotal > RECONCILIATION_ENTRY_FETCH_LIMIT ? ` (limite ${RECONCILIATION_ENTRY_FETCH_LIMIT})` : ""}
              </span>
            </div>
          </div>
        </article>
      </section>

      {modal === "create" && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card">
            <div className="panel-title">
              <h3>Efetuar lançamento a partir do extrato</h3>
              <button className="ghost-button" type="button" onClick={() => setModal(null)}>
                Fechar
              </button>
            </div>
            <div className="form-grid dense">
              <label>
                Título
                <input value={createDraft.title} onChange={(event) => setCreateDraft({ ...createDraft, title: event.target.value })} />
              </label>
              <label className="span-three">
                Categoria
                <CreatableSelect
                  classNamePrefix="erp-select"
                  formatCreateLabel={(inputValue) => `Criar categoria: ${inputValue}`}
                  isClearable
                  isDisabled={creatingCategory}
                  isLoading={creatingCategory}
                  menuPortalTarget={typeof document !== "undefined" ? document.body : null}
                  noOptionsMessage={() => "Nenhuma categoria encontrada"}
                  onChange={(option) => setCreateDraft({ ...createDraft, category_id: option?.value ?? "" })}
                  onCreateOption={(inputValue) => void handleCreateCategory(inputValue)}
                  options={categoryOptions}
                  placeholder="Buscar, selecionar ou criar categoria"
                  styles={categorySelectStyles}
                  value={selectedCategoryOption}
                />
              </label>
              {supplierRequired && (
                <>
                  <label className="span-three">
                    Fornecedor *
                    <CreatableSelect
                      classNamePrefix="erp-select"
                      formatCreateLabel={(inputValue) => `Criar fornecedor: ${inputValue}`}
                      isClearable
                      isDisabled={creatingSupplier}
                      isLoading={creatingSupplier}
                      menuPortalTarget={typeof document !== "undefined" ? document.body : null}
                      noOptionsMessage={() => "Nenhum fornecedor encontrado"}
                      onChange={(option) => setCreateDraft({ ...createDraft, supplier_id: option?.value ?? "" })}
                      onCreateOption={(inputValue) => void handleInlineSupplierCreate(inputValue)}
                      options={supplierOptions}
                      placeholder="Buscar, selecionar ou criar fornecedor"
                      styles={categorySelectStyles}
                      value={selectedSupplierOption}
                    />
                  </label>
                </>
              )}
              <label className="span-two">
                Observacoes
                <textarea value={createDraft.notes} onChange={(event) => setCreateDraft({ ...createDraft, notes: event.target.value })} />
              </label>
            </div>
            <div className="modal-summary">
              <span>Movimentos selecionados: {selectedBankIds.length}</span>
              <strong>{formatMoney(selectedBankDirectionCount > 1 ? selectedBankGrossAmount : selectedBankTotal)}</strong>
            </div>
            {!!createEntryValidationMessage && <div className="import-last-meta">{createEntryValidationMessage}</div>}
            <div className="action-row">
              <button
                className="primary-button"
                type="button"
                disabled={!canCreateConsolidatedEntry}
                onClick={() => void handleCreateEntry()}
              >
                Criar lançamento consolidado
              </button>
            </div>
          </div>
        </div>
      )}

      {modal === "transfer" && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card">
            <div className="panel-title">
              <h3>Lançar transferência entre contas</h3>
              <button className="ghost-button" type="button" onClick={() => setModal(null)}>
                Fechar
              </button>
            </div>
            <div className="form-grid dense">
              <label>
                Título
                <input value={createDraft.title} onChange={(event) => setCreateDraft({ ...createDraft, title: event.target.value })} />
              </label>
              <label>
                {transferSelectableAccountLabel}
                <select
                  value={createDraft.destination_account_id}
                  onChange={(event) => setCreateDraft({ ...createDraft, destination_account_id: event.target.value })}
                >
                  <option value="">Selecionar</option>
                  {transferSelectableAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-two field-note-only">
                {transferFixedAccountLabel}
                <span className="field-help-text">
                  {selectedTransferAccountName}
                </span>
              </label>
              <label className="span-two">
                Observacoes
                <textarea value={createDraft.notes} onChange={(event) => setCreateDraft({ ...createDraft, notes: event.target.value })} />
              </label>
            </div>
            <div className="modal-summary">
              <span>Movimentos selecionados: {selectedBankItems.length}</span>
              <strong>{formatMoney(selectedBankTotal)}</strong>
            </div>
            <div className="action-row">
              <button
                className="primary-button"
                type="button"
                disabled={!createDraft.destination_account_id || !selectedBankIds.length}
                onClick={() => void handleCreateTransfer()}
              >
                Criar transferência
              </button>
            </div>
          </div>
        </div>
      )}

      {categoryCreationModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card purchase-modal-card">
            <div className="panel-title">
              <h3>Selecionar grupo da categoria</h3>
              <button
                className="ghost-button"
                type="button"
                onClick={() => {
                  setCategoryCreationModalOpen(false);
                  setCategoryCreationDraft(emptyCategoryCreationDraft);
                }}
              >
                Fechar
              </button>
            </div>
            <div className="form-grid dense">
              <label>
                Categoria
                <input
                  value={categoryCreationDraft.name}
                  onChange={(event) => setCategoryCreationDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label>
                Grupo
                <input
                  list="reconciliation-category-group-options"
                  value={categoryCreationDraft.report_group}
                  onChange={(event) => setCategoryCreationDraft((current) => ({ ...current, report_group: event.target.value }))}
                  placeholder="Selecione ou digite o grupo"
                />
              </label>
              <datalist id="reconciliation-category-group-options">
                {categoryGroupOptions.map((group) => (
                  <option key={group} value={group} />
                ))}
              </datalist>
            </div>
            <div className="action-row">
              <button
                className="primary-button"
                type="button"
                disabled={creatingCategory || !categoryCreationDraft.name.trim() || !categoryCreationDraft.report_group.trim()}
                onClick={() => void confirmCategoryCreation()}
              >
                Criar categoria
              </button>
              <button
                className="ghost-button"
                type="button"
                onClick={() => {
                  setCategoryCreationModalOpen(false);
                  setCategoryCreationDraft(emptyCategoryCreationDraft);
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

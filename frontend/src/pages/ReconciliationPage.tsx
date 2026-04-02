import { useEffect, useMemo, useRef, useState } from "react";
import CreatableSelect from "react-select/creatable";

import { MoneyInput } from "../components/MoneyInput";
import { formatDate, formatEntryStatus, formatMoney, isGroupedEntryTitle, normalizeDisplayText } from "../lib/format";
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
  onUploadOfx: (file: File, accountId: string) => Promise<void>;
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

function displayCounterparty(entry: FinancialEntry) {
  return isGroupedEntryTitle(entry.title) ? "-" : compactSingleLine(entry.counterparty_name);
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

function extractFinderKeyword(value: string) {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);

  return normalized.find((token) => token.length >= 3) ?? normalized[0] ?? "";
}

function buildFinderCounterparty(item: ReconciliationWorklist["items"][number] | null) {
  if (!item) {
    return "";
  }

  const directName = compactSingleLine(item.name, "");
  if (directName) {
    return extractFinderKeyword(directName);
  }

  const rawMemo = compactSingleLine(item.memo, "")
    .replace(/^pix enviado:\s*/i, "")
    .replace(/^pix recebido:\s*/i, "")
    .replace(/^pagamento efetuado:\s*/i, "")
    .replace(/^transferencia recebida:\s*/i, "")
    .replace(/^transferencia enviada:\s*/i, "")
    .replace(/^boleto de cobranca recebido:\s*/i, "")
    .replace(/^credito domicilio cartao:\s*/i, "")
    .trim();

  return extractFinderKeyword(rawMemo);
}

function SelectionIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <rect height="10" rx="2" stroke="currentColor" strokeWidth="1.4" width="10" x="3" y="3" />
      <path d="M5.5 8l1.6 1.6L10.7 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

function SelectionClearIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 16 16" width="14">
      <rect height="10" rx="2" stroke="currentColor" strokeWidth="1.4" width="10" x="3" y="3" />
      <path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.4" />
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
  onUploadOfx,
  onSyncInterStatement,
  onReconcile,
  onUnreconcile,
  onQuickAction,
  onSearchEntries,
  onCreateCategory,
  onCreateSupplier,
  embedded = false,
}: Props) {
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
  const [ofxFile, setOfxFile] = useState<File | null>(null);
  const [ofxAccountId, setOfxAccountId] = useState(filters.account_id);
  const [ofxModalOpen, setOfxModalOpen] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [createDraft, setCreateDraft] = useState<CreateDraft>(emptyDraft);
  const [reconcileAdjustmentDraft, setReconcileAdjustmentDraft] = useState<ReconcileAdjustmentDraft>(emptyAdjustmentDraft);
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [creatingSupplier, setCreatingSupplier] = useState(false);
  const [categoryCreationModalOpen, setCategoryCreationModalOpen] = useState(false);
  const [categoryCreationDraft, setCategoryCreationDraft] = useState<CategoryCreationDraft>(emptyCategoryCreationDraft);
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
  const latestOfxBatch = useMemo(
    () => importSummary.import_batches.find((batch) => batch.source_type.startsWith("ofx:")) ?? null,
    [importSummary.import_batches],
  );
  const hasInterApiAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const ofxAccounts = useMemo(
    () => accounts.filter((account) => account.is_active && account.import_ofx_enabled),
    [accounts],
  );

  const selectedEntryRows = entryRows.filter((entry) => selectedEntryIds.includes(entry.id));
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

  useEffect(() => {
    setSelectedBankIds([]);
    setSelectedEntryIds([]);
    setBankSearch("");
  }, [worklist]);

  useEffect(() => {
    setOfxAccountId((current) => current || filters.account_id);
  }, [filters.account_id]);

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

    const suggestedSearch = buildFinderCounterparty(selectedBankItems[0]);
    setSelectedEntryIds([]);
    setEntrySearch(suggestedSearch);
    setEntryStatus("open");
  }, [finderModeActive, selectedBankItems]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadPeriodEntries(entrySearch, entryStatus);
    }, 220);

    return () => window.clearTimeout(timeoutId);
  }, [entrySearch, entryStatus, filters.end, filters.start]);

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
      const response = await onSearchEntries({
        date_from: filters.start,
        date_to: filters.end,
        status,
        search,
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

  function selectFilteredBankItems() {
    const eligibleIds = filteredBankItems
      .filter((item) => item.reconciliation_status !== "matched")
      .map((item) => item.bank_transaction_id);
    setSelectedBankIds(eligibleIds);
  }

  function clearBankSelection() {
    setSelectedBankIds([]);
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

  async function handleOfxImport() {
    if (!ofxFile || !ofxAccountId) {
      return;
    }
    await onUploadOfx(ofxFile, ofxAccountId);
    setOfxFile(null);
    setOfxModalOpen(false);
  }

  const reconciliationFiltersContent = (
    <div className="reconciliation-toolbar-stack">
      <div className="reconciliation-filter-group reconciliation-filter-group--primary reconciliation-filter-group--top">
        <label>
          Conta
          <select
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
        </label>
        <label>
          Inicio
          <input type="date" value={filters.start} onChange={(event) => onChangeFilters({ ...filters, start: event.target.value })} />
        </label>
        <label>
          Fim
          <input type="date" value={filters.end} onChange={(event) => onChangeFilters({ ...filters, end: event.target.value })} />
        </label>
        <div className="reconciliation-inline-meta">
          <div className="reconciliation-inline-stat">
            <span>Pendentes</span>
            <strong>{overallPendingCount}</strong>
          </div>
          <span className="reconciliation-import-meta">
            Último lançamento importado: {importSummary.latest_ofx_transaction_date ? formatDate(importSummary.latest_ofx_transaction_date) : "nenhum"}
          </span>
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
          <div className="panel-title">
            <h3>Extrato bancário</h3>
            <div className="panel-mini-actions">
              <button
                aria-label="Selecionar filtrados"
                className="secondary-button reconciliation-icon-button"
                disabled={!filteredBankItems.length}
                onClick={selectFilteredBankItems}
                title="Selecionar filtrados"
                type="button"
              >
                <SelectionIcon />
              </button>
              <button
                aria-label="Limpar seleção"
                className="ghost-button reconciliation-icon-button"
                disabled={!selectedBankIds.length}
                onClick={clearBankSelection}
                title="Limpar seleção"
                type="button"
              >
                <SelectionClearIcon />
              </button>
              <button className="secondary-button" type="button" disabled={!selectedBankIds.length} onClick={openTransferModal}>
                Transferência
              </button>
              <button className="secondary-button" type="button" disabled={!selectedBankIds.length} onClick={openCreateModal}>
                Efetuar lançamento
              </button>
            </div>
          </div>
          <div className="section-toolbar-content reconciliation-bank-toolbar">
            <label>
              Buscar no extrato
              <input value={bankSearch} onChange={(event) => setBankSearch(event.target.value)} />
            </label>
            <label>
              Tipo do extrato
              <select value={bankDirectionFilter} onChange={(event) => setBankDirectionFilter(event.target.value)}>
                <option value="all">Todos</option>
                <option value="in">Entradas</option>
                <option value="out">Saídas</option>
              </select>
            </label>
            <div className="reconciliation-panel-toolbar-actions">
              <label className="reconciliation-subtle-toggle">
                <input
                  type="checkbox"
                  checked={hideMatchedBankItems}
                  onChange={(event) => {
                    setHideMatchedBankItems(event.target.checked);
                  }}
                />
                <span>Ocultar conciliados</span>
              </label>
              <button className="secondary-button reconciliation-import-button" type="button" onClick={() => setOfxModalOpen(true)}>
                OFX
              </button>
              <button
                className="secondary-button icon-button reconciliation-import-button"
                disabled={submitting || !hasInterApiAccount}
                onClick={() => void onSyncInterStatement()}
                title="Atualizar extrato do Inter"
                type="button"
              >
                <RefreshIcon />
              </button>
            </div>
          </div>

          <div className="table-shell tall compact-table-shell">
            <table className="erp-table compact-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Data</th>
                  <th>Histórico</th>
                  <th>Conta</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Situacao</th>
                </tr>
              </thead>
              <tbody>
                {filteredBankItems.map((item) => {
                  const isMatched = item.reconciliation_status === "matched";
                  return (
                    <tr key={item.bank_transaction_id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedBankIds.includes(item.bank_transaction_id)}
                          disabled={isMatched}
                          onChange={() => toggleBankSelection(item.bank_transaction_id)}
                        />
                      </td>
                      <td>{formatDate(item.posted_at)}</td>
                      <td>
                        <div className="cell-stack reconciliation-cell-stack">
                          <strong className="single-line-cell">{compactSingleLine(item.name ?? item.memo ?? item.fit_id)}</strong>
                          <span className="compact-muted compact-detail-line">{compactSingleLine(item.memo ?? item.fit_id)}</span>
                        </div>
                      </td>
                      <td>{compactSingleLine(item.account_name)}</td>
                      <td className="numeric-cell compact-amount-cell">{formatReconciliationAmount(item.amount)}</td>
                      <td>
                        {isMatched ? "Conciliado" : "Pendente"}
                        {item.applied_entries.length > 0 && (
                          <div className="compact-muted compact-detail-line">
                            {item.applied_entries.map((entry) => compactSingleLine(entry.title)).join(", ")}
                          </div>
                        )}
                        {isMatched && (
                          <div className="compact-row-actions">
                            <button
                              className="text-action-button"
                              type="button"
                              onClick={() => void handleUnreconcile(item.bank_transaction_id, item.undo_mode)}
                            >
                              Desconciliar
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {!worklist?.items.length && (
                  <tr>
                    <td colSpan={6} className="empty-cell">
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
          <div className="panel-title">
            <h3>Lançamentos do sistema</h3>
            <div className="panel-mini-actions">
              <button
                className={finderModeActive ? "primary-button" : "secondary-button"}
                type="button"
                onClick={() => void toggleFinderMode()}
              >
                {finderModeActive ? "Busca por extrato ativa" : "Encontrar fatura em aberto"}
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={!selectedBankIds.length || !selectedEntryIds.length || loading}
                onClick={() => void handleBulkReconcile()}
              >
                Conciliar selecionados
              </button>
            </div>
          </div>
          <div className="section-toolbar-content reconciliation-entry-toolbar">
            <label>
              Buscar lançamentos
              <input value={entrySearch} onChange={(event) => setEntrySearch(event.target.value)} />
            </label>
        <label>
          Status
          <select value={entryStatus} onChange={(event) => setEntryStatus(event.target.value)}>
            <option value="">Todos</option>
            <option value="open">Em aberto</option>
            <option value="settled">Pago</option>
          </select>
        </label>
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
            <table className="erp-table compact-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Vencimento</th>
                  <th>Fatura/Lançamento</th>
                  <th>Cliente/Fornecedor</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {entryRows.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedEntryIds.includes(entry.id)}
                        disabled={!canSelectEntry(entry)}
                        onChange={() => toggleEntrySelection(entry.id)}
                      />
                    </td>
                    <td>{formatDate(entry.due_date)}</td>
                    <td>
                      <div className="cell-stack reconciliation-cell-stack">
                        <strong className="single-line-cell">{compactSingleLine(entry.title)}</strong>
                        <span className="compact-muted compact-detail-line">
                          {compactSingleLine(entry.document_number ?? entry.category_name ?? "Sem documento")}
                        </span>
                      </div>
                    </td>
                    <td>{displayCounterparty(entry)}</td>
                    <td className="numeric-cell">{formatMoney(Number(entry.total_amount))}</td>
                    <td>{formatEntryStatus(entry.status)}</td>
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
                Titulo
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
                Titulo
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

      {ofxModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card purchase-modal-card">
            <div className="panel-title">
              <h3>OFX</h3>
              <button className="ghost-button" type="button" onClick={() => setOfxModalOpen(false)}>
                Fechar
              </button>
            </div>
            <div className="form-grid dense">
              <label>
                Conta
                <select value={ofxAccountId} onChange={(event) => setOfxAccountId(event.target.value)}>
                  <option value="">Selecionar conta</option>
                  {ofxAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Arquivo OFX
                <input type="file" accept=".ofx" onChange={(event) => setOfxFile(event.target.files?.[0] ?? null)} />
              </label>
            </div>
            {!ofxAccounts.length && <div className="import-last-meta">Nenhuma conta com importacao OFX habilitada.</div>}
            <div className="import-last-meta">
              {latestOfxBatch ? `Ultima importacao: ${latestOfxBatch.filename} em ${formatDate(latestOfxBatch.created_at)}` : "Ultima importacao: nenhuma"}
            </div>
            <div className="action-row">
              <button
                className="primary-button"
                disabled={submitting || !ofxFile || !ofxAccountId}
                onClick={() => void handleOfxImport()}
                type="button"
              >
                OFX
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

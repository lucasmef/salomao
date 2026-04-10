import { useEffect, useMemo, useState } from "react";
import { MoneyInput } from "../components/MoneyInput";
import { ModalCloseButton } from "../components/ModalCloseButton";
import { formatDate, formatEntryStatus, formatMoney } from "../lib/format";
import type { Account, BoletoAlertItem, BoletoClient, BoletoDashboard } from "../types";

type Props = {
  accounts: Account[];
  view: BillingView;
  onCancelInterBoleto: (boletoId: string) => Promise<void>;
  dashboard: BoletoDashboard;
  showAllMonthlyMissingBoletos: boolean;
  submitting: boolean;
  onDownloadInterBoletoPdf: (boletoId: string) => Promise<void>;
  onDownloadInterBoletoPdfBatch: (boletoIds: string[]) => Promise<void>;
  onExportMissingBoletos: (selectionKeys: string[]) => Promise<void>;
  onIssueInterCharges: (selectionKeys: string[]) => Promise<void>;
  onReceiveInterBoleto: (boletoId: string, payWith?: "BOLETO" | "PIX") => Promise<void>;
  onCreateStandaloneBoleto: (payload: {
    account_id: string | null;
    client_name: string;
    amount: string;
    due_date: string;
    notes: string | null;
  }) => Promise<void>;
  onDownloadStandaloneBoletoPdf: (boletoId: string) => Promise<void>;
  onMarkStandaloneBoletoDownloaded: (boletoId: string) => Promise<void>;
  onCancelStandaloneBoleto: (boletoId: string) => Promise<void>;
  onSyncStandaloneBoletos: () => Promise<void>;
  onToggleAllMonthlyMissingBoletos: (showAll: boolean) => Promise<void>;
  onUploadBoletoC6: (file: File) => Promise<void>;
  onUploadClientData: (file: File) => Promise<void>;
  showMissingExportFallback: boolean;
  onSaveClients: (payload: {
    clients: Array<{
      client_key: string;
      uses_boleto: boolean;
      mode: string;
      boleto_due_day: number | null;
      include_interest: boolean;
      notes: string | null;
    }>;
  }) => Promise<void>;
};

type EditableClient = BoletoClient & { dirty?: boolean };
type StandaloneBoletoDraft = {
  account_id: string;
  client_name: string;
  amount: string;
  due_date: string;
  notes: string;
};
export type InvoiceFilter = "open" | "open-boletos" | "overdue" | "paid-pending" | "missing" | "excess";
export type BillingView = "standalone" | InvoiceFilter;
type OpenReceivableSort = "due_date" | "client_name" | "document" | "status" | "amount";
type OpenBoletoSort = "due_date" | "issue_date" | "client_name" | "bank" | "amount" | "document_id";
type StandaloneBoletoFilter = "all" | "open" | "paid" | "downloaded" | "cancelled";
type SortDirection = "asc" | "desc";
type OpenReceivableDateFilters = {
  start: string;
  end: string;
};

function getTodayInputDate() {
  return new Date().toISOString().slice(0, 10);
}

function uniqueStandaloneClientNames(clients: BoletoClient[]) {
  return Array.from(new Set(clients.map((item) => item.client_name.trim()).filter(Boolean))).sort((left, right) =>
    left.localeCompare(right, "pt-BR"),
  );
}

function resolveStandaloneBoletoFilter(item: BoletoDashboard["standalone_boletos"][number]): StandaloneBoletoFilter {
  if (item.local_status === "downloaded") {
    return "downloaded";
  }
  if (item.status === "Recebido por boleto") {
    return "paid";
  }
  if (item.status === "Cancelado") {
    return "cancelled";
  }
  return "open";
}

function formatStandaloneBoletoFilterLabel(filter: StandaloneBoletoFilter) {
  switch (filter) {
    case "paid":
      return "Pagos";
    case "downloaded":
      return "Baixados";
    case "cancelled":
      return "Cancelados";
    case "all":
      return "Todos";
    case "open":
    default:
      return "Em aberto";
  }
}

function renderReceivableDetails(item: BoletoAlertItem) {
  if (!item.receivables.length) {
    return "-";
  }
  return item.receivables
    .slice(0, 3)
    .map((receivable) => `${receivable.invoice_number || "Sem numero"}/${receivable.installment || "-"}`)
    .join(", ");
}

function formatRangeLabel(start: string, end: string) {
  if (!start && !end) {
    return "Selecionar periodo";
  }
  if (start && end) {
    return `${formatDate(start)} - ${formatDate(end)}`;
  }
  return start ? `${formatDate(start)} - ...` : `... - ${formatDate(end)}`;
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

function DownloadIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M10 4.5v8.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.75 10 10 13.25 13.25 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 15.25h12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CancelIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="m6 6 8 8M14 6l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="m5.5 10.5 3 3 6-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SortDirectionIcon({ direction }: { direction: SortDirection }) {
  if (direction === "asc") {
    return (
      <svg aria-hidden="true" height="14" viewBox="0 0 16 16" width="14">
        <path d="M8 12V4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        <path d="m4.75 7.25 3.25-3.25 3.25 3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" height="14" viewBox="0 0 16 16" width="14">
      <path d="M8 4v8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      <path d="m4.75 8.75 3.25 3.25 3.25-3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function boletoMatchesQuery(
  boleto: BoletoDashboard["open_boletos"][number],
  query: string,
) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return true;
  }
  return [
    boleto.client_name,
    boleto.document_id,
    boleto.inter_codigo_solicitacao,
    boleto.linha_digitavel,
    boleto.barcode,
    boleto.status,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalizedQuery));
}

function compareText(left: string | null | undefined, right: string | null | undefined) {
  return String(left ?? "").localeCompare(String(right ?? ""), "pt-BR");
}

function compareNumber(left: string | number, right: string | number) {
  return Number(left) - Number(right);
}

export function BoletosPage({
  accounts,
  view,
  onCancelInterBoleto,
  dashboard,
  showAllMonthlyMissingBoletos,
  submitting,
  onDownloadInterBoletoPdf,
  onDownloadInterBoletoPdfBatch,
  onExportMissingBoletos,
  onIssueInterCharges,
  onReceiveInterBoleto,
  onCreateStandaloneBoleto,
  onDownloadStandaloneBoletoPdf,
  onMarkStandaloneBoletoDownloaded,
  onCancelStandaloneBoleto,
  onSyncStandaloneBoletos,
  onToggleAllMonthlyMissingBoletos,
  onUploadBoletoC6,
  onUploadClientData,
  showMissingExportFallback,
  onSaveClients,
}: Props) {
  const [c6File, setC6File] = useState<File | null>(null);
  const [c6ModalOpen, setC6ModalOpen] = useState(false);
  const [customerDataFile, setCustomerDataFile] = useState<File | null>(null);
  const [customerDataModalOpen, setCustomerDataModalOpen] = useState(false);
  const [clientsModalOpen, setClientsModalOpen] = useState(false);
  const [standaloneBoletoModalOpen, setStandaloneBoletoModalOpen] = useState(false);
  const [clients, setClients] = useState<EditableClient[]>([]);
  const [selectedMissingKeys, setSelectedMissingKeys] = useState<string[]>([]);
  const [selectedOpenBoletoIds, setSelectedOpenBoletoIds] = useState<string[]>([]);
  const [openBoletoSearch, setOpenBoletoSearch] = useState("");
  const [openBoletoBankFilter, setOpenBoletoBankFilter] = useState("all");
  const [openReceivableFilterDraft, setOpenReceivableFilterDraft] = useState<OpenReceivableDateFilters>({ start: "", end: "" });
  const [openReceivableFilters, setOpenReceivableFilters] = useState<OpenReceivableDateFilters>({ start: "", end: "" });
  const [openReceivableSort, setOpenReceivableSort] = useState<OpenReceivableSort>("due_date");
  const [openReceivableSortDirection, setOpenReceivableSortDirection] = useState<SortDirection>("asc");
  const [openBoletoSort, setOpenBoletoSort] = useState<OpenBoletoSort>("issue_date");
  const [openBoletoSortDirection, setOpenBoletoSortDirection] = useState<SortDirection>("desc");
  const [showOpenReceivablePeriodPopover, setShowOpenReceivablePeriodPopover] = useState(false);
  const [showOpenReceivablePresetMenu, setShowOpenReceivablePresetMenu] = useState(false);
  const [standaloneBoletoDraft, setStandaloneBoletoDraft] = useState<StandaloneBoletoDraft>({
    account_id: "",
    client_name: "",
    amount: "",
    due_date: "",
    notes: "",
  });
  const [standaloneBoletoFilter, setStandaloneBoletoFilter] = useState<StandaloneBoletoFilter>("open");
  const invoiceFilter = view === "standalone" ? "open" : view;
  const visibleStandaloneBoletos = useMemo(
    () =>
      [...dashboard.standalone_boletos]
        .filter((item) => standaloneBoletoFilter === "all" || resolveStandaloneBoletoFilter(item) === standaloneBoletoFilter)
        .sort((left, right) => compareText(left.due_date, right.due_date) || compareText(left.client_name, right.client_name)),
    [dashboard.standalone_boletos, standaloneBoletoFilter],
  );

  useEffect(() => {
    setClients(dashboard.clients.map((item) => ({ ...item, dirty: false })));
  }, [dashboard.clients]);

  useEffect(() => {
    const visibleKeys = new Set(dashboard.missing_boletos.map((item) => item.selection_key));
    setSelectedMissingKeys((current) => current.filter((item) => visibleKeys.has(item)));
  }, [dashboard.missing_boletos]);

  useEffect(() => {
    const visibleIds = new Set(dashboard.open_boletos.map((item) => item.id));
    setSelectedOpenBoletoIds((current) => current.filter((item) => visibleIds.has(item)));
  }, [dashboard.open_boletos]);

  const standaloneClientOptions = useMemo(() => uniqueStandaloneClientNames(dashboard.clients), [dashboard.clients]);
  const filesBySource = useMemo(
    () => Object.fromEntries(dashboard.files.map((item) => [item.source_type, item] as const)) as Record<string, BoletoDashboard["files"][number]>,
    [dashboard.files],
  );
  const openReceivables = useMemo(
    () =>
      [...dashboard.receivables]
        .filter((item) => Number(item.corrected_amount || item.amount) > 0)
        .filter((item) => {
          if (!openReceivableFilters.start && !openReceivableFilters.end) {
            return true;
          }
          if (!item.due_date) {
            return false;
          }
          if (openReceivableFilters.start && item.due_date < openReceivableFilters.start) {
            return false;
          }
          if (openReceivableFilters.end && item.due_date > openReceivableFilters.end) {
            return false;
          }
          return true;
        })
        .sort((left, right) => {
          const result = (() => {
            switch (openReceivableSort) {
              case "client_name":
                return compareText(left.client_name, right.client_name);
              case "document":
                return compareText(
                  `${left.invoice_number || "Sem numero"}/${left.installment || "-"}`,
                  `${right.invoice_number || "Sem numero"}/${right.installment || "-"}`,
                );
              case "status":
                return compareText(left.status, right.status);
              case "amount":
                return compareNumber(left.corrected_amount || left.amount, right.corrected_amount || right.amount);
              case "due_date":
              default:
                return compareText(left.due_date, right.due_date);
            }
          })();
          return openReceivableSortDirection === "asc" ? result : -result;
        }),
    [dashboard.receivables, openReceivableFilters.end, openReceivableFilters.start, openReceivableSort, openReceivableSortDirection],
  );
  const hasInterApiAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const availableOpenBoletoBanks = useMemo(
    () => [...new Set(dashboard.open_boletos.map((item) => item.bank).filter(Boolean))].sort((left, right) => left.localeCompare(right, "pt-BR")),
    [dashboard.open_boletos],
  );
  const filteredOpenBoletos = useMemo(
    () =>
      dashboard.open_boletos
        .filter((item) => boletoMatchesQuery(item, openBoletoSearch))
        .filter((item) => openBoletoBankFilter === "all" || item.bank === openBoletoBankFilter)
        .sort((left, right) => {
          const result = (() => {
            switch (openBoletoSort) {
              case "issue_date":
                return compareText(left.issue_date, right.issue_date);
              case "client_name":
                return compareText(left.client_name, right.client_name);
              case "bank":
                return compareText(left.bank, right.bank);
              case "amount":
                return compareNumber(left.amount, right.amount);
              case "document_id":
                return compareText(left.document_id, right.document_id);
              case "due_date":
              default:
                return compareText(left.due_date, right.due_date);
            }
          })();
          return openBoletoSortDirection === "asc" ? result : -result;
        }),
    [dashboard.open_boletos, openBoletoSearch, openBoletoBankFilter, openBoletoSort, openBoletoSortDirection],
  );
  const downloadableOpenBoletos = useMemo(
    () => filteredOpenBoletos.filter((item) => item.pdf_available),
    [filteredOpenBoletos],
  );

  useEffect(() => {
    const visibleIds = new Set(filteredOpenBoletos.map((item) => item.id));
    setSelectedOpenBoletoIds((current) => current.filter((item) => visibleIds.has(item)));
  }, [filteredOpenBoletos]);

  useEffect(() => {
    setClientsModalOpen(false);
    setC6ModalOpen(false);
    setC6File(null);
    setCustomerDataModalOpen(false);
    setStandaloneBoletoModalOpen(false);
    setCustomerDataFile(null);
    setShowOpenReceivablePeriodPopover(false);
    setShowOpenReceivablePresetMenu(false);
  }, [view]);

  function renderFileMeta(sourceType: string) {
    const file =
      filesBySource[sourceType] ??
      dashboard.files.find((item) => sourceType.endsWith(":") && item.source_type.startsWith(sourceType));
    if (!file) {
      return <small className="compact-muted">Nenhuma carga ainda.</small>;
    }
    return (
      <small className="compact-muted">
        Ultima carga: {file.name} em {formatDate(file.updated_at)}
      </small>
    );
  }

  async function handleSaveClients() {
    await onSaveClients({
      clients: clients.map((item) => ({
        client_key: item.client_key,
        uses_boleto: item.uses_boleto,
        mode: item.mode,
        boleto_due_day: item.boleto_due_day,
        include_interest: item.include_interest,
        notes: item.notes,
      })),
    });
  }

  function toggleMissingSelection(selectionKey: string) {
    setSelectedMissingKeys((current) =>
      current.includes(selectionKey) ? current.filter((item) => item !== selectionKey) : [...current, selectionKey],
    );
  }

  function toggleOpenBoletoSelection(boletoId: string) {
    setSelectedOpenBoletoIds((current) =>
      current.includes(boletoId) ? current.filter((item) => item !== boletoId) : [...current, boletoId],
    );
  }

  function toggleOpenReceivableSort(nextSort: OpenReceivableSort) {
    if (openReceivableSort === nextSort) {
      setOpenReceivableSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setOpenReceivableSort(nextSort);
    setOpenReceivableSortDirection("asc");
  }

  function toggleOpenBoletoSort(nextSort: OpenBoletoSort) {
    if (openBoletoSort === nextSort) {
      setOpenBoletoSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setOpenBoletoSort(nextSort);
    setOpenBoletoSortDirection("asc");
  }

  function setOpenReceivableDateRange(start: string, end: string) {
    setOpenReceivableFilterDraft({ start, end });
  }

  function applyOpenReceivableDateFilters() {
    setOpenReceivableFilters(openReceivableFilterDraft);
  }

  function applyOpenReceivablePresetRange(kind: "today" | "current_month" | "previous_month" | "current_year") {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const formatValue = (value: Date) => value.toISOString().slice(0, 10);

    if (kind === "today") {
      const current = formatValue(today);
      setOpenReceivableDateRange(current, current);
      return;
    }

    if (kind === "current_month") {
      setOpenReceivableDateRange(formatValue(new Date(year, month, 1)), formatValue(new Date(year, month + 1, 0)));
      return;
    }

    if (kind === "previous_month") {
      setOpenReceivableDateRange(formatValue(new Date(year, month - 1, 1)), formatValue(new Date(year, month, 0)));
      return;
    }

    setOpenReceivableDateRange(formatValue(new Date(year, 0, 1)), formatValue(new Date(year, 11, 31)));
  }

  function renderSortButton(
    label: string,
    sortKey: string,
    currentSort: string,
    direction: SortDirection,
    onClick: () => void,
    numeric = false,
  ) {
    const isActive = currentSort === sortKey;
    return (
      <button className={`table-sort-button ${numeric ? "numeric" : ""}`.trim()} onClick={onClick} type="button">
        <strong>{label}</strong>
        {isActive ? (
          <span className="table-sort-indicator is-active">
            <SortDirectionIcon direction={direction} />
          </span>
        ) : null}
      </button>
    );
  }

  function resolveInterEnvironment(boleto: BoletoDashboard["open_boletos"][number]) {
    const directAccount = boleto.inter_account_id
      ? accounts.find((account) => account.id === boleto.inter_account_id)
      : null;
    if (directAccount?.inter_environment) {
      return directAccount.inter_environment;
    }
    const fallbackInterAccount = accounts.find((account) => account.is_active && account.inter_api_enabled);
    return fallbackInterAccount?.inter_environment ?? null;
  }

  function canCancelInterBoleto(boleto: BoletoDashboard["open_boletos"][number]) {
    return Boolean(
      boleto.bank === "INTER" &&
      boleto.inter_codigo_solicitacao &&
      !["Cancelado", "Recebido por boleto"].includes(boleto.status),
    );
  }

  function canReceiveInterBoleto(boleto: BoletoDashboard["open_boletos"][number]) {
    return Boolean(
      boleto.bank === "INTER" &&
      boleto.inter_codigo_solicitacao &&
      resolveInterEnvironment(boleto) === "sandbox" &&
      boleto.status !== "Recebido por boleto" &&
      boleto.status !== "Cancelado",
    );
  }

  function handleCancelInterBoleto(boleto: BoletoDashboard["open_boletos"][number]) {
    if (!window.confirm(`Cancelar o boleto ${boleto.document_id || boleto.inter_codigo_solicitacao}?`)) {
      return;
    }
    void onCancelInterBoleto(boleto.id);
  }

  function handleReceiveInterBoleto(boleto: BoletoDashboard["open_boletos"][number]) {
    if (!window.confirm(`Baixar o boleto ${boleto.document_id || boleto.inter_codigo_solicitacao} no Inter sandbox?`)) {
      return;
    }
    void onReceiveInterBoleto(boleto.id, "BOLETO");
  }

  function canCancelStandaloneBoleto(boleto: BoletoDashboard["standalone_boletos"][number]) {
    return Boolean(
      boleto.bank === "INTER" &&
      boleto.inter_codigo_solicitacao &&
      !["Cancelado", "Recebido por boleto"].includes(boleto.status),
    );
  }

  function handleCancelStandaloneBoleto(boleto: BoletoDashboard["standalone_boletos"][number]) {
    if (!window.confirm(`Cancelar o boleto avulso ${boleto.document_id || boleto.inter_codigo_solicitacao}?`)) {
      return;
    }
    void onCancelStandaloneBoleto(boleto.id);
  }

  function renderBoletoActions(
    boletos: BoletoAlertItem["boletos"],
    options?: {
      showPdfAction?: boolean;
    },
  ) {
    const showPdfAction = options?.showPdfAction ?? true;
    if (!boletos.length) {
      return "-";
    }
    return (
      <div className="billing-boleto-list">
        {boletos.map((boleto) => (
          <div key={boleto.id} className="billing-boleto-chip">
            <span title={boleto.document_id || boleto.barcode || boleto.bank}>
              {boleto.document_id || boleto.barcode || boleto.bank || "-"}
            </span>
            {showPdfAction && boleto.pdf_available && (
              <button
                className="table-button icon-only-button"
                disabled={submitting}
                onClick={() => void onDownloadInterBoletoPdf(boleto.id)}
                title="Baixar PDF do boleto"
                type="button"
              >
                <DownloadIcon />
              </button>
            )}
          </div>
        ))}
      </div>
    );
  }

  function closeCustomerDataModal() {
    if (submitting) {
      return;
    }
    setCustomerDataModalOpen(false);
    setCustomerDataFile(null);
  }

  function closeC6Modal() {
    if (submitting) {
      return;
    }
    setC6ModalOpen(false);
    setC6File(null);
  }

  function closeStandaloneBoletoModal() {
    if (submitting) {
      return;
    }
    setStandaloneBoletoModalOpen(false);
  }

  function openStandaloneBoletoModal() {
    const today = getTodayInputDate();
    const defaultInterAccount = accounts.find((account) => account.is_active && account.inter_api_enabled);
    setStandaloneBoletoDraft((current) => ({
      ...current,
      account_id: current.account_id || defaultInterAccount?.id || "",
      due_date: current.due_date || today,
    }));
    setStandaloneBoletoModalOpen(true);
  }

  async function handleCreateStandaloneBoleto() {
    await onCreateStandaloneBoleto({
      account_id: standaloneBoletoDraft.account_id || null,
      client_name: standaloneBoletoDraft.client_name.trim(),
      amount: standaloneBoletoDraft.amount.trim(),
      due_date: standaloneBoletoDraft.due_date,
      notes: standaloneBoletoDraft.notes.trim() || null,
    });
    setStandaloneBoletoDraft({
      account_id: "",
      client_name: "",
      amount: "",
      due_date: "",
      notes: "",
    });
    setStandaloneBoletoModalOpen(false);
  }

  async function handleIssueMissingBoletos() {
    try {
      await onIssueInterCharges(selectedMissingKeys);
    } catch {
      // A exibicao do XLSX de contingencia passa a depender da falha da emissao.
    }
  }

  async function handleUploadC6() {
    if (!c6File) {
      return;
    }
    await onUploadBoletoC6(c6File);
    setC6File(null);
    setC6ModalOpen(false);
  }

  function renderStandaloneBoletoModal() {
    if (!standaloneBoletoModalOpen) {
      return null;
    }

    const interAccounts = accounts.filter((account) => account.is_active && account.inter_api_enabled);

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-customer-modal">
          <div className="panel-title compact-title-row">
            <h3>Novo boleto avulso</h3>
            <ModalCloseButton onClick={closeStandaloneBoletoModal} />
          </div>

          {!interAccounts.length ? (
            <div className="billing-modal-copy billing-modal-copy--warning">
              <p>Nenhuma conta com API Inter ativa foi encontrada. A emissão será liberada quando houver uma conta Inter ativa.</p>
            </div>
          ) : null}

          <div className="billing-standalone-form">
            <label className="billing-standalone-form-field">
              <span>Conta Inter</span>
              <select
                value={standaloneBoletoDraft.account_id}
                onChange={(event) =>
                  setStandaloneBoletoDraft((current) => ({ ...current, account_id: event.target.value }))
                }
              >
                <option value="">Selecione</option>
                {interAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="billing-standalone-form-field billing-standalone-form-field--wide">
              <span>Cliente</span>
              <input
                list="standalone-boleto-clients"
                placeholder="Nome do cliente"
                value={standaloneBoletoDraft.client_name}
                onChange={(event) =>
                  setStandaloneBoletoDraft((current) => ({ ...current, client_name: event.target.value }))
                }
              />
              <datalist id="standalone-boleto-clients">
                {standaloneClientOptions.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </label>

            <label className="billing-standalone-form-field">
              <span>Valor</span>
              <MoneyInput
                placeholder="0,00"
                value={standaloneBoletoDraft.amount}
                onValueChange={(value) =>
                  setStandaloneBoletoDraft((current) => ({ ...current, amount: value }))
                }
              />
            </label>

            <label className="billing-standalone-form-field">
              <span>Vencimento</span>
              <input
                type="date"
                value={standaloneBoletoDraft.due_date}
                onChange={(event) =>
                  setStandaloneBoletoDraft((current) => ({ ...current, due_date: event.target.value }))
                }
              />
            </label>

            <label className="billing-standalone-form-field billing-standalone-form-field--full">
              <span>Observação</span>
              <textarea
                rows={4}
                placeholder="Descreva o motivo ou referência deste boleto"
                value={standaloneBoletoDraft.notes}
                onChange={(event) =>
                  setStandaloneBoletoDraft((current) => ({ ...current, notes: event.target.value }))
                }
              />
            </label>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={
                submitting ||
                !interAccounts.length ||
                !standaloneBoletoDraft.client_name.trim() ||
                !standaloneBoletoDraft.amount.trim() ||
                !standaloneBoletoDraft.due_date
              }
              onClick={() => void handleCreateStandaloneBoleto()}
              type="button"
            >
              Emitir boleto
            </button>
            <button className="ghost-button" onClick={closeStandaloneBoletoModal} type="button">
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderCustomerDataModal() {
    if (!customerDataModalOpen) {
      return null;
    }

    const customerDataImport = filesBySource["boletos:etiquetas"];

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-customer-modal">
          <div className="panel-title compact-title-row">
            <h3>Atualizar dados dos clientes</h3>
            <ModalCloseButton onClick={closeCustomerDataModal} />
          </div>

          <div className="billing-modal-copy">
            <p>
              Envie o arquivo <strong>etiquetas.txt</strong> para atualizar endereco, numero, complemento, bairro,
              cidade, estado, CEP, CPF/CNPJ, IE e telefones dos clientes.
            </p>
            <p>
              Os campos <strong>usa boleto</strong>, <strong>modo</strong>, <strong>dia</strong> e <strong>cobrar multa/juros</strong> não são alterados.
            </p>
            <small className="compact-muted">
              {customerDataImport
                ? `Ultima carga: ${customerDataImport.name} em ${formatDate(customerDataImport.updated_at)}`
                : "Nenhuma carga de etiquetas feita ainda."}
            </small>
          </div>

          <div className="compact-import-card billing-modal-upload-card">
            <input
              id="boletos-customer-data-file"
              className="hidden-file-input"
              type="file"
              accept=".txt,.html"
              onChange={(event) => setCustomerDataFile(event.target.files?.[0] ?? null)}
            />
            <div className="billing-file-picker-row">
              <label className="secondary-button compact-file-trigger" htmlFor="boletos-customer-data-file">
                Selecionar etiquetas
              </label>
              {customerDataFile ? (
                <span className="compact-file-name" title={customerDataFile.name}>
                  {customerDataFile.name}
                </span>
              ) : null}
            </div>
            <small className="compact-muted">Esse arquivo será a base fixa para a próxima etapa de emissão.</small>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={submitting || !customerDataFile}
              onClick={() => customerDataFile && void onUploadClientData(customerDataFile)}
              type="button"
            >
              Importar etiquetas
            </button>
            <button className="ghost-button" onClick={closeCustomerDataModal} type="button">
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderC6UploadModal() {
    if (!c6ModalOpen) {
      return null;
    }

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-customer-modal">
          <div className="panel-title compact-title-row">
            <h3>Importar relatório C6</h3>
            <ModalCloseButton onClick={closeC6Modal} />
          </div>

          <div className="billing-modal-copy">
            <p>Envie o arquivo CSV do C6 para atualizar os registros usados na conferência de boletos faltando.</p>
            {renderFileMeta("boletos:c6")}
          </div>

          <div className="compact-import-card billing-modal-upload-card">
            <input
              id="boletos-c6-file"
              className="hidden-file-input"
              type="file"
              accept=".csv"
              onChange={(event) => setC6File(event.target.files?.[0] ?? null)}
            />
            <div className="billing-file-picker-row">
              <label className="secondary-button compact-file-trigger" htmlFor="boletos-c6-file">
                Selecionar relatório
              </label>
              {c6File ? (
                <span className="compact-file-name" title={c6File.name}>
                  {c6File.name}
                </span>
              ) : null}
            </div>
            <small className="compact-muted">Após a importação, esta aba refletirá os dados processados do arquivo.</small>
          </div>

          <div className="action-row">
            <button className="primary-button" disabled={submitting || !c6File} onClick={() => void handleUploadC6()} type="button">
              Importar arquivo
            </button>
            <button className="ghost-button" onClick={closeC6Modal} type="button">
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderClientsModal() {
    if (!clientsModalOpen) {
      return null;
    }

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-clients-modal">
          <div className="panel-title compact-title-row">
            <h3>Clientes</h3>
            <div className="action-row">
              <button className="secondary-button" disabled={submitting} onClick={() => setCustomerDataModalOpen(true)} type="button">
                Atualizar dados dos clientes
              </button>
              <button className="primary-button" disabled={submitting} onClick={() => void handleSaveClients()} type="button">
                Salvar configurações
              </button>
              <ModalCloseButton disabled={submitting} onClick={() => setClientsModalOpen(false)} />
            </div>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table entries-list-table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Faturas</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Usa boleto</th>
                  <th>Modo</th>
                  <th>Dia</th>
                  <th>Cobrar multa/juros</th>
                  <th>Baixas pendentes</th>
                  <th>Observações</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.client_key}>
                    <td>
                      <strong className="single-line-cell" title={client.client_name}>
                        {client.client_name}
                      </strong>
                    </td>
                    <td>{client.receivable_count}</td>
                    <td className="numeric-cell">{formatMoney(client.total_amount)}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.uses_boleto}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, uses_boleto: event.target.checked, dirty: true } : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={client.mode}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, mode: event.target.value, dirty: true } : item,
                            ),
                          )
                        }
                      >
                        <option value="individual">Individual</option>
                        <option value="mensal">Mensal</option>
                        <option value="negociacao">Negociação</option>
                      </select>
                    </td>
                    <td>
                      <input
                        className="mini-input"
                        type="number"
                        min={1}
                        max={31}
                        value={client.boleto_due_day ?? ""}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key
                                ? { ...item, boleto_due_day: event.target.value ? Number(event.target.value) : null, dirty: true }
                                : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.include_interest}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key
                                ? { ...item, include_interest: event.target.checked, dirty: true }
                                : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>{client.matched_paid_count}</td>
                    <td>
                      <input
                        value={client.notes ?? ""}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, notes: event.target.value, dirty: true } : item,
                            ),
                          )
                        }
                      />
                    </td>
                  </tr>
                ))}
                {!clients.length && (
                  <tr>
                    <td colSpan={9}>Nenhum cliente encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  function renderInvoicePanel() {
    if (invoiceFilter === "open") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Faturas em aberto</h3>
            <div className="action-row billing-open-boletos-actions">
              <div className="entries-period-group">
                <button
                  aria-expanded={showOpenReceivablePeriodPopover}
                  aria-label="Selecionar periodo"
                  className={`entries-period-trigger ${showOpenReceivablePeriodPopover ? "is-active" : ""}`}
                  disabled={submitting}
                  onClick={() => {
                    setShowOpenReceivablePresetMenu(false);
                    setShowOpenReceivablePeriodPopover((current) => !current);
                  }}
                  type="button"
                >
                  <CalendarRangeIcon />
                  <span>{formatRangeLabel(openReceivableFilterDraft.start, openReceivableFilterDraft.end)}</span>
                </button>
                {showOpenReceivablePeriodPopover && (
                  <div className="entries-floating-panel entries-period-popover">
                    <div className="entries-period-fields">
                      <input
                        aria-label="Data inicial"
                        disabled={submitting}
                        type="date"
                        value={openReceivableFilterDraft.start}
                        onChange={(event) => setOpenReceivableDateRange(event.target.value, openReceivableFilterDraft.end)}
                      />
                      <input
                        aria-label="Data final"
                        disabled={submitting}
                        type="date"
                        value={openReceivableFilterDraft.end}
                        onChange={(event) => setOpenReceivableDateRange(openReceivableFilterDraft.start, event.target.value)}
                      />
                    </div>
                    <div className="entries-period-footer">
                      <button
                        className="secondary-button compact-button"
                        onClick={() => {
                          setOpenReceivableDateRange("", "");
                          setShowOpenReceivablePeriodPopover(false);
                        }}
                        type="button"
                      >
                        Limpar
                      </button>
                      <button
                        className="primary-button compact-button"
                        onClick={() => setShowOpenReceivablePeriodPopover(false)}
                        type="button"
                      >
                        Concluir
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div className="entries-toolbar-icon-wrap">
                <button
                  aria-expanded={showOpenReceivablePresetMenu}
                  aria-label="Periodos pre-definidos"
                  className={`entries-toolbar-icon ${showOpenReceivablePresetMenu ? "is-active" : ""}`}
                  disabled={submitting}
                  onClick={() => {
                    setShowOpenReceivablePeriodPopover(false);
                    setShowOpenReceivablePresetMenu((current) => !current);
                  }}
                  title="Periodos pre-definidos"
                  type="button"
                >
                  <FilterFunnelIcon />
                  <span className="entries-toolbar-icon-label">Atalhos</span>
                </button>
                {showOpenReceivablePresetMenu && (
                  <div className="entries-floating-panel entries-icon-menu">
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("today"); setShowOpenReceivablePresetMenu(false); }} type="button">Hoje</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("current_month"); setShowOpenReceivablePresetMenu(false); }} type="button">Mes atual</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("previous_month"); setShowOpenReceivablePresetMenu(false); }} type="button">Mes anterior</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("current_year"); setShowOpenReceivablePresetMenu(false); }} type="button">Ano atual</button>
                  </div>
                )}
              </div>
              <button className="primary-button compact-button" disabled={submitting} onClick={applyOpenReceivableDateFilters} type="button">
                Aplicar
              </button>
              <span>{openReceivables.length}</span>
            </div>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table entries-list-table billing-open-receivables-table">
              <colgroup>
                <col className="billing-open-receivables-col-due-date" />
                <col className="billing-open-receivables-col-client" />
                <col className="billing-open-receivables-col-title" />
                <col className="billing-open-receivables-col-status" />
                <col className="billing-open-receivables-col-amount" />
              </colgroup>
              <thead>
                <tr>
                  <th>{renderSortButton("Vencimento", "due_date", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("due_date"))}</th>
                  <th>{renderSortButton("Cliente", "client_name", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("client_name"))}</th>
                  <th>{renderSortButton("Título", "document", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("document"))}</th>
                  <th>{renderSortButton("Status", "status", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("status"))}</th>
                  <th className="numeric-cell">
                    {renderSortButton("Saldo", "amount", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("amount"), true)}
                  </th>
                </tr>
              </thead>
              <tbody>
                {openReceivables.map((item) => (
                  <tr key={`${item.client_name}-${item.invoice_number}-${item.installment}-${item.due_date ?? "-"}`}>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="billing-open-receivables-client-cell" title={item.client_name ?? "-"}>
                      {item.client_name ?? "-"}
                    </td>
                    <td
                      className="billing-open-receivables-title-cell"
                      title={`${item.invoice_number || "Sem numero"}/${item.installment || "-"}`}
                    >
                      {`${item.invoice_number || "Sem numero"}/${item.installment || "-"}`}
                    </td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td className="numeric-cell">{formatMoney(item.corrected_amount || item.amount)}</td>
                  </tr>
                ))}
                {!openReceivables.length && (
                  <tr>
                    <td className="empty-cell" colSpan={5}>Nenhuma fatura em aberto encontrada.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      );
    }

    if (invoiceFilter === "overdue") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Boletos atrasados</h3>
            <span>{dashboard.overdue_boletos.length}</span>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table entries-list-table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Modo</th>
                  <th>Banco</th>
                  <th>Vencimento</th>
                  <th>Atraso</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Status</th>
                  <th>Faturas</th>
                  <th>Boleto</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.overdue_boletos.map((item, index) => (
                  <tr key={`${item.client_name}-${item.due_date}-${index}`}>
                    <td>{item.client_name}</td>
                    <td>{item.mode || "-"}</td>
                    <td>{item.bank || "-"}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td>{item.days_overdue}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td>{renderReceivableDetails(item)}</td>
                    <td>{renderBoletoActions(item.boletos)}</td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
                {!dashboard.overdue_boletos.length && (
                  <tr>
                    <td colSpan={10}>Nenhum boleto atrasado encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      );
    }

    if (invoiceFilter === "paid-pending") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Pagas sem baixa</h3>
            <span>{dashboard.paid_pending.length}</span>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table entries-list-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Cliente</th>
                  <th>Modo</th>
                  <th>Competencia</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Faturas</th>
                  <th>Boleto</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.paid_pending.map((item, index) => (
                  <tr key={`${item.client_name}-${item.competence}-${index}`}>
                    <td>{item.type}</td>
                    <td>{item.client_name}</td>
                    <td>{item.mode || "-"}</td>
                    <td>{item.competence || "-"}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{renderReceivableDetails(item)}</td>
                    <td>{renderBoletoActions(item.boletos, { showPdfAction: false })}</td>
                  </tr>
                ))}
                {!dashboard.paid_pending.length && (
                  <tr>
                    <td colSpan={7}>Nenhum pagamento sem baixa encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      );
    }

    if (invoiceFilter === "excess") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Boletos em excesso</h3>
            <span>{dashboard.excess_boletos.length}</span>
          </div>
          <div className="table-shell tall entries-table-shell">
            <table className="erp-table entries-list-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Cliente</th>
                  <th>Modo</th>
                  <th>Competencia</th>
                  <th>Vencimento</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Status</th>
                  <th>Boleto</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.excess_boletos.map((item, index) => (
                  <tr key={`${item.client_name}-${item.competence}-${index}`}>
                    <td>{item.type}</td>
                    <td>{item.client_name}</td>
                    <td>{item.mode || "-"}</td>
                    <td>{item.competence || "-"}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td>{renderBoletoActions(item.boletos)}</td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
                {!dashboard.excess_boletos.length && (
                  <tr>
                    <td colSpan={9}>Nenhum boleto em excesso encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      );
    }

    if (invoiceFilter === "open-boletos") {
      return (
        <section className="panel compact-panel-card billing-open-boletos-panel">
          <div className="panel-title compact-title-row billing-open-boletos-header">
            <div>
              <h3>Boletos em aberto</h3>
              <small className="compact-muted">
                {selectedOpenBoletoIds.length} selecionado(s) para download
              </small>
            </div>
            <div className="action-row billing-open-boletos-actions">
              <label className="billing-search-field">
                <span>Buscar</span>
                <input
                  placeholder="Cliente, documento, linha digitável..."
                  type="search"
                  value={openBoletoSearch}
                  onChange={(event) => setOpenBoletoSearch(event.target.value)}
                />
              </label>
              <label className="billing-search-field billing-search-field--compact">
                <span>Banco</span>
                <select value={openBoletoBankFilter} onChange={(event) => setOpenBoletoBankFilter(event.target.value)}>
                  <option value="all">Todos</option>
                  {availableOpenBoletoBanks.map((bank) => (
                    <option key={bank} value={bank}>
                      {bank}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary-button"
                disabled={submitting || !selectedOpenBoletoIds.length}
                onClick={() => void onDownloadInterBoletoPdfBatch(selectedOpenBoletoIds)}
                type="button"
              >
                Baixar selecionados
              </button>
              <span className="billing-open-boletos-count">{filteredOpenBoletos.length}</span>
            </div>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell billing-open-boletos-table-shell">
            <table className="erp-table entries-list-table billing-open-boletos-table">
              <thead>
                <tr>
                  <th>
                    <input
                      checked={
                        !!downloadableOpenBoletos.length &&
                        downloadableOpenBoletos.every((item) => selectedOpenBoletoIds.includes(item.id))
                      }
                      disabled={submitting || !downloadableOpenBoletos.length}
                      onChange={(event) =>
                        setSelectedOpenBoletoIds(event.target.checked ? downloadableOpenBoletos.map((item) => item.id) : [])
                      }
                      type="checkbox"
                    />
                  </th>
                  <th>{renderSortButton("Cliente", "client_name", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("client_name"))}</th>
                  <th>{renderSortButton("Documento", "document_id", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("document_id"))}</th>
                  <th>{renderSortButton("Emissão", "issue_date", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("issue_date"))}</th>
                  <th>{renderSortButton("Vencimento", "due_date", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("due_date"))}</th>
                  <th className="numeric-cell">
                    {renderSortButton("Valor", "amount", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("amount"), true)}
                  </th>
                  <th>Status</th>
                  <th>{renderSortButton("Banco", "bank", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("bank"))}</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredOpenBoletos.map((item) => (
                  <tr key={item.id}>
                    <td className="billing-open-boletos-select-cell">
                      <input
                        checked={selectedOpenBoletoIds.includes(item.id)}
                        disabled={submitting || !item.pdf_available}
                        onChange={() => toggleOpenBoletoSelection(item.id)}
                        type="checkbox"
                      />
                    </td>
                    <td>{item.client_name}</td>
                    <td>
                      <strong>{item.document_id || "-"}</strong>
                    </td>
                    <td>{formatDate(item.issue_date)}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td>{item.bank}</td>
                    <td className="billing-open-boletos-actions-cell">
                      <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
                        {item.pdf_available ? (
                          <button
                            className="table-button icon-only-button"
                            disabled={submitting}
                            onClick={() => void onDownloadInterBoletoPdf(item.id)}
                            title="Baixar PDF do boleto"
                            type="button"
                          >
                            <DownloadIcon />
                          </button>
                        ) : null}
                        {canReceiveInterBoleto(item) ? (
                          <button
                            className="table-button icon-only-button"
                            disabled={submitting}
                            onClick={() => handleReceiveInterBoleto(item)}
                            title="Baixar no sandbox"
                            type="button"
                          >
                            <CheckIcon />
                          </button>
                        ) : null}
                        {canCancelInterBoleto(item) ? (
                          <button
                            className="table-button icon-only-button"
                            disabled={submitting}
                            onClick={() => handleCancelInterBoleto(item)}
                            title="Cancelar boleto no Inter"
                            type="button"
                          >
                            <CancelIcon />
                          </button>
                        ) : null}
                        {!item.pdf_available && !canReceiveInterBoleto(item) && !canCancelInterBoleto(item) ? (
                          <small className="compact-muted">Não disponível</small>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredOpenBoletos.length && (
                  <tr>
                    <td colSpan={9}>Nenhum boleto em aberto encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      );
    }

    return (
      <section className="panel compact-panel-card">
        <div className="panel-title compact-title-row">
          <div>
            <h3>Boletos faltando</h3>
            <small className="compact-muted">{selectedMissingKeys.length} selecionado(s)</small>
          </div>
          <div className="action-row">
            <button className="secondary-button" disabled={submitting} onClick={() => setClientsModalOpen(true)} type="button">
              Clientes
            </button>
            <button className="secondary-button" disabled={submitting} onClick={() => setC6ModalOpen(true)} type="button">
              Relatório C6
            </button>
            <label className="checkbox-line compact-inline">
              <input
                checked={showAllMonthlyMissingBoletos}
                disabled={submitting}
                onChange={(event) => void onToggleAllMonthlyMissingBoletos(event.target.checked)}
                type="checkbox"
              />
              <span>Exibe todos boletos de clientes mensal</span>
            </label>
            {showMissingExportFallback ? (
              <button
                className="ghost-button billing-secondary-action"
                disabled={submitting || !selectedMissingKeys.length}
                onClick={() => void onExportMissingBoletos(selectedMissingKeys)}
                type="button"
              >
                Gerar XLSX
              </button>
            ) : null}
            <button
              className="primary-button"
              disabled={submitting || !selectedMissingKeys.length || !hasInterApiAccount}
              onClick={() => void handleIssueMissingBoletos()}
              type="button"
            >
              Emitir no Inter
            </button>
            <span>{dashboard.missing_boletos.length}</span>
          </div>
        </div>
        <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
          <table className="erp-table entries-list-table billing-missing-table">
            <thead>
              <tr>
                <th>
                  <input
                    checked={
                      !!dashboard.missing_boletos.length &&
                      dashboard.missing_boletos.every((item) => selectedMissingKeys.includes(item.selection_key))
                    }
                    disabled={submitting || !dashboard.missing_boletos.length}
                    onChange={(event) =>
                      setSelectedMissingKeys(event.target.checked ? dashboard.missing_boletos.map((item) => item.selection_key) : [])
                    }
                    type="checkbox"
                  />
                </th>
                <th>Tipo</th>
                <th>Cliente</th>
                <th>Modo</th>
                <th>Competencia</th>
                <th>Vencimento</th>
                <th className="numeric-cell">Valor</th>
                <th>Faturas</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.missing_boletos.map((item) => (
                <tr key={item.selection_key}>
                  <td>
                    <input
                      checked={selectedMissingKeys.includes(item.selection_key)}
                      disabled={submitting}
                      onChange={() => toggleMissingSelection(item.selection_key)}
                      type="checkbox"
                    />
                  </td>
                  <td>{item.type}</td>
                  <td>{item.client_name}</td>
                  <td>{item.mode || "-"}</td>
                  <td>{item.competence || "-"}</td>
                  <td>{formatDate(item.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(item.amount)}</td>
                  <td>{renderReceivableDetails(item)}</td>
                  <td>{item.reason}</td>
                </tr>
              ))}
              {!dashboard.missing_boletos.length && (
                <tr>
                  <td colSpan={9}>Nenhum boleto faltando encontrado.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  return (
    <div className="page-layout">
      {view === "standalone" && (
        <>
          <section className="panel compact-panel-card">
            <div className="panel-title compact-title-row">
              <h3>Controle dos boletos avulsos</h3>
              <div className="action-row">
                <label className="compact-inline">
                  <span>Status</span>
                  <select
                    disabled={submitting}
                    onChange={(event) => setStandaloneBoletoFilter(event.target.value as StandaloneBoletoFilter)}
                    value={standaloneBoletoFilter}
                  >
                    <option value="open">Em aberto</option>
                    <option value="paid">Pagos</option>
                    <option value="downloaded">Baixados</option>
                    <option value="cancelled">Cancelados</option>
                    <option value="all">Todos</option>
                  </select>
                </label>
                <button
                  className="secondary-button"
                  disabled={submitting || !hasInterApiAccount}
                  onClick={() => void onSyncStandaloneBoletos()}
                  type="button"
                >
                  Atualizar Inter
                </button>
                <button
                  className="primary-button"
                  disabled={submitting}
                  onClick={openStandaloneBoletoModal}
                  type="button"
                >
                  Novo boleto avulso
                </button>
                <span>{visibleStandaloneBoletos.length}</span>
              </div>
            </div>
            <div className="table-shell tall">
              <table className="erp-table">
                <thead>
                  <tr>
                    <th>Cliente</th>
                    <th>Documento</th>
                    <th>Descrição</th>
                    <th>Emissão</th>
                    <th>Vencimento</th>
                    <th className="numeric-cell">Valor</th>
                    <th>Banco</th>
                    <th>Status banco</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStandaloneBoletos.map((item) => (
                    <tr key={item.id}>
                      <td>{item.client_name}</td>
                      <td>{item.document_id}</td>
                      <td>{item.description || "-"}</td>
                      <td>{formatDate(item.issue_date)}</td>
                      <td>{formatDate(item.due_date)}</td>
                      <td className="numeric-cell">{formatMoney(item.amount)}</td>
                      <td>{item.bank}</td>
                      <td>{item.status}</td>
                      <td className="billing-open-boletos-actions-cell">
                        <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
                          {item.pdf_available ? (
                            <button
                              className="table-button icon-only-button"
                              disabled={submitting}
                              onClick={() => void onDownloadStandaloneBoletoPdf(item.id)}
                              title="Baixar PDF do boleto avulso"
                              type="button"
                            >
                              <DownloadIcon />
                            </button>
                          ) : null}
                          <button
                            className="table-button icon-only-button"
                            disabled={submitting}
                            onClick={() => void onMarkStandaloneBoletoDownloaded(item.id)}
                            title="Marcar boleto avulso como baixado"
                            type="button"
                          >
                            <CheckIcon />
                          </button>
                          {canCancelStandaloneBoleto(item) ? (
                            <button
                              className="table-button icon-only-button"
                              disabled={submitting}
                              onClick={() => handleCancelStandaloneBoleto(item)}
                              title="Cancelar boleto avulso no Inter"
                              type="button"
                            >
                              <CancelIcon />
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!visibleStandaloneBoletos.length && (
                    <tr>
                      <td colSpan={9}>Nenhum boleto avulso em {formatStandaloneBoletoFilterLabel(standaloneBoletoFilter).toLowerCase()}.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {false && (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Cadastro de clientes</h3>
            <div className="action-row">
              <button className="secondary-button" disabled={submitting} onClick={() => setCustomerDataModalOpen(true)} type="button">
                Atualizar dados dos clientes
              </button>
              <button className="primary-button" disabled={submitting} onClick={() => void handleSaveClients()} type="button">
                Salvar configurações
              </button>
            </div>
          </div>
          <div className="table-shell tall">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Faturas</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Usa boleto</th>
                  <th>Modo</th>
                  <th>Dia</th>
                  <th>Cobrar multa/juros</th>
                  <th>Baixas pendentes</th>
                  <th>Observações</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.client_key}>
                    <td>
                      <strong className="single-line-cell" title={client.client_name}>
                        {client.client_name}
                      </strong>
                    </td>
                    <td>{client.receivable_count}</td>
                    <td className="numeric-cell">{formatMoney(client.total_amount)}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.uses_boleto}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, uses_boleto: event.target.checked, dirty: true } : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={client.mode}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, mode: event.target.value, dirty: true } : item,
                            ),
                          )
                        }
                      >
                        <option value="individual">Individual</option>
                        <option value="mensal">Mensal</option>
                        <option value="negociacao">Negociacao</option>
                      </select>
                    </td>
                    <td>
                      <input
                        className="mini-input"
                        type="number"
                        min={1}
                        max={31}
                        value={client.boleto_due_day ?? ""}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key
                                ? { ...item, boleto_due_day: event.target.value ? Number(event.target.value) : null, dirty: true }
                                : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.include_interest}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key
                                ? { ...item, include_interest: event.target.checked, dirty: true }
                                : item,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>{client.matched_paid_count}</td>
                    <td>
                      <input
                        value={client.notes ?? ""}
                        onChange={(event) =>
                          setClients((current) =>
                            current.map((item) =>
                              item.client_key === client.client_key ? { ...item, notes: event.target.value, dirty: true } : item,
                            ),
                          )
                        }
                      />
                    </td>
                  </tr>
                ))}
                {!clients.length && (
                  <tr>
                    <td colSpan={9}>Nenhum cliente encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {view !== "standalone" && (
        <>
          {renderInvoicePanel()}
        </>
      )}

      {renderClientsModal()}
      {renderC6UploadModal()}
      {renderCustomerDataModal()}
      {renderStandaloneBoletoModal()}
    </div>
  );
}


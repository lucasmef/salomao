import { useEffect, useMemo, useState } from "react";
import { MoneyInput } from "../components/MoneyInput";
import { ModalCloseButton } from "../components/ModalCloseButton";
import { Button } from "../components/ui";
import { formatDate, formatEntryStatus, formatMoney } from "../lib/format";
import { normalizePtBrMoneyInput } from "../lib/money";
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
type OpenBoletoSort = "due_date" | "issue_date" | "client_name" | "bank" | "amount" | "document_id" | "status";
type StandaloneBoletoFilter = "all" | "open" | "paid" | "downloaded" | "cancelled";
type SortDirection = "asc" | "desc";
type OpenReceivableDateFilters = {
  start: string;
  end: string;
};
type OpenBoletoDateFilters = {
  start: string;
  end: string;
};
type OpenBoletoColumnFilter = "status" | "bank" | null;
type BillingAlertSort =
  | "client_name"
  | "mode"
  | "type"
  | "competence"
  | "due_date"
  | "days_overdue"
  | "amount"
  | "status"
  | "bank"
  | "receivables"
  | "reason";
type StandaloneBoletoSort =
  | "client_name"
  | "document_id"
  | "issue_date"
  | "due_date"
  | "amount"
  | "bank"
  | "status";

function getTodayInputDate() {
  return new Date().toISOString().slice(0, 10);
}

function uniqueStandaloneClientNames(clients: BoletoClient[]) {
  return Array.from(new Set(clients.map((item) => String(item?.client_name ?? "").trim()).filter(Boolean))).sort((left, right) =>
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

function renderStatusBadge(status: string) {
  const label = formatEntryStatus(status);
  let tone: "success" | "warning" | "danger" | "neutral" = "neutral";

  switch (status) {
    case "settled":
    case "paid":
    case "Recebido por boleto":
      tone = "success";
      break;
    case "overdue":
    case "missing":
    case "cancelled":
    case "Cancelado":
      tone = "danger";
      break;
    case "open":
    case "partial":
    case "planned":
    case "Aberto":
    case "Em processamento":
      tone = "warning";
      break;
  }

  return <span className={`badge badge-${tone}`}>{label}</span>;
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

function compareMultiSelectValues(
  left: string[] | null,
  right: string[] | null,
  availableValues: string[],
) {
  const leftValues = left ?? availableValues;
  const rightValues = right ?? availableValues;
  return {
    leftValues,
    rightValues,
    leftAllSelected: left === null || leftValues.length === availableValues.length,
    rightAllSelected: right === null || rightValues.length === availableValues.length,
  };
}

function toggleMultiSelectValue(
  current: string[] | null,
  value: string,
  availableValues: string[],
) {
  const currentValues = current ?? availableValues;
  const exists = currentValues.includes(value);
  const nextValues = exists ? currentValues.filter((item) => item !== value) : [...currentValues, value];
  if (nextValues.length === availableValues.length) {
    return null;
  }
  return nextValues;
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
  const [openBoletoBankFilter, setOpenBoletoBankFilter] = useState<string[] | null>(null);
  const [openBoletoStatusFilter, setOpenBoletoStatusFilter] = useState<string[] | null>(null);
  const [openReceivableFilterDraft, setOpenReceivableFilterDraft] = useState<OpenReceivableDateFilters>({ start: "", end: "" });
  const [openReceivableFilters, setOpenReceivableFilters] = useState<OpenReceivableDateFilters>({ start: "", end: "" });
  const [openBoletoFilterDraft, setOpenBoletoFilterDraft] = useState<OpenBoletoDateFilters>({ start: "", end: "" });
  const [openBoletoFilters, setOpenBoletoFilters] = useState<OpenBoletoDateFilters>({ start: "", end: "" });
  const [openReceivableSort, setOpenReceivableSort] = useState<OpenReceivableSort>("due_date");
  const [openReceivableSortDirection, setOpenReceivableSortDirection] = useState<SortDirection>("asc");
  const [openBoletoSort, setOpenBoletoSort] = useState<OpenBoletoSort>("issue_date");
  const [openBoletoSortDirection, setOpenBoletoSortDirection] = useState<SortDirection>("desc");
  const [overdueSort, setOverdueSort] = useState<BillingAlertSort>("due_date");
  const [overdueSortDirection, setOverdueSortDirection] = useState<SortDirection>("asc");
  const [paidPendingSort, setPaidPendingSort] = useState<BillingAlertSort>("client_name");
  const [paidPendingSortDirection, setPaidPendingSortDirection] = useState<SortDirection>("asc");
  const [missingSort, setMissingSort] = useState<BillingAlertSort>("due_date");
  const [missingSortDirection, setMissingSortDirection] = useState<SortDirection>("asc");
  const [excessSort, setExcessSort] = useState<BillingAlertSort>("due_date");
  const [excessSortDirection, setExcessSortDirection] = useState<SortDirection>("asc");
  const [standaloneSort, setStandaloneSort] = useState<StandaloneBoletoSort>("due_date");
  const [standaloneSortDirection, setStandaloneSortDirection] = useState<SortDirection>("asc");
  const [showOpenReceivablePeriodPopover, setShowOpenReceivablePeriodPopover] = useState(false);
  const [showOpenReceivablePresetMenu, setShowOpenReceivablePresetMenu] = useState(false);
  const [showOpenBoletoPeriodPopover, setShowOpenBoletoPeriodPopover] = useState(false);
  const [showOpenBoletoPresetMenu, setShowOpenBoletoPresetMenu] = useState(false);
  const [openBoletoColumnFilter, setOpenBoletoColumnFilter] = useState<OpenBoletoColumnFilter>(null);
  const [standaloneBoletoDraft, setStandaloneBoletoDraft] = useState<StandaloneBoletoDraft>({
    account_id: "",
    client_name: "",
    amount: "",
    due_date: "",
    notes: "",
  });
  const [standaloneBoletoFilter, setStandaloneBoletoFilter] = useState<StandaloneBoletoFilter>("open");
  const invoiceFilter = view === "standalone" ? "open" : view;

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
  const availableOpenBoletoStatuses = useMemo(
    () => [...new Set(dashboard.open_boletos.map((item) => item.status).filter(Boolean))].sort((left, right) => left.localeCompare(right, "pt-BR")),
    [dashboard.open_boletos],
  );
  const availableOpenBoletoBanks = useMemo(
    () => [...new Set(dashboard.open_boletos.map((item) => item.bank).filter(Boolean))].sort((left, right) => left.localeCompare(right, "pt-BR")),
    [dashboard.open_boletos],
  );
  const visibleOpenBoletoStatuses = openBoletoStatusFilter ?? availableOpenBoletoStatuses;
  const visibleOpenBoletoBanks = openBoletoBankFilter ?? availableOpenBoletoBanks;
  const filteredOpenBoletos = useMemo(
    () =>
      dashboard.open_boletos
        .filter((item) => boletoMatchesQuery(item, openBoletoSearch))
        .filter((item) => {
          if (!openBoletoFilters.start && !openBoletoFilters.end) {
            return true;
          }
          if (!item.due_date) {
            return false;
          }
          if (openBoletoFilters.start && item.due_date < openBoletoFilters.start) {
            return false;
          }
          if (openBoletoFilters.end && item.due_date > openBoletoFilters.end) {
            return false;
          }
          return true;
        })
        .filter((item) => visibleOpenBoletoStatuses.length > 0 && visibleOpenBoletoStatuses.includes(item.status))
        .filter((item) => visibleOpenBoletoBanks.length > 0 && visibleOpenBoletoBanks.includes(item.bank))
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
              case "status":
                return compareText(left.status, right.status);
              case "due_date":
              default:
                return compareText(left.due_date, right.due_date);
            }
          })();
          return openBoletoSortDirection === "asc" ? result : -result;
        }),
    [
      dashboard.open_boletos,
      openBoletoFilters.end,
      openBoletoFilters.start,
      openBoletoSearch,
      openBoletoSort,
      openBoletoSortDirection,
      visibleOpenBoletoBanks,
      visibleOpenBoletoStatuses,
    ],
  );
  const downloadableOpenBoletos = useMemo(
    () => filteredOpenBoletos.filter((item) => item.pdf_available),
    [filteredOpenBoletos],
  );
  const visibleOverdueBoletos = useMemo(
    () =>
      [...dashboard.overdue_boletos].sort((left, right) => {
        const result = (() => {
          switch (overdueSort) {
            case "client_name":
              return compareText(left.client_name, right.client_name);
            case "mode":
              return compareText(left.mode, right.mode);
            case "bank":
              return compareText(left.bank, right.bank);
            case "days_overdue":
              return compareNumber(left.days_overdue, right.days_overdue);
            case "amount":
              return compareNumber(left.amount, right.amount);
            case "status":
              return compareText(left.status, right.status);
            case "receivables":
              return compareText(renderReceivableDetails(left), renderReceivableDetails(right));
            case "due_date":
            default:
              return compareText(left.due_date, right.due_date);
          }
        })();
        return overdueSortDirection === "asc" ? result : -result;
      }),
    [dashboard.overdue_boletos, overdueSort, overdueSortDirection],
  );
  const visiblePaidPending = useMemo(
    () =>
      [...dashboard.paid_pending].sort((left, right) => {
        const result = (() => {
          switch (paidPendingSort) {
            case "type":
              return compareText(left.type, right.type);
            case "mode":
              return compareText(left.mode, right.mode);
            case "competence":
              return compareText(left.competence, right.competence);
            case "amount":
              return compareNumber(left.amount, right.amount);
            case "receivables":
              return compareText(renderReceivableDetails(left), renderReceivableDetails(right));
            case "bank":
              return compareText(left.bank, right.bank);
            case "due_date":
              return compareText(left.due_date, right.due_date);
            case "status":
              return compareText(left.status, right.status);
            case "client_name":
            default:
              return compareText(left.client_name, right.client_name);
          }
        })();
        return paidPendingSortDirection === "asc" ? result : -result;
      }),
    [dashboard.paid_pending, paidPendingSort, paidPendingSortDirection],
  );
  const visibleMissingBoletos = useMemo(
    () =>
      [...dashboard.missing_boletos].sort((left, right) => {
        const result = (() => {
          switch (missingSort) {
            case "mode":
              return compareText(left.mode, right.mode);
            case "competence":
              return compareText(left.competence, right.competence);
            case "amount":
              return compareNumber(left.amount, right.amount);
            case "receivables":
              return compareText(renderReceivableDetails(left), renderReceivableDetails(right));
            case "reason":
              return compareText(left.reason, right.reason);
            case "client_name":
              return compareText(left.client_name, right.client_name);
            case "due_date":
            default:
              return compareText(left.due_date, right.due_date);
          }
        })();
        return missingSortDirection === "asc" ? result : -result;
      }),
    [dashboard.missing_boletos, missingSort, missingSortDirection],
  );
  const visibleExcessBoletos = useMemo(
    () =>
      [...dashboard.excess_boletos].sort((left, right) => {
        const result = (() => {
          switch (excessSort) {
            case "type":
              return compareText(left.type, right.type);
            case "mode":
              return compareText(left.mode, right.mode);
            case "competence":
              return compareText(left.competence, right.competence);
            case "amount":
              return compareNumber(left.amount, right.amount);
            case "status":
              return compareText(left.status, right.status);
            case "bank":
              return compareText(left.bank, right.bank);
            case "reason":
              return compareText(left.reason, right.reason);
            case "client_name":
              return compareText(left.client_name, right.client_name);
            case "due_date":
            default:
              return compareText(left.due_date, right.due_date);
          }
        })();
        return excessSortDirection === "asc" ? result : -result;
      }),
    [dashboard.excess_boletos, excessSort, excessSortDirection],
  );
  const visibleStandaloneBoletos = useMemo(
    () =>
      [...dashboard.standalone_boletos]
        .filter((item) => standaloneBoletoFilter === "all" || resolveStandaloneBoletoFilter(item) === standaloneBoletoFilter)
        .sort((left, right) => {
          const result = (() => {
            switch (standaloneSort) {
              case "client_name":
                return compareText(left.client_name, right.client_name);
              case "document_id":
                return compareText(left.document_id, right.document_id);
              case "issue_date":
                return compareText(left.issue_date, right.issue_date);
              case "amount":
                return compareNumber(left.amount, right.amount);
              case "bank":
                return compareText(left.bank, right.bank);
              case "status":
                return compareText(left.status, right.status);
              case "due_date":
              default:
                return compareText(left.due_date, right.due_date);
            }
          })();
          return standaloneSortDirection === "asc" ? result : -result;
        }),
    [dashboard.standalone_boletos, standaloneBoletoFilter, standaloneSort, standaloneSortDirection],
  );

  useEffect(() => {
    const visibleIds = new Set(filteredOpenBoletos.map((item) => item.id));
    setSelectedOpenBoletoIds((current) => current.filter((item) => visibleIds.has(item)));
  }, [filteredOpenBoletos]);

  useEffect(() => {
    setOpenBoletoStatusFilter((current) => {
      if (current === null) {
        return null;
      }
      return current.filter((item) => availableOpenBoletoStatuses.includes(item));
    });
  }, [availableOpenBoletoStatuses]);

  useEffect(() => {
    setOpenBoletoBankFilter((current) => {
      if (current === null) {
        return null;
      }
      return current.filter((item) => availableOpenBoletoBanks.includes(item));
    });
  }, [availableOpenBoletoBanks]);

  useEffect(() => {
    setClientsModalOpen(false);
    setC6ModalOpen(false);
    setC6File(null);
    setCustomerDataModalOpen(false);
    setStandaloneBoletoModalOpen(false);
    setCustomerDataFile(null);
    setShowOpenReceivablePeriodPopover(false);
    setShowOpenReceivablePresetMenu(false);
    setShowOpenBoletoPeriodPopover(false);
    setShowOpenBoletoPresetMenu(false);
    setOpenBoletoColumnFilter(null);
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

  function toggleOverdueSort(nextSort: BillingAlertSort) {
    if (overdueSort === nextSort) {
      setOverdueSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setOverdueSort(nextSort);
    setOverdueSortDirection("asc");
  }

  function togglePaidPendingSort(nextSort: BillingAlertSort) {
    if (paidPendingSort === nextSort) {
      setPaidPendingSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setPaidPendingSort(nextSort);
    setPaidPendingSortDirection("asc");
  }

  function toggleMissingSort(nextSort: BillingAlertSort) {
    if (missingSort === nextSort) {
      setMissingSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setMissingSort(nextSort);
    setMissingSortDirection("asc");
  }

  function toggleExcessSort(nextSort: BillingAlertSort) {
    if (excessSort === nextSort) {
      setExcessSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setExcessSort(nextSort);
    setExcessSortDirection("asc");
  }

  function toggleStandaloneSort(nextSort: StandaloneBoletoSort) {
    if (standaloneSort === nextSort) {
      setStandaloneSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setStandaloneSort(nextSort);
    setStandaloneSortDirection("asc");
  }

  function setOpenReceivableDateRange(start: string, end: string) {
    setOpenReceivableFilterDraft({ start, end });
  }

  function applyOpenReceivableDateFilters() {
    setOpenReceivableFilters(openReceivableFilterDraft);
  }

  function setOpenBoletoDateRange(start: string, end: string) {
    setOpenBoletoFilterDraft({ start, end });
  }

  function applyOpenBoletoDateFilters() {
    setOpenBoletoFilters(openBoletoFilterDraft);
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

  function applyOpenBoletoPresetRange(kind: "today" | "current_month" | "previous_month" | "current_year") {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const formatValue = (value: Date) => value.toISOString().slice(0, 10);

    if (kind === "today") {
      const current = formatValue(today);
      setOpenBoletoDateRange(current, current);
      return;
    }

    if (kind === "current_month") {
      setOpenBoletoDateRange(formatValue(new Date(year, month, 1)), formatValue(new Date(year, month + 1, 0)));
      return;
    }

    if (kind === "previous_month") {
      setOpenBoletoDateRange(formatValue(new Date(year, month - 1, 1)), formatValue(new Date(year, month, 0)));
      return;
    }

    setOpenBoletoDateRange(formatValue(new Date(year, 0, 1)), formatValue(new Date(year, 11, 31)));
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

  function renderOpenBoletoHeader(
    label: string,
    sortKey: OpenBoletoSort,
    options?: {
      numeric?: boolean;
      filter?: OpenBoletoColumnFilter;
      filterLabel?: string;
      values?: string[];
      selectedValues?: string[] | null;
      onToggleValue?: (value: string) => void;
      onToggleAll?: () => void;
    },
  ) {
    const numeric = options?.numeric ?? false;
    const filter = options?.filter ?? null;
    const availableValues = options?.values ?? [];
    const currentValues = options?.selectedValues ?? null;
    const { leftValues, leftAllSelected } = compareMultiSelectValues(currentValues, currentValues, availableValues);

    return (
      <div className={`finance-open-items-table-header ${numeric ? "is-numeric" : ""}`.trim()}>
        {renderSortButton(label, sortKey, openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort(sortKey), numeric)}
        {filter ? (
          <div className="billing-column-filter-wrap">
            <button
              aria-label={options?.filterLabel ?? `Filtrar ${label}`}
              className={`entries-column-filter-trigger ${openBoletoColumnFilter === filter ? "is-active" : ""}`.trim()}
              onClick={() => setOpenBoletoColumnFilter((current) => (current === filter ? null : filter))}
              type="button"
            >
              <FilterFunnelIcon />
            </button>
            {openBoletoColumnFilter === filter ? (
              <div className="entries-floating-panel finance-open-items-filter-popover billing-column-filter-popover">
                <div className="entries-category-filter-head">
                  <strong>{options?.filterLabel ?? `Filtrar ${label}`}</strong>
                </div>
                <div className="entries-category-filter-list">
                  <label className="entries-category-filter-option is-all">
                    <input checked={leftAllSelected} onChange={() => options?.onToggleAll?.()} type="checkbox" />
                    <div className="entries-category-filter-text">
                      <strong>Selecionar tudo</strong>
                    </div>
                  </label>
                  {availableValues.map((value) => (
                    <label className="entries-category-filter-option" key={value}>
                      <input checked={leftValues.includes(value)} onChange={() => options?.onToggleValue?.(value)} type="checkbox" />
                      <div className="entries-category-filter-text">
                        <strong>{value}</strong>
                      </div>
                    </label>
                  ))}
                  {!availableValues.length ? <p className="entries-category-filter-empty">Nenhum valor encontrado.</p> : null}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
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
    const clientName = String(standaloneBoletoDraft.client_name ?? "").trim();
    const amount = normalizePtBrMoneyInput(standaloneBoletoDraft.amount);
    const notes = String(standaloneBoletoDraft.notes ?? "").trim();
    await onCreateStandaloneBoleto({
      account_id: standaloneBoletoDraft.account_id || null,
      client_name: clientName,
      amount,
      due_date: standaloneBoletoDraft.due_date,
      notes: notes || null,
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
    await onIssueInterCharges(selectedMissingKeys);
  }

  async function handleUploadC6() {
    if (!c6File) return;
    await onUploadBoletoC6(c6File);
    setC6File(null);
    setC6ModalOpen(false);
  }

  async function handleUploadCustomerData() {
    if (!customerDataFile) return;
    await onUploadClientData(customerDataFile);
    setCustomerDataFile(null);
    setCustomerDataModalOpen(false);
  }

  function renderInvoicePanel() {
    if (invoiceFilter === "open") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Faturas em aberto</h3>
            <div className="action-row">
              <div className="entries-period-group">
                <button
                  aria-expanded={showOpenReceivablePeriodPopover}
                  aria-label="Selecionar período"
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
                {showOpenReceivablePeriodPopover ? (
                  <div className="entries-floating-panel entries-period-popover">
                    <div className="entries-period-fields">
                      <label>
                        Início
                        <input
                          disabled={submitting}
                          type="date"
                          value={openReceivableFilterDraft.start}
                          onChange={(event) => setOpenReceivableDateRange(event.target.value, openReceivableFilterDraft.end)}
                        />
                      </label>
                      <label>
                        Fim
                        <input
                          disabled={submitting}
                          type="date"
                          value={openReceivableFilterDraft.end}
                          onChange={(event) => setOpenReceivableDateRange(openReceivableFilterDraft.start, event.target.value)}
                        />
                      </label>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="entries-toolbar-icon-wrap">
                <button
                  aria-expanded={showOpenReceivablePresetMenu}
                  aria-label="Filtros pré-definidos de data"
                  className={`entries-toolbar-icon ${showOpenReceivablePresetMenu ? "is-active" : ""}`}
                  disabled={submitting}
                  onClick={() => {
                    setShowOpenReceivablePeriodPopover(false);
                    setShowOpenReceivablePresetMenu((current) => !current);
                  }}
                  type="button"
                >
                  <FilterFunnelIcon />
                </button>
                {showOpenReceivablePresetMenu ? (
                  <div className="entries-floating-panel entries-icon-menu">
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("today"); setShowOpenReceivablePresetMenu(false); }} type="button">Hoje</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("current_month"); setShowOpenReceivablePresetMenu(false); }} type="button">Mês atual</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("previous_month"); setShowOpenReceivablePresetMenu(false); }} type="button">Mês anterior</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenReceivablePresetRange("current_year"); setShowOpenReceivablePresetMenu(false); }} type="button">Ano atual</button>
                  </div>
                ) : null}
              </div>
              <Button type="button" variant="primary" size="sm" loading={submitting} disabled={submitting} onClick={applyOpenReceivableDateFilters}>
                Aplicar
              </Button>
              <span>{openReceivables.length}</span>
            </div>
          </div>
          <div className="table-shell table-shell--scroll billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-open-receivables-table">
              <thead>
                <tr>
                  <th>{renderSortButton("Vencimento", "due_date", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("due_date"))}</th>
                  <th>{renderSortButton("Cliente", "client_name", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("client_name"))}</th>
                  <th>{renderSortButton("Título", "document", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("document"))}</th>
                  <th>{renderSortButton("Status", "status", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("status"))}</th>
                  <th className="numeric-cell">{renderSortButton("Saldo", "amount", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("amount"), true)}</th>
                </tr>
              </thead>
              <tbody>
                {openReceivables.map((item) => (
                  <tr key={`${item.client_name}-${item.invoice_number}-${item.installment}`}>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="billing-open-receivables-client-cell">{item.client_name}</td>
                    <td>{`${item.invoice_number || "Sem numero"}/${item.installment || "-"}`}</td>
                    <td>{renderStatusBadge(item.status)}</td>
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
            <span>{visibleOverdueBoletos.length}</span>
          </div>
          <div className="table-shell table-shell--scroll billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-alert-table">
              <thead>
                <tr>
                  <th>{renderSortButton("Cliente", "client_name", overdueSort, overdueSortDirection, () => toggleOverdueSort("client_name"))}</th>
                  <th className="col-hide-md">{renderSortButton("Modo", "mode", overdueSort, overdueSortDirection, () => toggleOverdueSort("mode"))}</th>
                  <th className="col-hide-md">{renderSortButton("Banco", "bank", overdueSort, overdueSortDirection, () => toggleOverdueSort("bank"))}</th>
                  <th>{renderSortButton("Vencimento", "due_date", overdueSort, overdueSortDirection, () => toggleOverdueSort("due_date"))}</th>
                  <th className="col-hide-md">{renderSortButton("Atraso", "days_overdue", overdueSort, overdueSortDirection, () => toggleOverdueSort("days_overdue"))}</th>
                  <th className="numeric-cell">{renderSortButton("Valor", "amount", overdueSort, overdueSortDirection, () => toggleOverdueSort("amount"), true)}</th>
                  <th>{renderSortButton("Status", "status", overdueSort, overdueSortDirection, () => toggleOverdueSort("status"))}</th>
                  <th>{renderSortButton("Faturas", "receivables", overdueSort, overdueSortDirection, () => toggleOverdueSort("receivables"))}</th>
                  <th>Boleto</th>
                </tr>
              </thead>
              <tbody>
                {visibleOverdueBoletos.map((item, index) => (
                  <tr key={index}>
                    <td>{item.client_name}</td>
                    <td className="col-hide-md">{item.mode || "-"}</td>
                    <td className="col-hide-md">{item.bank || "-"}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="col-hide-md">{item.days_overdue}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{renderStatusBadge(item.status)}</td>
                    <td>{renderReceivableDetails(item)}</td>
                    <td>{renderBoletoActions(item.boletos)}</td>
                  </tr>
                ))}
                {!visibleOverdueBoletos.length && (
                  <tr>
                    <td className="empty-cell" colSpan={9}>Nenhum boleto atrasado encontrado.</td>
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
            <span>{visiblePaidPending.length}</span>
          </div>
          <div className="table-shell table-shell--scroll billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-alert-table">
              <colgroup>
                <col className="billing-alert-col-type" />
                <col className="billing-alert-col-client" />
                <col className="billing-alert-col-mode" />
                <col className="billing-alert-col-competence" />
                <col className="billing-alert-col-amount" />
                <col className="billing-alert-col-receivables" />
                <col className="billing-alert-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th className="col-hide-md">{renderSortButton("Tipo", "type", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("type"))}</th>
                  <th>{renderSortButton("Cliente", "client_name", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("client_name"))}</th>
                  <th className="col-hide-md">{renderSortButton("Modo", "mode", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("mode"))}</th>
                  <th>{renderSortButton("Competência", "competence", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("competence"))}</th>
                  <th className="numeric-cell">{renderSortButton("Valor", "amount", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("amount"), true)}</th>
                  <th>{renderSortButton("Faturas", "receivables", paidPendingSort, paidPendingSortDirection, () => togglePaidPendingSort("receivables"))}</th>
                  <th>Boleto</th>
                </tr>
              </thead>
              <tbody>
                {visiblePaidPending.map((item, index) => (
                  <tr key={`${item.client_name}-${item.competence}-${index}`}>
                    <td className="col-hide-md">{item.type}</td>
                    <td>{item.client_name}</td>
                    <td className="col-hide-md">{item.mode || "-"}</td>
                    <td>{item.competence || "-"}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{renderReceivableDetails(item)}</td>
                    <td>{renderBoletoActions(item.boletos, { showPdfAction: false })}</td>
                  </tr>
                ))}
                {!visiblePaidPending.length && (
                  <tr>
                    <td className="empty-cell" colSpan={7}>Nenhum pagamento sem baixa encontrado.</td>
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
            <span>{visibleExcessBoletos.length}</span>
          </div>
          <div className="table-shell table-shell--scroll billing-table-shell billing-table-shell--expanded entries-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-alert-table">
              <colgroup>
                <col className="billing-alert-col-type" />
                <col className="billing-alert-col-client" />
                <col className="billing-alert-col-mode" />
                <col className="billing-alert-col-competence" />
                <col className="billing-alert-col-due-date" />
                <col className="billing-alert-col-amount" />
                <col className="billing-alert-col-status" />
                <col className="billing-alert-col-boleto" />
                <col className="billing-alert-col-reason" />
              </colgroup>
              <thead>
                <tr>
                  <th className="col-hide-md">{renderSortButton("Tipo", "type", excessSort, excessSortDirection, () => toggleExcessSort("type"))}</th>
                  <th>{renderSortButton("Cliente", "client_name", excessSort, excessSortDirection, () => toggleExcessSort("client_name"))}</th>
                  <th className="col-hide-md">{renderSortButton("Modo", "mode", excessSort, excessSortDirection, () => toggleExcessSort("mode"))}</th>
                  <th className="col-hide-md">{renderSortButton("Competência", "competence", excessSort, excessSortDirection, () => toggleExcessSort("competence"))}</th>
                  <th>{renderSortButton("Vencimento", "due_date", excessSort, excessSortDirection, () => toggleExcessSort("due_date"))}</th>
                  <th className="numeric-cell">{renderSortButton("Valor", "amount", excessSort, excessSortDirection, () => toggleExcessSort("amount"), true)}</th>
                  <th>{renderSortButton("Status", "status", excessSort, excessSortDirection, () => toggleExcessSort("status"))}</th>
                  <th>Boleto</th>
                  <th>{renderSortButton("Motivo", "reason", excessSort, excessSortDirection, () => toggleExcessSort("reason"))}</th>
                </tr>
              </thead>
              <tbody>
                {visibleExcessBoletos.map((item, index) => (
                  <tr key={`${item.client_name}-${item.competence}-${index}`}>
                    <td className="col-hide-md">{item.type}</td>
                    <td>{item.client_name}</td>
                    <td className="col-hide-md">{item.mode || "-"}</td>
                    <td className="col-hide-md">{item.competence || "-"}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{renderStatusBadge(item.status)}</td>
                    <td>{renderBoletoActions(item.boletos)}</td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
                {!visibleExcessBoletos.length && (
                  <tr>
                    <td className="empty-cell" colSpan={9}>Nenhum boleto em excesso encontrado.</td>
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
              <div className="entries-period-group">
                <button
                  aria-expanded={showOpenBoletoPeriodPopover}
                  aria-label="Selecionar período"
                  className={`entries-period-trigger ${showOpenBoletoPeriodPopover ? "is-active" : ""}`}
                  disabled={submitting}
                  onClick={() => {
                    setOpenBoletoColumnFilter(null);
                    setShowOpenBoletoPresetMenu(false);
                    setShowOpenBoletoPeriodPopover((current) => !current);
                  }}
                  type="button"
                >
                  <CalendarRangeIcon />
                  <span>{formatRangeLabel(openBoletoFilterDraft.start, openBoletoFilterDraft.end)}</span>
                </button>
                {showOpenBoletoPeriodPopover ? (
                  <div className="entries-floating-panel entries-period-popover">
                    <div className="entries-period-fields">
                      <label>
                        Início
                        <input
                          disabled={submitting}
                          type="date"
                          value={openBoletoFilterDraft.start}
                          onChange={(event) => setOpenBoletoDateRange(event.target.value, openBoletoFilterDraft.end)}
                        />
                      </label>
                      <label>
                        Fim
                        <input
                          disabled={submitting}
                          type="date"
                          value={openBoletoFilterDraft.end}
                          onChange={(event) => setOpenBoletoDateRange(openBoletoFilterDraft.start, event.target.value)}
                        />
                      </label>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="entries-toolbar-icon-wrap">
                <button
                  aria-expanded={showOpenBoletoPresetMenu}
                  aria-label="Filtros pré-definidos de data"
                  className={`entries-toolbar-icon ${showOpenBoletoPresetMenu ? "is-active" : ""}`}
                  disabled={submitting}
                  onClick={() => {
                    setOpenBoletoColumnFilter(null);
                    setShowOpenBoletoPeriodPopover(false);
                    setShowOpenBoletoPresetMenu((current) => !current);
                  }}
                  type="button"
                >
                  <FilterFunnelIcon />
                </button>
                {showOpenBoletoPresetMenu ? (
                  <div className="entries-floating-panel entries-icon-menu">
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenBoletoPresetRange("today"); setShowOpenBoletoPresetMenu(false); }} type="button">Hoje</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenBoletoPresetRange("current_month"); setShowOpenBoletoPresetMenu(false); }} type="button">Mês atual</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenBoletoPresetRange("previous_month"); setShowOpenBoletoPresetMenu(false); }} type="button">Mês anterior</button>
                    <button className="entries-icon-menu-item" onClick={() => { applyOpenBoletoPresetRange("current_year"); setShowOpenBoletoPresetMenu(false); }} type="button">Ano atual</button>
                  </div>
                ) : null}
              </div>
              <Button type="button" variant="primary" size="sm" loading={submitting} disabled={submitting} onClick={applyOpenBoletoDateFilters}>
                Aplicar
              </Button>
              <Button
                type="button"
                variant="secondary"
                loading={submitting}
                disabled={submitting || !selectedOpenBoletoIds.length}
                onClick={() => void onDownloadInterBoletoPdfBatch(selectedOpenBoletoIds)}
              >
                Baixar selecionados
              </Button>
              <span className="billing-open-boletos-count">{filteredOpenBoletos.length}</span>
            </div>
          </div>
          <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell billing-open-boletos-table-shell">
            <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-open-boletos-table">
              <colgroup>
                <col className="billing-open-boletos-col-select" />
                <col className="billing-open-boletos-col-client" />
                <col className="billing-open-boletos-col-document" />
                <col className="billing-open-boletos-col-issue-date" />
                <col className="billing-open-boletos-col-due-date" />
                <col className="billing-open-boletos-col-amount" />
                <col className="billing-open-boletos-col-status" />
                <col className="billing-open-boletos-col-bank" />
                <col className="billing-open-boletos-col-actions" />
              </colgroup>
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
                  <th>{renderOpenBoletoHeader("Cliente", "client_name")}</th>
                  <th>{renderOpenBoletoHeader("Documento", "document_id")}</th>
                  <th>{renderOpenBoletoHeader("Emissão", "issue_date")}</th>
                  <th>{renderOpenBoletoHeader("Vencimento", "due_date")}</th>
                  <th className="numeric-cell">
                    {renderOpenBoletoHeader("Valor", "amount", { numeric: true })}
                  </th>
                  <th>
                    {renderOpenBoletoHeader("Status", "status", {
                      filter: "status",
                      filterLabel: "Status",
                      values: availableOpenBoletoStatuses,
                      selectedValues: openBoletoStatusFilter,
                      onToggleAll: () => setOpenBoletoStatusFilter((current) => (current === null ? [] : null)),
                      onToggleValue: (value) =>
                        setOpenBoletoStatusFilter((current) => toggleMultiSelectValue(current, value, availableOpenBoletoStatuses)),
                    })}
                  </th>
                  <th>
                    {renderOpenBoletoHeader("Banco", "bank", {
                      filter: "bank",
                      filterLabel: "Banco",
                      values: availableOpenBoletoBanks,
                      selectedValues: openBoletoBankFilter,
                      onToggleAll: () => setOpenBoletoBankFilter((current) => (current === null ? [] : null)),
                      onToggleValue: (value) =>
                        setOpenBoletoBankFilter((current) => toggleMultiSelectValue(current, value, availableOpenBoletoBanks)),
                    })}
                  </th>
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
                    <td className="billing-open-boletos-client-cell" title={item.client_name}>
                      {item.client_name}
                    </td>
                    <td className="billing-open-boletos-document-cell" title={item.document_id || "-"}>
                      <strong>{item.document_id || "-"}</strong>
                    </td>
                    <td>{formatDate(item.issue_date)}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{renderStatusBadge(item.status)}</td>
                    <td>{item.bank || "-"}</td>
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
                    <td className="empty-cell" colSpan={9}>Nenhum boleto em aberto encontrado.</td>
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
            <Button type="button" variant="secondary" disabled={submitting} onClick={() => setClientsModalOpen(true)}>
              Clientes
            </Button>
            <Button type="button" variant="secondary" disabled={submitting} onClick={() => setC6ModalOpen(true)}>
              Relatório C6
            </Button>
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
              <Button
                type="button"
                variant="ghost"
                className="billing-secondary-action"
                loading={submitting}
                disabled={submitting || !selectedMissingKeys.length}
                onClick={() => void onExportMissingBoletos(selectedMissingKeys)}
              >
                Gerar XLSX
              </Button>
            ) : null}
            <Button
              type="button"
              variant="primary"
              loading={submitting}
              disabled={submitting || !selectedMissingKeys.length || !hasInterApiAccount}
              onClick={() => void handleIssueMissingBoletos()}
            >
              Emitir no Inter
            </Button>
            <span>{visibleMissingBoletos.length}</span>
          </div>
        </div>
        <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
          <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-alert-table">
            <colgroup>
              <col className="billing-alert-col-select" />
              <col className="billing-alert-col-client" />
              <col className="billing-alert-col-mode" />
              <col className="billing-alert-col-competence" />
              <col className="billing-alert-col-due-date" />
              <col className="billing-alert-col-amount" />
              <col className="billing-alert-col-receivables" />
              <col className="billing-alert-col-reason" />
            </colgroup>
            <thead>
              <tr>
                <th>
                  <input
                    checked={!!visibleMissingBoletos.length && visibleMissingBoletos.every((item) => selectedMissingKeys.includes(item.selection_key))}
                    disabled={submitting || !visibleMissingBoletos.length}
                    onChange={(event) =>
                      setSelectedMissingKeys(event.target.checked ? visibleMissingBoletos.map((item) => item.selection_key) : [])
                    }
                    type="checkbox"
                  />
                </th>
                <th>{renderSortButton("Cliente", "client_name", missingSort, missingSortDirection, () => toggleMissingSort("client_name"))}</th>
                <th>{renderSortButton("Modo", "mode", missingSort, missingSortDirection, () => toggleMissingSort("mode"))}</th>
                <th>{renderSortButton("Competência", "competence", missingSort, missingSortDirection, () => toggleMissingSort("competence"))}</th>
                <th>{renderSortButton("Vencimento", "due_date", missingSort, missingSortDirection, () => toggleMissingSort("due_date"))}</th>
                <th className="numeric-cell">{renderSortButton("Valor", "amount", missingSort, missingSortDirection, () => toggleMissingSort("amount"), true)}</th>
                <th>{renderSortButton("Faturas", "receivables", missingSort, missingSortDirection, () => toggleMissingSort("receivables"))}</th>
                <th>{renderSortButton("Motivo", "reason", missingSort, missingSortDirection, () => toggleMissingSort("reason"))}</th>
              </tr>
            </thead>
            <tbody>
              {visibleMissingBoletos.map((item) => (
                <tr key={item.selection_key}>
                  <td>
                    <input
                      checked={selectedMissingKeys.includes(item.selection_key)}
                      disabled={submitting}
                      onChange={() => toggleMissingSelection(item.selection_key)}
                      type="checkbox"
                    />
                  </td>
                  <td>{item.client_name}</td>
                  <td>{item.mode || "-"}</td>
                  <td>{item.competence || "-"}</td>
                  <td>{formatDate(item.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(item.amount)}</td>
                  <td>{renderReceivableDetails(item)}</td>
                  <td>{item.reason}</td>
                </tr>
              ))}
              {!visibleMissingBoletos.length && (
                <tr>
                  <td className="empty-cell" colSpan={8}>Nenhum boleto faltando encontrado.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  function renderStandaloneBoletoModal() {
    if (!standaloneBoletoModalOpen) return null;
    const interAccounts = accounts.filter((a) => a.is_active && a.inter_api_enabled);
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-customer-modal">
          <div className="panel-title compact-title-row">
            <h3>Novo boleto avulso</h3>
            <ModalCloseButton onClick={closeStandaloneBoletoModal} />
          </div>
          <div className="billing-standalone-form">
            <label className="billing-standalone-form-field">
              <span>Conta Inter</span>
              <select
                value={standaloneBoletoDraft.account_id}
                onChange={(e) => setStandaloneBoletoDraft({ ...standaloneBoletoDraft, account_id: e.target.value })}
              >
                <option value="">Selecione</option>
                {interAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>{acc.name}</option>
                ))}
              </select>
            </label>
            <label className="billing-standalone-form-field billing-standalone-form-field--wide">
              <span>Cliente</span>
              <input
                list="standalone-clients"
                value={standaloneBoletoDraft.client_name}
                onChange={(e) => setStandaloneBoletoDraft({ ...standaloneBoletoDraft, client_name: e.target.value })}
              />
              <datalist id="standalone-clients">
                {standaloneClientOptions.map((c) => <option key={c} value={c} />)}
              </datalist>
            </label>
            <label className="billing-standalone-form-field">
              <span>Valor</span>
              <MoneyInput
                value={standaloneBoletoDraft.amount}
                onValueChange={(v) => setStandaloneBoletoDraft({ ...standaloneBoletoDraft, amount: v })}
              />
            </label>
            <label className="billing-standalone-form-field">
              <span>Vencimento</span>
              <input
                type="date"
                value={standaloneBoletoDraft.due_date}
                onChange={(e) => setStandaloneBoletoDraft({ ...standaloneBoletoDraft, due_date: e.target.value })}
              />
            </label>
            <label className="billing-standalone-form-field billing-standalone-form-field--full">
              <span>Observações</span>
              <textarea
                value={standaloneBoletoDraft.notes}
                onChange={(e) => setStandaloneBoletoDraft({ ...standaloneBoletoDraft, notes: e.target.value })}
              />
            </label>
          </div>
          <div className="action-row">
            <Button
              type="button"
              variant="primary"
              loading={submitting}
              disabled={submitting || !standaloneBoletoDraft.client_name || !standaloneBoletoDraft.amount}
              onClick={() => void handleCreateStandaloneBoleto()}
            >
              Emitir
            </Button>
            <Button type="button" variant="ghost" onClick={closeStandaloneBoletoModal}>Cancelar</Button>
          </div>
        </div>
      </div>
    );
  }

  function renderCustomerDataModal() {
    if (!customerDataModalOpen) return null;
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card">
          <div className="panel-title compact-title-row">
            <h3>Importar dados de clientes</h3>
            <ModalCloseButton onClick={closeCustomerDataModal} />
          </div>
          <div className="billing-modal-body">
            <p>Selecione o arquivo Excel exportado do banco ou gerado pelo sistema.</p>
            <label className="billing-file-input">
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={(e) => setCustomerDataFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>
          <div className="action-row">
            <Button
              type="button"
              variant="primary"
              loading={submitting}
              disabled={submitting || !customerDataFile}
              onClick={() => void handleUploadCustomerData()}
            >
              Importar
            </Button>
            <Button type="button" variant="ghost" onClick={closeCustomerDataModal}>Cancelar</Button>
          </div>
        </div>
      </div>
    );
  }

  function renderC6UploadModal() {
    if (!c6ModalOpen) return null;
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card">
          <div className="panel-title compact-title-row">
            <h3>Importar relatório C6</h3>
            <ModalCloseButton onClick={closeC6Modal} />
          </div>
          <div className="billing-modal-body">
            <p>Selecione o relatório consolidado de boletos do C6 Bank.</p>
            <label className="billing-file-input">
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={(e) => setC6File(e.target.files?.[0] || null)}
              />
            </label>
          </div>
          <div className="action-row">
            <Button
              type="button"
              variant="primary"
              loading={submitting}
              disabled={submitting || !c6File}
              onClick={() => void handleUploadC6()}
            >
              Importar
            </Button>
            <Button type="button" variant="ghost" onClick={closeC6Modal}>Cancelar</Button>
          </div>
        </div>
      </div>
    );
  }

  function renderClientsModal() {
    if (!clientsModalOpen) return null;
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card billing-large-modal">
          <div className="panel-title compact-title-row">
            <h3>Configurações de clientes</h3>
            <ModalCloseButton onClick={() => setClientsModalOpen(false)} />
          </div>
          <div className="billing-modal-actions action-row">
            <Button type="button" variant="secondary" onClick={() => setCustomerDataModalOpen(true)}>Importar XLSX</Button>
            <Button type="button" variant="primary" onClick={() => void handleSaveClients()}>Salvar</Button>
          </div>
          <div className="table-shell billing-modal-table-shell">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Usa boleto</th>
                  <th>Modo</th>
                  <th>Dia</th>
                  <th>Multa/Juros</th>
                  <th>Notas</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.client_key}>
                    <td>{client.client_name}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.uses_boleto}
                        onChange={(e) => setClients(current => current.map(item => item.client_key === client.client_key ? { ...item, uses_boleto: e.target.checked, dirty: true } : item))}
                      />
                    </td>
                    <td>
                      <select
                        value={client.mode}
                        onChange={(e) => setClients(current => current.map(item => item.client_key === client.client_key ? { ...item, mode: e.target.value, dirty: true } : item))}
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
                        onChange={(e) => setClients(current => current.map(item => item.client_key === client.client_key ? { ...item, boleto_due_day: e.target.value ? Number(e.target.value) : null, dirty: true } : item))}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={client.include_interest}
                        onChange={(e) => setClients(current => current.map(item => item.client_key === client.client_key ? { ...item, include_interest: e.target.checked, dirty: true } : item))}
                      />
                    </td>
                    <td>
                      <input
                        value={client.notes ?? ""}
                        onChange={(e) => setClients(current => current.map(item => item.client_key === client.client_key ? { ...item, notes: e.target.value, dirty: true } : item))}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-layout">
      {view === "standalone" && (
        <>
          <section className="panel compact-panel-card">
            <div className="panel-title compact-title-row">
              <h3>Boletos avulsos</h3>
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
                <Button
                  type="button"
                  variant="secondary"
                  loading={submitting}
                  disabled={submitting || !hasInterApiAccount}
                  onClick={() => void onSyncStandaloneBoletos()}
                >
                  Atualizar Inter
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  loading={submitting}
                  disabled={submitting}
                  onClick={openStandaloneBoletoModal}
                >
                  Novo boleto avulso
                </Button>
                <span>{visibleStandaloneBoletos.length}</span>
              </div>
            </div>
            <div className="table-shell table-shell--scroll billing-table-shell billing-table-shell--expanded entries-table-shell">
              <table className="erp-table erp-table--compact erp-table--responsive entries-list-table billing-alert-table">
                <colgroup>
                  <col className="billing-alert-col-client" />
                  <col className="billing-alert-col-document" />
                  <col className="billing-alert-col-issue-date" />
                  <col className="billing-alert-col-due-date" />
                  <col className="billing-alert-col-amount" />
                  <col className="billing-alert-col-bank" />
                  <col className="billing-alert-col-status" />
                  <col className="billing-alert-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>{renderSortButton("Cliente", "client_name", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("client_name"))}</th>
                    <th>{renderSortButton("Documento", "document_id", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("document_id"))}</th>
                    <th>{renderSortButton("Emissão", "issue_date", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("issue_date"))}</th>
                    <th>{renderSortButton("Vencimento", "due_date", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("due_date"))}</th>
                    <th className="numeric-cell">{renderSortButton("Valor", "amount", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("amount"), true)}</th>
                    <th>{renderSortButton("Banco", "bank", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("bank"))}</th>
                    <th>{renderSortButton("Status banco", "status", standaloneSort, standaloneSortDirection, () => toggleStandaloneSort("status"))}</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStandaloneBoletos.map((item) => (
                    <tr key={item.id}>
                      <td>{item.client_name}</td>
                      <td>{item.document_id}</td>
                      <td>{formatDate(item.issue_date)}</td>
                      <td>{formatDate(item.due_date)}</td>
                      <td className="numeric-cell">{formatMoney(item.amount)}</td>
                      <td>{item.bank}</td>
                      <td>{renderStatusBadge(item.status)}</td>
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
                      <td className="empty-cell" colSpan={8}>Nenhum boleto avulso em {formatStandaloneBoletoFilterLabel(standaloneBoletoFilter).toLowerCase()}.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
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

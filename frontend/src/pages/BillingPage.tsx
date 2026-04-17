import { useEffect, useMemo, useState } from "react";
import { MoneyInput } from "../components/MoneyInput";
import { ModalCloseButton } from "../components/ModalCloseButton";
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
type BillingView = "invoices" | "boletos";
type DateRange = {
  start: string;
  end: string;
};
type FilterPopover = "status" | "client" | "issue_date" | "due_date" | "type" | "bank" | null;
type StandaloneBoletoDraft = {
  account_id: string;
  client_name: string;
  amount: string;
  due_date: string;
  notes: string;
};
type InvoiceStatusKey = "open" | "paid" | "overdue" | "cancelled";
type BoletoStatusKey =
  | "open"
  | "paid"
  | "overdue"
  | "cancelled"
  | "paid_pending"
  | "missing"
  | "excess"
  | "standalone";
type BoletoTypeKey = "recurring" | "standalone" | "paid_pending" | "missing" | "excess";
type InvoiceRow = {
  id: string;
  client_name: string;
  title: string;
  issue_date: string | null;
  due_date: string | null;
  amount: string;
  status: string;
  status_key: InvoiceStatusKey;
};
type BoletoRowKind = "bank" | "standalone" | "paid_pending" | "missing" | "excess";
type BoletoRow = {
  id: string;
  kind: BoletoRowKind;
  client_name: string;
  document_id: string;
  description: string;
  issue_date: string | null;
  due_date: string | null;
  amount: string;
  bank: string | null;
  status: string;
  status_key: BoletoStatusKey;
  type_key: BoletoTypeKey;
  type_label: string;
  status_loja: string;
  status_banco: string;
  filter_keys: BoletoStatusKey[];
  selection_key: string | null;
  boletos: BoletoAlertItem["boletos"];
  boletoId: string | null;
  standaloneId: string | null;
  pdf_available: boolean;
  inter_codigo_solicitacao: string | null;
  inter_account_id: string | null;
  local_status: string | null;
};

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 25;
const DEFAULT_INVOICE_FILTERS: InvoiceStatusKey[] = ["overdue"];
const DEFAULT_BOLETO_FILTERS: BoletoStatusKey[] = ["overdue"];
const ALL_BOLETO_STATUS_FILTERS: BoletoStatusKey[] = ["open", "paid", "overdue", "paid_pending", "missing", "excess", "standalone"];
const ALL_BOLETO_TYPE_FILTERS: BoletoTypeKey[] = ["recurring", "standalone", "paid_pending", "missing", "excess"];

function getTodayInputDate() {
  return new Date().toISOString().slice(0, 10);
}

function compareText(left: string | null | undefined, right: string | null | undefined) {
  return String(left ?? "").localeCompare(String(right ?? ""), "pt-BR");
}

function compareDate(left: string | null | undefined, right: string | null | undefined) {
  return compareText(left ?? "9999-12-31", right ?? "9999-12-31");
}

function compareAmount(left: string | number, right: string | number) {
  return Number(left) - Number(right);
}

function matchesDateRange(value: string | null | undefined, range: DateRange) {
  if (!range.start && !range.end) {
    return true;
  }
  if (!value) {
    return false;
  }
  if (range.start && value < range.start) {
    return false;
  }
  if (range.end && value > range.end) {
    return false;
  }
  return true;
}

function resolvePageSizeLimit(pageSize: number, total: number) {
  if (pageSize === -1) {
    return Math.max(total, 1);
  }
  return pageSize;
}

function uniqueValues(values: Array<string | null | undefined>) {
  return [...new Set(values.map((item) => String(item ?? "").trim()).filter(Boolean))].sort((left, right) =>
    left.localeCompare(right, "pt-BR"),
  );
}

function invoiceStatusLabel(status: InvoiceStatusKey) {
  switch (status) {
    case "paid":
      return "Pago";
    case "cancelled":
      return "Cancelado";
    case "overdue":
      return "Atrasado";
    case "open":
    default:
      return "Em aberto";
  }
}

function boletoStatusLabel(status: BoletoStatusKey) {
  switch (status) {
    case "paid":
      return "Pago";
    case "cancelled":
      return "Cancelado";
    case "overdue":
      return "Atrasado";
    case "paid_pending":
      return "Pago sem baixa";
    case "missing":
      return "Boleto faltando";
    case "excess":
      return "Boleto em excesso";
    case "standalone":
      return "Boleto avulso";
    case "open":
    default:
      return "Em aberto";
  }
}

function boletoTypeLabel(type: BoletoTypeKey) {
  switch (type) {
    case "standalone":
      return "Boleto avulso";
    case "paid_pending":
      return "Pago sem baixa";
    case "missing":
      return "Boleto faltando";
    case "excess":
      return "Boleto em excesso";
    case "recurring":
    default:
      return "Cobranca recorrente";
  }
}

function renderBoletoStatusBadge(statusKey: BoletoStatusKey, label: string) {
  let tone: "success" | "warning" | "danger" | "info" | "neutral" = "neutral";
  
  switch (statusKey) {
    case "paid":
      tone = "success";
      break;
    case "overdue":
    case "missing":
    case "excess":
      tone = "danger";
      break;
    case "open":
    case "paid_pending":
      tone = "warning";
      break;
    case "standalone":
      tone = "info";
      break;
    case "cancelled":
      tone = "neutral";
      break;
  }

  return <span className={`badge badge-${tone}`}>{label}</span>;
}

function renderInvoiceStatusBadge(statusKey: InvoiceStatusKey, label: string) {
  let tone: "success" | "warning" | "danger" | "neutral" = "neutral";

  switch (statusKey) {
    case "paid":
      tone = "success";
      break;
    case "overdue":
      tone = "danger";
      break;
    case "open":
      tone = "warning";
      break;
  }

  return <span className={`badge badge-${tone}`}>{label}</span>;
}

function buildInvoiceTitle(item: BoletoDashboard["invoice_items"][number]) {
  const document = String(item.document ?? "").trim();
  const invoiceNumber = String(item.invoice_number ?? "").trim();
  const installment = String(item.installment ?? "").trim();
  const fallback = [invoiceNumber, installment].filter(Boolean).join(" / ");
  return document || fallback || "Sem titulo";
}

function resolveInvoiceStatus(item: BoletoDashboard["invoice_items"][number]): InvoiceStatusKey {
  if (item.status_bucket === "paid") {
    return "paid";
  }
  if (item.status_bucket === "cancelled") {
    return "cancelled";
  }
  if (item.status_bucket === "overdue") {
    return "overdue";
  }
  return "open";
}

function resolveRegularBoletoStatus(item: { status_bucket: string }): BoletoStatusKey {
  if (item.status_bucket === "paid") {
    return "paid";
  }
  if (item.status_bucket === "cancelled") {
    return "cancelled";
  }
  if (item.status_bucket === "overdue") {
    return "overdue";
  }
  return "open";
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

function summarizeBoletoDocuments(boletos: BoletoAlertItem["boletos"]) {
  if (!boletos.length) {
    return "-";
  }
  return boletos
    .slice(0, 2)
    .map((item) => item.document_id || item.inter_codigo_solicitacao || item.barcode || item.bank)
    .filter(Boolean)
    .join(", ");
}

function formatStatusSummary(boletos: BoletoAlertItem["boletos"]) {
  const labels = uniqueValues(boletos.map((item) => formatEntryStatus(item.status)));
  return labels.length ? labels.join(", ") : "-";
}

function uniqueStandaloneClientNames(clients: BoletoClient[]) {
  return uniqueValues(clients.map((item) => item.client_name));
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

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M7 10a2.75 2.75 0 1 0 0-5.5A2.75 2.75 0 0 0 7 10Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="M13.5 9a2.25 2.25 0 1 0 0-4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M3.75 15.5a3.75 3.75 0 0 1 6.5-2.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M11.75 15.5a3 3 0 0 1 4.5-2.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M6 3.75h5.5L15 7.25v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M11.5 3.75v3.5H15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M7.5 11h5M7.5 13.75h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M15.75 10a5.75 5.75 0 1 1-1.6-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M12.75 4.5h2.75v2.75" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M16 4 9 11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="m16 4-9.5 11 1-4.5L16 4Zm0 0-4.5 1-5 5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M10 4.5v11M4.5 10h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M5.5 4.25v2.5M14.5 4.25v2.5M4.5 7h11M5.25 5.5h9.5a1 1 0 0 1 1 1v8.25a1 1 0 0 1-1 1h-9.5a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BillingPage({
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
  const [selectedDownloadableBoletoIds, setSelectedDownloadableBoletoIds] = useState<string[]>([]);
  const [standaloneBoletoDraft, setStandaloneBoletoDraft] = useState<StandaloneBoletoDraft>({
    account_id: "",
    client_name: "",
    amount: "",
    due_date: "",
    notes: "",
  });
  const [invoiceStatusFilters, setInvoiceStatusFilters] = useState<InvoiceStatusKey[]>(DEFAULT_INVOICE_FILTERS);
  const [boletoStatusFilters, setBoletoStatusFilters] = useState<BoletoStatusKey[]>(DEFAULT_BOLETO_FILTERS);
  const [boletoTypeFilters, setBoletoTypeFilters] = useState<BoletoTypeKey[]>([]);
  const [invoiceClientFilters, setInvoiceClientFilters] = useState<string[]>([]);
  const [boletoClientFilters, setBoletoClientFilters] = useState<string[]>([]);
  const [invoiceClientSearch, setInvoiceClientSearch] = useState("");
  const [boletoClientSearch, setBoletoClientSearch] = useState("");
  const [invoiceIssueDateDraft, setInvoiceIssueDateDraft] = useState<DateRange>({ start: "", end: "" });
  const [invoiceIssueDateRange, setInvoiceIssueDateRange] = useState<DateRange>({ start: "", end: "" });
  const [invoiceDateDraft, setInvoiceDateDraft] = useState<DateRange>({ start: "", end: "" });
  const [invoiceDateRange, setInvoiceDateRange] = useState<DateRange>({ start: "", end: "" });
  const [boletoIssueDateDraft, setBoletoIssueDateDraft] = useState<DateRange>({ start: "", end: "" });
  const [boletoIssueDateRange, setBoletoIssueDateRange] = useState<DateRange>({ start: "", end: "" });
  const [boletoDateDraft, setBoletoDateDraft] = useState<DateRange>({ start: "", end: "" });
  const [boletoDateRange, setBoletoDateRange] = useState<DateRange>({ start: "", end: "" });
  const [boletoBankFilters, setBoletoBankFilters] = useState<string[]>([]);
  const [invoicePopover, setInvoicePopover] = useState<FilterPopover>(null);
  const [boletoPopover, setBoletoPopover] = useState<FilterPopover>(null);
  const [invoicePage, setInvoicePage] = useState(1);
  const [boletoPage, setBoletoPage] = useState(1);
  const [invoicePageSize, setInvoicePageSize] = useState(DEFAULT_PAGE_SIZE);
  const [boletoPageSize, setBoletoPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setClients(dashboard.clients.map((item) => ({ ...item, dirty: false })));
  }, [dashboard.clients]);

  useEffect(() => {
    const visibleKeys = new Set(dashboard.missing_boletos.map((item) => item.selection_key));
    setSelectedMissingKeys((current) => current.filter((item) => visibleKeys.has(item)));
  }, [dashboard.missing_boletos]);

  const filesBySource = useMemo(
    () => Object.fromEntries(dashboard.files.map((item) => [item.source_type, item] as const)) as Record<string, BoletoDashboard["files"][number]>,
    [dashboard.files],
  );
  const standaloneClientOptions = useMemo(() => uniqueStandaloneClientNames(dashboard.clients), [dashboard.clients]);
  const hasInterApiAccount = useMemo(
    () => accounts.some((account) => account.is_active && account.inter_api_enabled),
    [accounts],
  );
  const invoiceSourceItems = dashboard.invoice_items.length ? dashboard.invoice_items : dashboard.receivables;
  const invoiceRows = useMemo<InvoiceRow[]>(
    () =>
      invoiceSourceItems.map((item) => ({
        id: `${item.client_name}-${item.invoice_number}-${item.installment}-${item.due_date ?? "-"}`,
        client_name: item.client_name ?? "",
        title: buildInvoiceTitle(item),
        issue_date: item.issue_date ?? null,
        due_date: item.due_date ?? null,
        amount: item.corrected_amount || item.amount,
        status: invoiceStatusLabel(resolveInvoiceStatus(item)),
        status_key: resolveInvoiceStatus(item),
      })),
    [invoiceSourceItems],
  );
  const boletoRows = useMemo<BoletoRow[]>(() => {
    const rows: BoletoRow[] = [];

    dashboard.all_boletos.forEach((item) => {
      const statusKey = resolveRegularBoletoStatus(item);
      if (statusKey === "cancelled") {
        return;
      }
      rows.push({
        id: `bank:${item.id}`,
        kind: "bank",
        client_name: item.client_name ?? "",
        document_id: item.document_id || "-",
        description: item.linha_digitavel || item.barcode || item.inter_codigo_solicitacao || "-",
        issue_date: item.issue_date ?? null,
        due_date: item.due_date ?? null,
        amount: item.amount,
        bank: item.bank ?? "-",
        status: boletoStatusLabel(statusKey),
        status_key: statusKey,
        type_key: "recurring",
        type_label: boletoTypeLabel("recurring"),
        status_loja: boletoTypeLabel("recurring"),
        status_banco: formatEntryStatus(item.status),
        filter_keys: [statusKey],
        selection_key: null,
        boletos: [],
        boletoId: item.id,
        standaloneId: null,
        pdf_available: Boolean(item.pdf_available),
        inter_codigo_solicitacao: item.inter_codigo_solicitacao ?? null,
        inter_account_id: item.inter_account_id ?? null,
        local_status: null,
      });
    });

    dashboard.standalone_boletos.forEach((item) => {
      const statusKey = resolveRegularBoletoStatus(item);
      if (statusKey === "cancelled") {
        return;
      }
      rows.push({
        id: `standalone:${item.id}`,
        kind: "standalone",
        client_name: item.client_name ?? "",
        document_id: item.document_id || "-",
        description: item.description || item.notes || "-",
        issue_date: item.issue_date ?? null,
        due_date: item.due_date ?? null,
        amount: item.amount,
        bank: item.bank ?? "-",
        status: boletoStatusLabel(statusKey),
        status_key: statusKey,
        type_key: "standalone",
        type_label: boletoTypeLabel("standalone"),
        status_loja: boletoTypeLabel("standalone"),
        status_banco: formatEntryStatus(item.status),
        filter_keys: [statusKey, "standalone"],
        selection_key: null,
        boletos: [],
        boletoId: null,
        standaloneId: item.id,
        pdf_available: Boolean(item.pdf_available),
        inter_codigo_solicitacao: item.inter_codigo_solicitacao ?? null,
        inter_account_id: item.inter_account_id ?? null,
        local_status: item.local_status ?? null,
      });
    });

    dashboard.paid_pending.forEach((item, index) => {
      rows.push({
        id: `paid-pending:${item.selection_key}:${index}`,
        kind: "paid_pending",
        client_name: item.client_name ?? "",
        document_id: summarizeBoletoDocuments(item.boletos),
        description: renderReceivableDetails(item),
        issue_date: null,
        due_date: item.due_date ?? null,
        amount: item.amount,
        bank: item.bank ?? null,
        status: boletoStatusLabel("paid_pending"),
        status_key: "paid_pending",
        type_key: "paid_pending",
        type_label: boletoTypeLabel("paid_pending"),
        status_loja: boletoTypeLabel("paid_pending"),
        status_banco: formatStatusSummary(item.boletos),
        filter_keys: ["paid_pending"],
        selection_key: null,
        boletos: item.boletos,
        boletoId: null,
        standaloneId: null,
        pdf_available: item.boletos.some((boleto) => boleto.pdf_available),
        inter_codigo_solicitacao: null,
        inter_account_id: null,
        local_status: null,
      });
    });

    dashboard.missing_boletos.forEach((item, index) => {
      rows.push({
        id: `missing:${item.selection_key}:${index}`,
        kind: "missing",
        client_name: item.client_name ?? "",
        document_id: renderReceivableDetails(item),
        description: item.reason || "-",
        issue_date: null,
        due_date: item.due_date ?? null,
        amount: item.amount,
        bank: null,
        status: boletoStatusLabel("missing"),
        status_key: "missing",
        type_key: "missing",
        type_label: boletoTypeLabel("missing"),
        status_loja: boletoTypeLabel("missing"),
        status_banco: "-",
        filter_keys: ["missing"],
        selection_key: item.selection_key,
        boletos: [],
        boletoId: null,
        standaloneId: null,
        pdf_available: false,
        inter_codigo_solicitacao: null,
        inter_account_id: null,
        local_status: null,
      });
    });

    dashboard.excess_boletos.forEach((item, index) => {
      rows.push({
        id: `excess:${item.selection_key}:${index}`,
        kind: "excess",
        client_name: item.client_name ?? "",
        document_id: summarizeBoletoDocuments(item.boletos),
        description: item.reason || "-",
        issue_date: null,
        due_date: item.due_date ?? null,
        amount: item.amount,
        bank: item.bank ?? null,
        status: boletoStatusLabel("excess"),
        status_key: "excess",
        type_key: "excess",
        type_label: boletoTypeLabel("excess"),
        status_loja: boletoTypeLabel("excess"),
        status_banco: formatStatusSummary(item.boletos),
        filter_keys: ["excess"],
        selection_key: null,
        boletos: item.boletos,
        boletoId: null,
        standaloneId: null,
        pdf_available: item.boletos.some((boleto) => boleto.pdf_available),
        inter_codigo_solicitacao: null,
        inter_account_id: null,
        local_status: null,
      });
    });

    return rows.sort((left, right) => {
      const dueComparison = compareDate(left.due_date, right.due_date);
      if (dueComparison !== 0) {
        return dueComparison;
      }
      const clientComparison = compareText(left.client_name, right.client_name);
      if (clientComparison !== 0) {
        return clientComparison;
      }
      return compareAmount(left.amount, right.amount);
    });
  }, [dashboard.all_boletos, dashboard.excess_boletos, dashboard.missing_boletos, dashboard.paid_pending, dashboard.standalone_boletos]);

  useEffect(() => {
    const visibleIds = new Set(
      boletoRows
        .filter((item) => item.kind === "bank" && item.pdf_available && item.boletoId)
        .map((item) => item.boletoId as string),
    );
    setSelectedDownloadableBoletoIds((current) => current.filter((item) => visibleIds.has(item)));
  }, [boletoRows]);

  const invoiceClients = useMemo(() => uniqueValues(invoiceRows.map((item) => item.client_name)), [invoiceRows]);
  const boletoClients = useMemo(() => uniqueValues(boletoRows.map((item) => item.client_name)), [boletoRows]);
  const boletoBanks = useMemo(() => uniqueValues(boletoRows.map((item) => item.bank || "-")), [boletoRows]);

  const visibleInvoiceClients = useMemo(() => {
    const query = invoiceClientSearch.trim().toLowerCase();
    if (!query) {
      return invoiceClients;
    }
    return invoiceClients.filter((item) => item.toLowerCase().includes(query));
  }, [invoiceClientSearch, invoiceClients]);
  const visibleBoletoClients = useMemo(() => {
    const query = boletoClientSearch.trim().toLowerCase();
    if (!query) {
      return boletoClients;
    }
    return boletoClients.filter((item) => item.toLowerCase().includes(query));
  }, [boletoClientSearch, boletoClients]);

  const filteredInvoices = useMemo(() => {
    const selectedStatuses = invoiceStatusFilters.length ? invoiceStatusFilters : (["open", "paid", "overdue", "cancelled"] as InvoiceStatusKey[]);
    return invoiceRows
      .filter((item) => selectedStatuses.includes(item.status_key))
      .filter((item) => !invoiceClientFilters.length || invoiceClientFilters.includes(item.client_name))
      .filter((item) => matchesDateRange(item.issue_date, invoiceIssueDateRange))
      .filter((item) => matchesDateRange(item.due_date, invoiceDateRange));
  }, [invoiceClientFilters, invoiceDateRange, invoiceIssueDateRange, invoiceRows, invoiceStatusFilters]);

  const filteredBoletos = useMemo(() => {
    const selectedStatuses = boletoStatusFilters.length ? boletoStatusFilters : ALL_BOLETO_STATUS_FILTERS;
    const ignoreDefaultStatusFilter =
      boletoTypeFilters.length > 0 &&
      boletoStatusFilters.length === DEFAULT_BOLETO_FILTERS.length &&
      boletoStatusFilters.every((value, index) => value === DEFAULT_BOLETO_FILTERS[index]);
    return boletoRows
      .filter((item) => !boletoTypeFilters.length || boletoTypeFilters.includes(item.type_key))
      // When the user chooses a type filter from the header, don't keep the default
      // "Atrasado" filter silently hiding the selected type.
      .filter((item) => ignoreDefaultStatusFilter || item.filter_keys.some((key) => selectedStatuses.includes(key)))
      .filter((item) => !boletoClientFilters.length || boletoClientFilters.includes(item.client_name))
      .filter((item) => !boletoBankFilters.length || boletoBankFilters.includes(item.bank || "-"))
      .filter((item) => matchesDateRange(item.issue_date, boletoIssueDateRange))
      .filter((item) => matchesDateRange(item.due_date, boletoDateRange));
  }, [boletoBankFilters, boletoClientFilters, boletoDateRange, boletoIssueDateRange, boletoRows, boletoStatusFilters, boletoTypeFilters]);

  useEffect(() => {
    setInvoicePage(1);
  }, [invoiceClientFilters, invoiceDateRange, invoiceIssueDateRange, invoicePageSize, invoiceStatusFilters]);

  useEffect(() => {
    setBoletoPage(1);
  }, [boletoBankFilters, boletoClientFilters, boletoDateRange, boletoIssueDateRange, boletoPageSize, boletoStatusFilters, boletoTypeFilters]);

  const paginatedInvoices = useMemo(
    () => {
      const limit = resolvePageSizeLimit(invoicePageSize, filteredInvoices.length);
      return filteredInvoices.slice((invoicePage - 1) * limit, invoicePage * limit);
    },
    [filteredInvoices, invoicePage, invoicePageSize],
  );
  const paginatedBoletos = useMemo(
    () => {
      const limit = resolvePageSizeLimit(boletoPageSize, filteredBoletos.length);
      return filteredBoletos.slice((boletoPage - 1) * limit, boletoPage * limit);
    },
    [filteredBoletos, boletoPage, boletoPageSize],
  );
  const visibleMissingPageKeys = useMemo(
    () => paginatedBoletos.map((item) => item.selection_key).filter((item): item is string => Boolean(item)),
    [paginatedBoletos],
  );
  const visibleDownloadablePageIds = useMemo(
    () =>
      paginatedBoletos
        .filter((item) => item.kind === "bank" && item.pdf_available && item.boletoId)
        .map((item) => item.boletoId as string),
    [paginatedBoletos],
  );

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

  function resolveInterEnvironment(boleto: Pick<BoletoRow, "inter_account_id">) {
    const directAccount = boleto.inter_account_id ? accounts.find((account) => account.id === boleto.inter_account_id) : null;
    if (directAccount?.inter_environment) {
      return directAccount.inter_environment;
    }
    const fallbackInterAccount = accounts.find((account) => account.is_active && account.inter_api_enabled);
    return fallbackInterAccount?.inter_environment ?? null;
  }

  function canCancelBankBoleto(row: BoletoRow) {
    return Boolean(
      row.kind === "bank" &&
      row.bank === "INTER" &&
      row.inter_codigo_solicitacao &&
      row.status_key !== "cancelled" &&
      row.status_key !== "paid",
    );
  }

  function canReceiveBankBoleto(row: BoletoRow) {
    return Boolean(
      row.kind === "bank" &&
      row.bank === "INTER" &&
      row.inter_codigo_solicitacao &&
      resolveInterEnvironment(row) === "sandbox" &&
      row.status_key !== "paid" &&
      row.status_key !== "cancelled",
    );
  }

  function canCancelStandaloneBoleto(row: BoletoRow) {
    return Boolean(
      row.kind === "standalone" &&
      row.bank === "INTER" &&
      row.inter_codigo_solicitacao &&
      row.status_key !== "cancelled" &&
      row.status_key !== "paid",
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

  async function handleUploadC6() {
    if (!c6File) {
      return;
    }
    await onUploadBoletoC6(c6File);
    setC6File(null);
    setC6ModalOpen(false);
  }

  function toggleMissingSelection(selectionKey: string) {
    setSelectedMissingKeys((current) =>
      current.includes(selectionKey) ? current.filter((item) => item !== selectionKey) : [...current, selectionKey],
    );
  }

  function toggleDownloadSelection(boletoId: string) {
    setSelectedDownloadableBoletoIds((current) =>
      current.includes(boletoId) ? current.filter((item) => item !== boletoId) : [...current, boletoId],
    );
  }

  function applyInvoiceDateFilter() {
    setInvoiceDateRange(invoiceDateDraft);
    setInvoicePopover(null);
  }

  function applyInvoiceIssueDateFilter() {
    setInvoiceIssueDateRange(invoiceIssueDateDraft);
    setInvoicePopover(null);
  }

  function clearInvoiceDateFilter() {
    const nextRange = { start: "", end: "" };
    setInvoiceDateDraft(nextRange);
    setInvoiceDateRange(nextRange);
    setInvoicePopover(null);
  }

  function clearInvoiceIssueDateFilter() {
    const nextRange = { start: "", end: "" };
    setInvoiceIssueDateDraft(nextRange);
    setInvoiceIssueDateRange(nextRange);
    setInvoicePopover(null);
  }

  function applyBoletoDateFilter() {
    setBoletoDateRange(boletoDateDraft);
    setBoletoPopover(null);
  }

  function applyBoletoIssueDateFilter() {
    setBoletoIssueDateRange(boletoIssueDateDraft);
    setBoletoPopover(null);
  }

  function clearBoletoDateFilter() {
    const nextRange = { start: "", end: "" };
    setBoletoDateDraft(nextRange);
    setBoletoDateRange(nextRange);
    setBoletoPopover(null);
  }

  function clearBoletoIssueDateFilter() {
    const nextRange = { start: "", end: "" };
    setBoletoIssueDateDraft(nextRange);
    setBoletoIssueDateRange(nextRange);
    setBoletoPopover(null);
  }

  function renderHeaderFilterButton(label: string, isActive: boolean, onClick: () => void) {
    return (
      <div className="finance-open-items-table-header">
        <button className="table-sort-button billing-filter-header-button" onClick={onClick} type="button">
          <strong>{label}</strong>
        </button>
        <button className={`entries-column-filter-trigger ${isActive ? "is-active" : ""}`.trim()} onClick={onClick} type="button">
          <FilterFunnelIcon />
        </button>
      </div>
    );
  }

  function renderStatusPopover<T extends string>(
    values: T[],
    selectedValues: T[],
    onToggleValue: (value: T) => void,
    onReset: () => void,
  ) {
    const renderLabel = (value: string) => {
      if (["open", "paid", "overdue", "cancelled"].includes(value)) {
        return invoiceStatusLabel(value as InvoiceStatusKey);
      }
      return boletoStatusLabel(value as BoletoStatusKey);
    };
    return (
      <div className="entries-floating-panel entries-column-filter-popover entries-category-filter-popover billing-column-filter-popover">
        <div className="entries-category-filter-head">
          <strong>Filtrar status</strong>
        </div>
        <div className="entries-category-filter-list">
          {values.map((value) => (
            <label className="entries-category-filter-option" key={value}>
              <input checked={selectedValues.includes(value)} onChange={() => onToggleValue(value)} type="checkbox" />
              <div className="entries-category-filter-text">
                <strong>{renderLabel(value)}</strong>
              </div>
            </label>
          ))}
        </div>
        <div className="entries-column-filter-popover-actions">
          <button className="ghost-button" onClick={onReset} type="button">
            Limpar
          </button>
        </div>
      </div>
    );
  }

  function renderBoletoTypePopover() {
    return (
      <div className="entries-floating-panel entries-column-filter-popover entries-category-filter-popover billing-column-filter-popover">
        <div className="entries-category-filter-head">
          <strong>Filtrar tipo</strong>
        </div>
        <div className="entries-category-filter-list">
          {ALL_BOLETO_TYPE_FILTERS.map((value) => (
            <label className="entries-category-filter-option" key={value}>
              <input
                checked={boletoTypeFilters.includes(value)}
                onChange={() =>
                  setBoletoTypeFilters((current) =>
                    current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                  )
                }
                type="checkbox"
              />
              <div className="entries-category-filter-text">
                <strong>{boletoTypeLabel(value)}</strong>
              </div>
            </label>
          ))}
        </div>
        <div className="entries-column-filter-popover-actions">
          <button className="ghost-button" onClick={() => setBoletoTypeFilters([])} type="button">
            Limpar
          </button>
        </div>
      </div>
    );
  }

  function renderBankPopover() {
    return (
      <div className="entries-floating-panel entries-column-filter-popover entries-category-filter-popover billing-column-filter-popover">
        <div className="entries-category-filter-head">
          <strong>Filtrar banco</strong>
        </div>
        <div className="entries-category-filter-list">
          {boletoBanks.map((value) => (
            <label className="entries-category-filter-option" key={value}>
              <input
                checked={boletoBankFilters.includes(value)}
                onChange={() =>
                  setBoletoBankFilters((current) =>
                    current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                  )
                }
                type="checkbox"
              />
              <div className="entries-category-filter-text">
                <strong>{value}</strong>
              </div>
            </label>
          ))}
        </div>
        <div className="entries-column-filter-popover-actions">
          <button className="ghost-button" onClick={() => setBoletoBankFilters([])} type="button">
            Limpar
          </button>
        </div>
      </div>
    );
  }

  function renderClientPopover(
    values: string[],
    visibleValues: string[],
    selectedValues: string[],
    search: string,
    onSearchChange: (value: string) => void,
    onToggleValue: (value: string) => void,
    onReset: () => void,
  ) {
    return (
      <div className="entries-floating-panel entries-column-filter-popover entries-category-filter-popover billing-column-filter-popover">
        <div className="entries-category-filter-head">
          <strong>Filtrar cliente</strong>
        </div>
        <div className="billing-filter-search">
          <input placeholder="Buscar cliente" type="search" value={search} onChange={(event) => onSearchChange(event.target.value)} />
        </div>
        <div className="entries-category-filter-list">
          {visibleValues.map((value) => (
            <label className="entries-category-filter-option" key={value}>
              <input checked={selectedValues.includes(value)} onChange={() => onToggleValue(value)} type="checkbox" />
              <div className="entries-category-filter-text">
                <strong>{value}</strong>
              </div>
            </label>
          ))}
          {!visibleValues.length ? <p className="entries-category-filter-empty">Nenhum cliente encontrado.</p> : null}
        </div>
        <div className="entries-column-filter-popover-actions">
          <button className="ghost-button" onClick={onReset} type="button">
            Limpar
          </button>
        </div>
      </div>
    );
  }

  function renderDatePopover(
    draft: DateRange,
    setDraft: (next: DateRange) => void,
    onApply: () => void,
    onClear: () => void,
  ) {
    return (
      <div className="entries-floating-panel entries-column-filter-popover entries-category-filter-popover billing-column-filter-popover">
        <div className="entries-category-filter-head">
          <strong>Filtrar periodo</strong>
        </div>
        <div className="billing-date-filter-grid">
          <label className="billing-date-filter-field">
            <span>De</span>
            <input type="date" value={draft.start} onChange={(event) => setDraft({ ...draft, start: event.target.value })} />
          </label>
          <label className="billing-date-filter-field">
            <span>Ate</span>
            <input type="date" value={draft.end} onChange={(event) => setDraft({ ...draft, end: event.target.value })} />
          </label>
        </div>
        <div className="entries-column-filter-popover-actions">
          <button className="ghost-button" onClick={onClear} type="button">
            Limpar
          </button>
          <button className="primary-button" onClick={onApply} type="button">
            Aplicar
          </button>
        </div>
      </div>
    );
  }

  function renderTablePagination(
    total: number,
    page: number,
    pageSize: number,
    onPageChange: (nextPage: number) => void,
    onPageSizeChange: (nextSize: number) => void,
  ) {
    const effectivePageSize = resolvePageSizeLimit(pageSize, total);
    const totalPages = Math.max(1, Math.ceil(total / effectivePageSize));
    return (
      <div className="table-pagination">
        <div className="table-pagination-actions">
          <label className="pagination-size">
            <span>Linhas</span>
            <select value={String(pageSize)} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
              {PAGE_SIZE_OPTIONS.map((option) => (
                <option key={option} value={String(option)}>
                  {option}
                </option>
              ))}
              <option value="-1">Todos</option>
            </select>
          </label>
          <button className="secondary-button" disabled={page <= 1} onClick={() => onPageChange(page - 1)} type="button">
            Anterior
          </button>
          <span className="compact-muted">
            {page}/{totalPages}
          </span>
          <button className="secondary-button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} type="button">
            Proxima
          </button>
        </div>
      </div>
    );
  }

  function renderAlertBoletoActions(boletos: BoletoAlertItem["boletos"]) {
    if (!boletos.length) {
      return <small className="compact-muted">-</small>;
    }
    return (
      <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
        {boletos
          .filter((item) => item.pdf_available)
          .slice(0, 3)
          .map((item) => (
            <button
              key={item.id}
              className="table-button icon-only-button"
              disabled={submitting}
              onClick={() => void onDownloadInterBoletoPdf(item.id)}
              title={`Baixar PDF ${item.document_id || item.bank}`}
              type="button"
            >
              <DownloadIcon />
            </button>
          ))}
      </div>
    );
  }

  function renderInvoiceTable() {
    return (
      <section className="panel compact-panel-card">
        <div className="billing-section-header">
          <div className="billing-section-header-top">
            <div className="billing-section-heading">
              <h3>Faturas</h3>
            </div>
          </div>

          <div className="billing-section-toolbar">
            <div className="billing-section-meta">
              {renderFileMeta("linx_receivables")}
              <span className="billing-section-count">{filteredInvoices.length}</span>
            </div>
            <div className="billing-section-pagination">
              {renderTablePagination(filteredInvoices.length, invoicePage, invoicePageSize, setInvoicePage, setInvoicePageSize)}
            </div>
          </div>
        </div>

        <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
          <table className="erp-table entries-list-table billing-alert-table billing-open-receivables-table">
            <colgroup>
              <col className="billing-alert-col-client" />
              <col className="billing-alert-col-document" />
              <col className="billing-alert-col-issue-date" />
              <col className="billing-alert-col-due-date" />
              <col className="billing-alert-col-amount" />
              <col className="billing-alert-col-status" />
            </colgroup>
            <thead>
              <tr>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Cliente", invoicePopover === "client", () =>
                    setInvoicePopover((current) => (current === "client" ? null : "client")),
                  )}
                  {invoicePopover === "client"
                    ? renderClientPopover(
                        invoiceClients,
                        visibleInvoiceClients,
                        invoiceClientFilters,
                        invoiceClientSearch,
                        setInvoiceClientSearch,
                        (value) =>
                          setInvoiceClientFilters((current) =>
                            current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                          ),
                        () => {
                          setInvoiceClientFilters([]);
                          setInvoiceClientSearch("");
                        },
                      )
                    : null}
                </th>
                <th>Titulo</th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Emissao", invoicePopover === "issue_date", () =>
                    setInvoicePopover((current) => (current === "issue_date" ? null : "issue_date")),
                  )}
                  {invoicePopover === "issue_date"
                    ? renderDatePopover(invoiceIssueDateDraft, setInvoiceIssueDateDraft, applyInvoiceIssueDateFilter, clearInvoiceIssueDateFilter)
                    : null}
                </th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Vencimento", invoicePopover === "due_date", () =>
                    setInvoicePopover((current) => (current === "due_date" ? null : "due_date")),
                  )}
                  {invoicePopover === "due_date"
                    ? renderDatePopover(invoiceDateDraft, setInvoiceDateDraft, applyInvoiceDateFilter, clearInvoiceDateFilter)
                    : null}
                </th>
                <th className="numeric-cell">Valor</th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Status", invoicePopover === "status", () =>
                    setInvoicePopover((current) => (current === "status" ? null : "status")),
                  )}
                  {invoicePopover === "status"
                    ? renderStatusPopover<InvoiceStatusKey>(
                        ["open", "paid", "overdue", "cancelled"],
                        invoiceStatusFilters,
                        (value) =>
                          setInvoiceStatusFilters((current) =>
                            current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                          ),
                        () => setInvoiceStatusFilters([]),
                      )
                    : null}
                </th>
              </tr>
            </thead>
            <tbody>
              {paginatedInvoices.map((item) => (
                <tr key={item.id}>
                  <td title={item.client_name}>{item.client_name}</td>
                  <td title={item.title}>
                    <strong>{item.title}</strong>
                  </td>
                  <td>{formatDate(item.issue_date)}</td>
                  <td>{formatDate(item.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(item.amount)}</td>
                  <td>
                    {renderInvoiceStatusBadge(item.status_key, item.status)}
                  </td>
                </tr>
              ))}
              {!paginatedInvoices.length ? (
                <tr>
                  <td className="empty-cell" colSpan={6}>
                    Nenhuma fatura encontrada.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

      </section>
    );
  }

  function renderBoletoActions(row: BoletoRow) {
    if (row.kind === "bank" && row.boletoId) {
      return (
        <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
          {row.pdf_available ? (
            <button className="table-button icon-only-button" disabled={submitting} onClick={() => void onDownloadInterBoletoPdf(row.boletoId!)} title="Baixar PDF" type="button">
              <DownloadIcon />
            </button>
          ) : null}
          {canReceiveBankBoleto(row) ? (
            <button className="table-button icon-only-button" disabled={submitting} onClick={() => row.boletoId && void onReceiveInterBoleto(row.boletoId, "BOLETO")} title="Baixar no sandbox" type="button">
              <CheckIcon />
            </button>
          ) : null}
          {canCancelBankBoleto(row) ? (
            <button
              className="table-button icon-only-button"
              disabled={submitting}
              onClick={() => {
                if (row.boletoId && window.confirm(`Cancelar o boleto ${row.document_id}?`)) {
                  void onCancelInterBoleto(row.boletoId);
                }
              }}
              title="Cancelar no Inter"
              type="button"
            >
              <CancelIcon />
            </button>
          ) : null}
        </div>
      );
    }
    if (row.kind === "standalone" && row.standaloneId) {
      return (
        <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
          {row.pdf_available ? (
            <button className="table-button icon-only-button" disabled={submitting} onClick={() => void onDownloadStandaloneBoletoPdf(row.standaloneId!)} title="Baixar PDF" type="button">
              <DownloadIcon />
            </button>
          ) : null}
          <button className="table-button icon-only-button" disabled={submitting} onClick={() => void onMarkStandaloneBoletoDownloaded(row.standaloneId!)} title="Marcar como baixado" type="button">
            <CheckIcon />
          </button>
          {canCancelStandaloneBoleto(row) ? (
            <button
              className="table-button icon-only-button"
              disabled={submitting}
              onClick={() => {
                if (row.standaloneId && window.confirm(`Cancelar o boleto avulso ${row.document_id}?`)) {
                  void onCancelStandaloneBoleto(row.standaloneId);
                }
              }}
              title="Cancelar no Inter"
              type="button"
            >
              <CancelIcon />
            </button>
          ) : null}
        </div>
      );
    }
    if (row.kind === "missing" && row.selection_key) {
      return (
        <div className="billing-boleto-row-actions billing-boleto-row-actions--compact">
          <button className="secondary-button billing-secondary-action" disabled={submitting || !hasInterApiAccount} onClick={() => void onIssueInterCharges([row.selection_key!])} type="button">
            Emitir
          </button>
        </div>
      );
    }
    return renderAlertBoletoActions(row.boletos);
  }

  function renderBoletosTable() {
    const allVisibleMissingSelected = Boolean(visibleMissingPageKeys.length) && visibleMissingPageKeys.every((item) => selectedMissingKeys.includes(item));
    const allVisibleDownloadableSelected =
      Boolean(visibleDownloadablePageIds.length) &&
      visibleDownloadablePageIds.every((item) => selectedDownloadableBoletoIds.includes(item));

    return (
      <section className="panel compact-panel-card">
        <div className="billing-section-header">
          <div className="billing-section-header-top">
            <div className="billing-section-heading">
              <h3>Boletos</h3>
            </div>
            <div className="billing-section-meta">
              <span className="billing-section-count">{filteredBoletos.length}</span>
            </div>
          </div>

          <div className="billing-section-toolbar">
            <div className="billing-section-actions">
            <button
              aria-label="Clientes"
              className="secondary-button icon-only-button billing-toolbar-icon-button"
              disabled={submitting}
              onClick={() => setClientsModalOpen(true)}
              title="Clientes"
              type="button"
            >
              <UsersIcon />
            </button>
            <label className="checkbox-line compact-inline billing-toolbar-toggle" title="Mostrar todos os boletos mensais">
              <CalendarIcon />
              <input checked={showAllMonthlyMissingBoletos} disabled={submitting} onChange={(event) => void onToggleAllMonthlyMissingBoletos(event.target.checked)} type="checkbox" />
              <span>Mostrar todos os boletos mensais</span>
            </label>
            {showMissingExportFallback ? null : null}
            <button
              aria-label="Baixar selecionados"
              className="secondary-button icon-only-button billing-toolbar-icon-button"
              disabled={submitting || !selectedDownloadableBoletoIds.length}
              onClick={() => void onDownloadInterBoletoPdfBatch(selectedDownloadableBoletoIds)}
              title="Baixar selecionados"
              type="button"
            >
              <DownloadIcon />
            </button>
            <button
              aria-label="Emitir no Inter"
              className="primary-button icon-only-button billing-toolbar-icon-button"
              disabled={submitting || !selectedMissingKeys.length || !hasInterApiAccount}
              onClick={() => void onIssueInterCharges(selectedMissingKeys)}
              title="Emitir no Inter"
              type="button"
            >
              <SendIcon />
            </button>
            <button
              aria-label="Atualizar Inter"
              className="secondary-button icon-only-button billing-toolbar-icon-button"
              disabled={submitting || !hasInterApiAccount}
              onClick={() => void onSyncStandaloneBoletos()}
              title="Atualizar Inter"
              type="button"
            >
              <RefreshIcon />
            </button>
            <button
              aria-label="Novo boleto avulso"
              className="primary-button icon-only-button billing-toolbar-icon-button"
              disabled={submitting}
              onClick={openStandaloneBoletoModal}
              title="Novo boleto avulso"
              type="button"
            >
              <PlusIcon />
            </button>
            </div>

            <div className="billing-section-pagination">
              {renderTablePagination(filteredBoletos.length, boletoPage, boletoPageSize, setBoletoPage, setBoletoPageSize)}
            </div>
          </div>
        </div>

        <div className="table-shell billing-table-shell billing-table-shell--expanded entries-table-shell">
          <table className="erp-table entries-list-table billing-alert-table billing-open-boletos-table">
            <colgroup>
              <col className="billing-alert-col-select" />
              <col className="billing-alert-col-client" />
              <col className="billing-alert-col-document" />
              <col className="billing-alert-col-description" />
              <col className="billing-alert-col-issue-date" />
              <col className="billing-alert-col-due-date" />
              <col className="billing-alert-col-amount" />
              <col className="billing-alert-col-status" />
              <col className="billing-alert-col-status" />
              <col className="billing-alert-col-bank" />
              <col className="billing-alert-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>
                  <div className="billing-selection-stack">
                    <input
                      checked={allVisibleMissingSelected}
                      disabled={submitting || !visibleMissingPageKeys.length}
                      onChange={(event) =>
                        setSelectedMissingKeys((current) => {
                          if (!event.target.checked) {
                            return current.filter((item) => !visibleMissingPageKeys.includes(item));
                          }
                          return [...new Set([...current, ...visibleMissingPageKeys])];
                        })
                      }
                      title="Selecionar faltando da página"
                      type="checkbox"
                    />
                    <input
                      checked={allVisibleDownloadableSelected}
                      disabled={submitting || !visibleDownloadablePageIds.length}
                      onChange={(event) =>
                        setSelectedDownloadableBoletoIds((current) => {
                          if (!event.target.checked) {
                            return current.filter((item) => !visibleDownloadablePageIds.includes(item));
                          }
                          return [...new Set([...current, ...visibleDownloadablePageIds])];
                        })
                      }
                      title="Selecionar PDFs da página"
                      type="checkbox"
                    />
                  </div>
                </th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Cliente", boletoPopover === "client", () => setBoletoPopover((current) => (current === "client" ? null : "client")))}
                  {boletoPopover === "client"
                    ? renderClientPopover(
                        boletoClients,
                        visibleBoletoClients,
                        boletoClientFilters,
                        boletoClientSearch,
                        setBoletoClientSearch,
                        (value) =>
                          setBoletoClientFilters((current) =>
                            current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                          ),
                        () => {
                          setBoletoClientFilters([]);
                          setBoletoClientSearch("");
                        },
                      )
                    : null}
                </th>
                <th>Documento</th>
                <th>Descricao</th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Emissao", boletoPopover === "issue_date", () =>
                    setBoletoPopover((current) => (current === "issue_date" ? null : "issue_date")),
                  )}
                  {boletoPopover === "issue_date"
                    ? renderDatePopover(boletoIssueDateDraft, setBoletoIssueDateDraft, applyBoletoIssueDateFilter, clearBoletoIssueDateFilter)
                    : null}
                </th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Vencimento", boletoPopover === "due_date", () => setBoletoPopover((current) => (current === "due_date" ? null : "due_date")))}
                  {boletoPopover === "due_date" ? renderDatePopover(boletoDateDraft, setBoletoDateDraft, applyBoletoDateFilter, clearBoletoDateFilter) : null}
                </th>
                <th className="numeric-cell">Valor</th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Status", boletoPopover === "status", () => setBoletoPopover((current) => (current === "status" ? null : "status")))}
                  {boletoPopover === "status"
                    ? renderStatusPopover<BoletoStatusKey>(
                        ALL_BOLETO_STATUS_FILTERS,
                        boletoStatusFilters,
                        (value) =>
                          setBoletoStatusFilters((current) =>
                            current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                          ),
                        () => setBoletoStatusFilters([]),
                      )
                    : null}
                </th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Status loja", boletoPopover === "type", () => setBoletoPopover((current) => (current === "type" ? null : "type")))}
                  {boletoPopover === "type" ? renderBoletoTypePopover() : null}
                </th>
                <th className="billing-filter-header-cell">
                  {renderHeaderFilterButton("Banco", boletoPopover === "bank", () => setBoletoPopover((current) => (current === "bank" ? null : "bank")))}
                  {boletoPopover === "bank" ? renderBankPopover() : null}
                </th>
                <th>Acoes</th>
              </tr>
            </thead>
            <tbody>
              {paginatedBoletos.map((row) => (
                <tr key={row.id}>
                  <td className="billing-open-boletos-select-cell">
                    <div className="billing-selection-stack">
                      {row.selection_key ? (
                        <input
                          checked={selectedMissingKeys.includes(row.selection_key)}
                          disabled={submitting}
                          onChange={() => toggleMissingSelection(row.selection_key!)}
                          title="Selecionar para emitir"
                          type="checkbox"
                        />
                      ) : (
                        <span className="billing-selection-placeholder" />
                      )}
                      {row.kind === "bank" && row.pdf_available && row.boletoId ? (
                        <input
                          checked={selectedDownloadableBoletoIds.includes(row.boletoId)}
                          disabled={submitting}
                          onChange={() => toggleDownloadSelection(row.boletoId!)}
                          title="Selecionar para baixar"
                          type="checkbox"
                        />
                      ) : (
                        <span className="billing-selection-placeholder" />
                      )}
                    </div>
                  </td>
                  <td title={row.client_name}>{row.client_name}</td>
                  <td title={row.document_id}>
                    <strong>{row.document_id || "-"}</strong>
                  </td>
                  <td title={row.description}>{row.description || "-"}</td>
                  <td>{formatDate(row.issue_date)}</td>
                  <td>{formatDate(row.due_date)}</td>
                  <td className="numeric-cell">{formatMoney(row.amount)}</td>
                  <td>
                    {renderBoletoStatusBadge(row.status_key, row.status)}
                  </td>
                  <td>{row.status_loja}</td>
                  <td>{row.status_banco === "-" ? row.bank || "-" : `${row.bank || "-"} / ${row.status_banco}`}</td>
                  <td className="billing-open-boletos-actions-cell">{renderBoletoActions(row)}</td>
                </tr>
              ))}
              {!paginatedBoletos.length ? (
                <tr>
                  <td className="empty-cell" colSpan={11}>
                    Nenhum boleto encontrado.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

      </section>
    );
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
              <p>Nenhuma conta com API Inter ativa foi encontrada. A emissao sera liberada quando houver uma conta Inter ativa.</p>
            </div>
          ) : null}

          <div className="billing-standalone-form">
            <label className="billing-standalone-form-field">
              <span>Conta Inter</span>
              <select value={standaloneBoletoDraft.account_id} onChange={(event) => setStandaloneBoletoDraft((current) => ({ ...current, account_id: event.target.value }))}>
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
              <input list="standalone-boleto-clients" placeholder="Nome do cliente" value={standaloneBoletoDraft.client_name} onChange={(event) => setStandaloneBoletoDraft((current) => ({ ...current, client_name: event.target.value }))} />
              <datalist id="standalone-boleto-clients">
                {standaloneClientOptions.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </label>

            <label className="billing-standalone-form-field">
              <span>Valor</span>
              <MoneyInput placeholder="0,00" value={standaloneBoletoDraft.amount} onValueChange={(value) => setStandaloneBoletoDraft((current) => ({ ...current, amount: value }))} />
            </label>

            <label className="billing-standalone-form-field">
              <span>Vencimento</span>
              <input type="date" value={standaloneBoletoDraft.due_date} onChange={(event) => setStandaloneBoletoDraft((current) => ({ ...current, due_date: event.target.value }))} />
            </label>

            <label className="billing-standalone-form-field billing-standalone-form-field--full">
              <span>Observacao</span>
              <textarea rows={4} placeholder="Descreva o motivo ou referencia deste boleto" value={standaloneBoletoDraft.notes} onChange={(event) => setStandaloneBoletoDraft((current) => ({ ...current, notes: event.target.value }))} />
            </label>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={submitting || !interAccounts.length || !standaloneBoletoDraft.client_name.trim() || !standaloneBoletoDraft.amount.trim() || !standaloneBoletoDraft.due_date}
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
            <p>Envie o arquivo etiquetas.txt para atualizar os dados cadastrais dos clientes usados na cobranca.</p>
            <small className="compact-muted">
              {customerDataImport ? `Ultima carga: ${customerDataImport.name} em ${formatDate(customerDataImport.updated_at)}` : "Nenhuma carga de etiquetas feita ainda."}
            </small>
          </div>

          <div className="compact-import-card billing-modal-upload-card">
            <input id="boletos-customer-data-file" className="hidden-file-input" type="file" accept=".txt,.html" onChange={(event) => setCustomerDataFile(event.target.files?.[0] ?? null)} />
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
          </div>

          <div className="action-row">
            <button className="primary-button" disabled={submitting || !customerDataFile} onClick={() => customerDataFile && void onUploadClientData(customerDataFile)} type="button">
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
            <h3>Importar relatorio C6</h3>
            <ModalCloseButton onClick={closeC6Modal} />
          </div>

          <div className="billing-modal-copy">
            <p>Envie o arquivo CSV do C6 para atualizar os registros usados na conferencia de boletos faltando.</p>
            {renderFileMeta("boletos:c6")}
          </div>

          <div className="compact-import-card billing-modal-upload-card">
            <input id="boletos-c6-file" className="hidden-file-input" type="file" accept=".csv" onChange={(event) => setC6File(event.target.files?.[0] ?? null)} />
            <div className="billing-file-picker-row">
              <label className="secondary-button compact-file-trigger" htmlFor="boletos-c6-file">
                Selecionar relatorio
              </label>
              {c6File ? (
                <span className="compact-file-name" title={c6File.name}>
                  {c6File.name}
                </span>
              ) : null}
            </div>
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
                Salvar configuracoes
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
                  <th>Observacoes</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.client_key}>
                    <td title={client.client_name}>{client.client_name}</td>
                    <td>{client.receivable_count}</td>
                    <td className="numeric-cell">{formatMoney(client.total_amount)}</td>
                    <td>
                      <input type="checkbox" checked={client.uses_boleto} onChange={(event) => setClients((current) => current.map((item) => (item.client_key === client.client_key ? { ...item, uses_boleto: event.target.checked, dirty: true } : item)))} />
                    </td>
                    <td>
                      <select value={client.mode} onChange={(event) => setClients((current) => current.map((item) => (item.client_key === client.client_key ? { ...item, mode: event.target.value, dirty: true } : item)))}>
                        <option value="individual">Individual</option>
                        <option value="mensal">Mensal</option>
                        <option value="negociacao">Negociacao</option>
                      </select>
                    </td>
                    <td>
                      <input className="mini-input" type="number" min={1} max={31} value={client.boleto_due_day ?? ""} onChange={(event) => setClients((current) => current.map((item) => (item.client_key === client.client_key ? { ...item, boleto_due_day: event.target.value ? Number(event.target.value) : null, dirty: true } : item)))} />
                    </td>
                    <td>
                      <input type="checkbox" checked={client.include_interest} onChange={(event) => setClients((current) => current.map((item) => (item.client_key === client.client_key ? { ...item, include_interest: event.target.checked, dirty: true } : item)))} />
                    </td>
                    <td>
                      <input value={client.notes ?? ""} onChange={(event) => setClients((current) => current.map((item) => (item.client_key === client.client_key ? { ...item, notes: event.target.value, dirty: true } : item)))} />
                    </td>
                  </tr>
                ))}
                {!clients.length ? (
                  <tr>
                    <td colSpan={8}>Nenhum cliente encontrado.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-layout">
      {view === "invoices" ? renderInvoiceTable() : renderBoletosTable()}
      {renderClientsModal()}
      {renderC6UploadModal()}
      {renderCustomerDataModal()}
      {renderStandaloneBoletoModal()}
    </div>
  );
}

export type { BillingView };

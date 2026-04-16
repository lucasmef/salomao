import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { GlobalProductSearchModal } from "./components/GlobalProductSearchModal";
import { RouteLoadingFallback } from "./components/RouteLoadingFallback";
import { SectionChrome } from "./components/SectionChrome";
import { findChildNavItem, legacySectionPathMap, mainNavigation, overviewNavigationItem } from "./data/navigation";
import { downloadFile, fetchJson } from "./lib/api";
import { parseApiError } from "./lib/format";
import { LoginPage } from "./pages/LoginPage";
import type {
  Account,
  AuthUser,
  BackupRead,
  BoletoDashboard,
  CashflowOverview,
  CollectionSeason,
  Category,
  CategoryLookups,
  DashboardOverview,
  FeedbackState,
  FinancialEntryBulkDeleteResponse,
  FinancialEntryBulkCategoryUpdateResponse,
  FinancialEntryListResponse,
  ImportResult,
  ImportSummary,
  InstanceInfo,
  LinxCustomerDirectory,
  LinxMovementDirectory,
  LinxOpenReceivableDirectory,
  LinxProductDirectory,
  LinxProductSearchResult,
  LoanContract,
  LoginResponse,
  LinxSettings,
  LinxSettingsUpdatePayload,
  MfaSetup,
  MfaStatus,
  PurchaseBrand,
  PurchaseInvoiceDraft,
  PurchasePlanningOverview,
  PurchaseReturn,
  ReportConfig,
  RecurrenceRule,
  ReportsOverview,
  ReconciliationWorklist,
  SectionId,
  Supplier,
  Transfer,
  UserCredentialsUpdatePayload,
} from "./types";

type SessionState = {
  token: string | null;
  user: AuthUser;
};

type PendingAuthState = {
  status: "mfa_required" | "mfa_setup_required";
  pendingToken: string;
  user: AuthUser;
  mfaSetup: MfaSetup | null;
};

function toDateInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

function getCurrentMonthRange() {
  const today = new Date();
  return {
    start: toDateInput(new Date(today.getFullYear(), today.getMonth(), 1)),
    end: toDateInput(new Date(today.getFullYear(), today.getMonth() + 1, 0)),
  };
}

function getDefaultPurchasePlanningFilters() {
  return {
    year: "",
    brand_id: "",
    supplier_id: "",
    collection_id: "",
    status: "",
  };
}

function getDefaultEntryFilters(): Record<string, string | boolean> {
  const { start, end } = getCurrentMonthRange();
  return {
    page: "1",
    page_size: "50",
    status: "",
    statuses: "",
    entry_type: "",
    entry_types: "",
    reconciled: false,
    account_id: "",
    category_id: "",
    report_group: "",
    source_system: "",
    counterparty_name: "",
    document_number: "",
    search: "",
    date_field: "due_date",
    date_from: start,
    date_to: end,
    include_legacy: false,
  };
}

function getDefaultCashflowFilters() {
  const { start, end } = getCurrentMonthRange();
  return {
    start,
    end,
    account_id: "",
    include_purchase_planning: true,
    include_crediario_receivables: true,
  };
}

const emptyImportSummary: ImportSummary = {
  import_batches: [],
  sales_snapshot_count: 0,
  receivable_title_count: 0,
  bank_transaction_count: 0,
  historical_cashbook_count: 0,
  latest_ofx_transaction_date: null,
};

const emptyEntryList: FinancialEntryListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_amount: "0.00",
  paid_amount: "0.00",
};

const emptyCashflow: CashflowOverview = {
  current_balance: "0.00",
  projected_inflows: "0.00",
  projected_outflows: "0.00",
  planned_purchase_outflows: "0.00",
  projected_ending_balance: "0.00",
  alerts: [],
  account_balances: [],
  daily_projection: [],
  weekly_projection: [],
  monthly_projection: [],
};
const emptyPurchasePlanning: PurchasePlanningOverview = {
  summary: {
    purchased_total: "0.00",
    delivered_total: "0.00",
    launched_financial_total: "0.00",
    paid_total: "0.00",
    outstanding_goods_total: "0.00",
    delivered_not_recorded_total: "0.00",
    outstanding_payable_total: "0.00",
  },
  rows: [],
  cost_totals: [],
  monthly_projection: [],
  invoices: [],
  open_installments: [],
  plans: [],
  ungrouped_suppliers: [],
};

const emptyReports: ReportsOverview = {
  dre: {
    period_label: "",
    gross_revenue: "0.00",
    deductions: "0.00",
    net_revenue: "0.00",
    cmv: "0.00",
    gross_profit: "0.00",
    other_operating_income: "0.00",
    operating_expenses: "0.00",
    financial_expenses: "0.00",
    non_operating_income: "0.00",
    non_operating_expenses: "0.00",
    taxes_on_profit: "0.00",
    net_profit: "0.00",
    profit_distribution: "0.00",
    remaining_profit: "0.00",
    dashboard_cards: [],
    statement: [],
  },
  dro: {
    period_label: "",
    bank_revenue: "0.00",
    sales_taxes: "0.00",
    purchases_paid: "0.00",
    contribution_margin: "0.00",
    operating_expenses: "0.00",
    financial_expenses: "0.00",
    non_operating_income: "0.00",
    non_operating_expenses: "0.00",
    net_profit: "0.00",
    profit_distribution: "0.00",
    remaining_profit: "0.00",
    dashboard_cards: [],
    statement: [],
  },
};
const emptyReconciliation: ReconciliationWorklist = {
  unreconciled_count: 0,
  overall_unreconciled_count: 0,
  matched_count: 0,
  total: 0,
  page: 1,
  page_size: 200,
  total_account_balance: "0.00",
  account_balances: [],
  items: [],
};
const emptyDashboard: DashboardOverview = {
  period_label: "",
  kpis: {
    gross_revenue: "0.00",
    net_revenue: "0.00",
    cmv: "0.00",
    purchases_paid: "0.00",
    operating_expenses: "0.00",
    financial_expenses: "0.00",
    net_profit: "0.00",
    profit_distribution: "0.00",
    remaining_profit: "0.00",
    current_balance: "0.00",
    projected_balance: "0.00",
    overdue_payables: 0,
    overdue_receivables: 0,
    pending_reconciliations: 0,
  },
  dre_cards: [],
  dre_chart: [],
  revenue_comparison: {
    current_year: new Date().getFullYear(),
    previous_year: new Date().getFullYear() - 1,
    points: [],
  },
  account_balances: [],
  overdue_payables: [],
  overdue_receivables: [],
  pending_reconciliations: 0,
};

const emptyLookups: CategoryLookups = { group_options: [], subgroup_options: [] };
const emptyBoletoDashboard: BoletoDashboard = {
  generated_at: "",
  files: [],
  summary: {
    receivable_count: 0,
    receivable_total: "0.00",
    boleto_count: 0,
    overdue_boleto_count: 0,
    overdue_invoice_client_count: 0,
    paid_pending_count: 0,
    missing_boleto_count: 0,
    excess_boleto_count: 0,
    boleto_clients_count: 0,
  },
  clients: [],
  receivables: [],
  open_boletos: [],
  overdue_boletos: [],
  overdue_invoices: [],
  paid_pending: [],
  missing_boletos: [],
  excess_boletos: [],
  standalone_boletos: [],
};

function normalizeBoletoDashboard(payload: Partial<BoletoDashboard> | null | undefined): BoletoDashboard {
  const nextDashboard = payload ?? {};
  const safeFiles = Array.isArray(nextDashboard.files)
    ? nextDashboard.files.filter(
        (item): item is BoletoDashboard["files"][number] =>
          Boolean(item) && typeof item === "object" && "source_type" in item,
      )
    : emptyBoletoDashboard.files;
  const safeClients = Array.isArray(nextDashboard.clients)
    ? nextDashboard.clients.filter(
        (item): item is BoletoDashboard["clients"][number] =>
          Boolean(item) && typeof item === "object" && "client_key" in item,
      )
    : emptyBoletoDashboard.clients;
  const safeReceivables = Array.isArray(nextDashboard.receivables)
    ? nextDashboard.receivables.filter(
        (item): item is BoletoDashboard["receivables"][number] =>
          Boolean(item) && typeof item === "object" && "document" in item,
      )
    : emptyBoletoDashboard.receivables;
  const safeOpenBoletos = Array.isArray(nextDashboard.open_boletos)
    ? nextDashboard.open_boletos.filter(
        (item): item is BoletoDashboard["open_boletos"][number] =>
          Boolean(item) && typeof item === "object" && "id" in item,
      )
    : emptyBoletoDashboard.open_boletos;
  const safeOverdueBoletos = Array.isArray(nextDashboard.overdue_boletos)
    ? nextDashboard.overdue_boletos.filter(
        (item): item is BoletoDashboard["overdue_boletos"][number] =>
          Boolean(item) && typeof item === "object" && "selection_key" in item,
      )
    : emptyBoletoDashboard.overdue_boletos;
  const safeOverdueInvoices = Array.isArray(nextDashboard.overdue_invoices)
    ? nextDashboard.overdue_invoices.filter(
        (item): item is BoletoDashboard["overdue_invoices"][number] =>
          Boolean(item) && typeof item === "object" && "client_name" in item,
      )
    : emptyBoletoDashboard.overdue_invoices;
  const safePaidPending = Array.isArray(nextDashboard.paid_pending)
    ? nextDashboard.paid_pending.filter(
        (item): item is BoletoDashboard["paid_pending"][number] =>
          Boolean(item) && typeof item === "object" && "selection_key" in item,
      )
    : emptyBoletoDashboard.paid_pending;
  const safeMissingBoletos = Array.isArray(nextDashboard.missing_boletos)
    ? nextDashboard.missing_boletos.filter(
        (item): item is BoletoDashboard["missing_boletos"][number] =>
          Boolean(item) && typeof item === "object" && "selection_key" in item,
      )
    : emptyBoletoDashboard.missing_boletos;
  const safeExcessBoletos = Array.isArray(nextDashboard.excess_boletos)
    ? nextDashboard.excess_boletos.filter(
        (item): item is BoletoDashboard["excess_boletos"][number] =>
          Boolean(item) && typeof item === "object" && "selection_key" in item,
      )
    : emptyBoletoDashboard.excess_boletos;
  const safeStandaloneBoletos = Array.isArray(nextDashboard.standalone_boletos)
    ? nextDashboard.standalone_boletos.filter(
        (item): item is BoletoDashboard["standalone_boletos"][number] =>
          Boolean(item) && typeof item === "object" && "id" in item,
      )
    : emptyBoletoDashboard.standalone_boletos;
  return {
    ...emptyBoletoDashboard,
    ...nextDashboard,
    summary: {
      ...emptyBoletoDashboard.summary,
      ...(nextDashboard.summary ?? {}),
    },
    files: safeFiles,
    clients: safeClients,
    receivables: safeReceivables,
    open_boletos: safeOpenBoletos,
    overdue_boletos: safeOverdueBoletos,
    overdue_invoices: safeOverdueInvoices,
    paid_pending: safePaidPending,
    missing_boletos: safeMissingBoletos,
    excess_boletos: safeExcessBoletos,
    standalone_boletos: safeStandaloneBoletos.map((item) => ({
      ...item,
      bank: item.bank ?? "INTER",
      client_name: item.client_name ?? "",
      document_id: item.document_id ?? "",
      paid_amount: item.paid_amount ?? "0.00",
      status: item.status ?? "",
      local_status: item.local_status ?? "open",
      description: item.description ?? null,
      notes: item.notes ?? null,
      tax_id: item.tax_id ?? null,
      email: item.email ?? null,
      barcode: item.barcode ?? null,
      linha_digitavel: item.linha_digitavel ?? null,
      pix_copia_e_cola: item.pix_copia_e_cola ?? null,
      inter_codigo_solicitacao: item.inter_codigo_solicitacao ?? null,
      inter_account_id: item.inter_account_id ?? null,
      pdf_available: Boolean(item.pdf_available),
      downloaded_at: item.downloaded_at ?? null,
    })),
  };
}

const emptyLinxCustomerDirectory: LinxCustomerDirectory = {
  generated_at: "",
  summary: {
    total_count: 0,
    client_count: 0,
    supplier_count: 0,
    transporter_count: 0,
    active_count: 0,
    boleto_enabled_count: 0,
  },
  items: [],
};
const emptyLinxProductDirectory: LinxProductDirectory = {
  generated_at: "",
  summary: {
    total_count: 0,
    active_count: 0,
    inactive_count: 0,
    with_supplier_count: 0,
    with_collection_count: 0,
  },
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
};
const emptyLinxProductSearchResult: LinxProductSearchResult = {
  generated_at: "",
  query: "",
  total: 0,
  items: [],
};
const emptyLinxMovementDirectory: LinxMovementDirectory = {
  generated_at: "",
  summary: {
    total_count: 0,
    sales_total_amount: "0.00",
    sales_return_total_amount: "0.00",
    purchases_total_amount: "0.00",
    purchase_returns_total_amount: "0.00",
  },
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
};
const emptyLinxOpenReceivableDirectory: LinxOpenReceivableDirectory = {
  generated_at: "",
  summary: {
    total_count: 0,
    overdue_count: 0,
    due_today_count: 0,
    total_amount: "0.00",
  },
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
};

const RECONCILIATION_WORKLIST_LIMIT = 200;

const BoletosPage = lazy(() => import("./pages/BoletosPage").then((module) => ({ default: module.BoletosPage })));
const CadastrosClientsPage = lazy(() =>
  import("./pages/CadastrosClientsPage").then((module) => ({ default: module.CadastrosClientsPage })),
);
const CadastrosProductsPage = lazy(() =>
  import("./pages/CadastrosProductsPage").then((module) => ({ default: module.CadastrosProductsPage })),
);
const CadastrosMovementsPage = lazy(() =>
  import("./pages/CadastrosMovementsPage").then((module) => ({ default: module.CadastrosMovementsPage })),
);
const CadastrosOpenReceivablesPage = lazy(() =>
  import("./pages/CadastrosOpenReceivablesPage").then((module) => ({ default: module.CadastrosOpenReceivablesPage })),
);
const CadastrosRulesPage = lazy(() =>
  import("./pages/CadastrosRulesPage").then((module) => ({ default: module.CadastrosRulesPage })),
);
const CashflowPage = lazy(() => import("./pages/CashflowPage").then((module) => ({ default: module.CashflowPage })));
const EntriesPage = lazy(() => import("./pages/EntriesPage").then((module) => ({ default: module.EntriesPage })));
const MasterDataPage = lazy(() =>
  import("./pages/MasterDataPage").then((module) => ({ default: module.MasterDataPage })),
);
const OperationsPage = lazy(() =>
  import("./pages/OperationsPage").then((module) => ({ default: module.OperationsPage })),
);
const OverviewSectionPage = lazy(() =>
  import("./pages/OverviewSectionPage").then((module) => ({ default: module.OverviewSectionPage })),
);
const PurchasePlanningPage = lazy(() =>
  import("./pages/PurchasePlanningPage").then((module) => ({ default: module.PurchasePlanningPage })),
);
const ReconciliationPage = lazy(() =>
  import("./pages/ReconciliationPage").then((module) => ({ default: module.ReconciliationPage })),
);
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage })));
const ResultsComparativesPage = lazy(() =>
  import("./pages/ResultsComparativesPage").then((module) => ({ default: module.ResultsComparativesPage })),
);
const SecurityPage = lazy(() => import("./pages/SecurityPage").then((module) => ({ default: module.SecurityPage })));
const SystemImportsGeneralPage = lazy(() =>
  import("./pages/SystemImportsGeneralPage").then((module) => ({ default: module.SystemImportsGeneralPage })),
);

function buildQuery(params: Record<string, string | boolean | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "" || value === false) {
      return;
    }
    query.set(key, String(value));
  });
  return query.toString();
}

function buildCashflowQuery(params: {
  start: string;
  end: string;
  account_id: string;
  include_purchase_planning: boolean;
  include_crediario_receivables: boolean;
}, options?: { refresh?: boolean }) {
  const query = new URLSearchParams();
  query.set("start", params.start);
  query.set("end", params.end);
  if (params.account_id) {
    query.set("account_id", params.account_id);
  }
  query.set("include_purchase_planning", String(params.include_purchase_planning));
  query.set("include_crediario_receivables", String(params.include_crediario_receivables));
  if (options?.refresh) {
    query.set("refresh", "true");
  }
  return query.toString();
}

async function fetchOverviewSnapshot(
  activeSession: SessionState,
  filters: { start: string; end: string },
  options?: { refresh?: boolean },
) {
  return fetchJson<DashboardOverview>(
    `/dashboard/overview?${buildQuery({ ...filters, refresh: options?.refresh ?? false })}`,
    { token: activeSession.token },
  );
}

async function fetchCashflowSnapshot(
  activeSession: SessionState,
  filters: {
    start: string;
    end: string;
    account_id: string;
    include_purchase_planning: boolean;
    include_crediario_receivables: boolean;
  },
  options?: { refresh?: boolean },
) {
  return fetchJson<CashflowOverview>(`/cashflow/overview?${buildCashflowQuery(filters, options)}`, {
    token: activeSession.token,
  });
}

async function fetchReportsSnapshot(
  activeSession: SessionState,
  filters: { start: string; end: string },
  options?: { refresh?: boolean },
) {
  return fetchJson<ReportsOverview>(
    `/reports/overview?${buildQuery({ ...filters, refresh: options?.refresh ?? false })}`,
    { token: activeSession.token },
  );
}

function getNavigationSection(key: string) {
  if (key === "overview") {
    return overviewNavigationItem;
  }
  return mainNavigation.find((item) => item.key === key) ?? mainNavigation[0];
}

function normalizePath(pathname: string) {
  const normalized = pathname.replace(/\/+$/, "");
  return normalized || "/";
}

function getPurchasePlanningMode(pathname: string): "summary" | "planning" | "returns" {
  const normalizedPath = normalizePath(pathname);
  if (normalizedPath === "/compras/resumo") {
    return "summary";
  }
  if (normalizedPath === "/compras/devolucoes") {
    return "returns";
  }
  return "planning";
}

function getPurchasePlanningRequestFilters(
  filters: ReturnType<typeof getDefaultPurchasePlanningFilters>,
  mode: "summary" | "planning" | "returns",
) {
  if (mode !== "planning") {
    return filters;
  }
  return {
    ...filters,
    year: "",
    brand_id: "",
    supplier_id: "",
    collection_id: "",
  };
}

function getLegacySectionsForPath(pathname: string): SectionId[] {
  const currentPath = normalizePath(pathname);

  if (currentPath.startsWith("/overview")) {
    return ["overview"];
  }
  if (currentPath === "/financeiro/lancamentos" || currentPath === "/financeiro/em-aberto") {
    return ["lancamentos"];
  }
  if (currentPath === "/financeiro/conciliacao") {
    return ["conciliacao", "importacoes"];
  }
  if (currentPath === "/financeiro/cobranca" || currentPath.startsWith("/financeiro/cobranca/")) {
    return ["boletos", "caixa", "importacoes"];
  }
  if (currentPath === "/financeiro/importacoes") {
    return ["importacoes"];
  }
  if (currentPath.startsWith("/compras")) {
    return ["planejamento"];
  }
  if (currentPath === "/caixa-resultados/fluxo-caixa") {
    return ["caixa"];
  }
  if (currentPath === "/caixa-resultados/dre" || currentPath === "/caixa-resultados/dro") {
    return ["relatorios", "importacoes"];
  }
  if (currentPath === "/caixa-resultados/projecoes") {
    return ["operacoes", "caixa"];
  }
  if (currentPath === "/caixa-resultados/comparativos") {
    return ["overview"];
  }
  if (currentPath === "/cadastros/contas" || currentPath === "/cadastros/categorias") {
    return ["cadastros"];
  }
  if (currentPath === "/cadastros/clientes") {
    return ["cadastros", "importacoes"];
  }
  if (currentPath === "/cadastros/produtos") {
    return ["cadastros", "importacoes"];
  }
  if (currentPath === "/cadastros/movimentos") {
    return ["cadastros", "importacoes"];
  }
  if (currentPath === "/cadastros/faturas-a-receber") {
    return ["cadastros", "importacoes"];
  }
  if (currentPath === "/cadastros/regras") {
    return ["operacoes"];
  }
  if (currentPath === "/sistema/usuarios" || currentPath === "/sistema/backup" || currentPath === "/sistema/seguranca") {
    return ["seguranca"];
  }
  if (currentPath === "/sistema/importacoes-gerais") {
    return ["importacoes"];
  }
  if (currentPath === "/sistema/auditoria") {
    return ["importacoes"];
  }
  return ["overview"];
}

function DevBanner() {
  const hostname = window.location.hostname;
  const isDev = hostname.includes("100.") || hostname.includes(".ts.net") || hostname.includes("salomao-vps") || hostname === "localhost" || hostname === "127.0.0.1";
  if (!isDev) return null;
  return (
    <div style={{ background: "#ff9800", color: "#fff", textAlign: "center", padding: "4px", fontSize: "12px", fontWeight: "bold", position: "fixed", top: 0, width: "100%", zIndex: 99999 }}>
       AMBIENTE DE DESENVOLVIMENTO / HOMOLOGAÇÃO
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <DevBanner />
      <AppRuntime />
    </BrowserRouter>
  );
}

function AppRuntime() {
  const location = useLocation();
  const autoLoadingSectionKeysRef = useRef<Set<string>>(new Set());
  const [session, setSession] = useState<SessionState | null>(null);
  const [pendingAuth, setPendingAuth] = useState<PendingAuthState | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackState>({ tone: "info", message: "" });
  const [toast, setToast] = useState<FeedbackState | null>(null);
  const [showMissingBoletosExportFallback, setShowMissingBoletosExportFallback] = useState(false);
  const [loadedSections, setLoadedSections] = useState<Record<SectionId, boolean>>({
    overview: false,
    cadastros: false,
    lancamentos: false,
    planejamento: false,
    operacoes: false,
    importacoes: false,
    boletos: false,
    conciliacao: false,
    caixa: false,
    relatorios: false,
    seguranca: false,
  });

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [brands, setBrands] = useState<PurchaseBrand[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [purchaseSuppliers, setPurchaseSuppliers] = useState<Supplier[]>([]);
  const [collections, setCollections] = useState<CollectionSeason[]>([]);
  const [categoryLookups, setCategoryLookups] = useState<CategoryLookups>(emptyLookups);
  const [entryList, setEntryList] = useState<FinancialEntryListResponse>(emptyEntryList);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [recurrences, setRecurrences] = useState<RecurrenceRule[]>([]);
  const [loans, setLoans] = useState<LoanContract[]>([]);
  const [importSummary, setImportSummary] = useState<ImportSummary>(emptyImportSummary);
  const [boletoDashboard, setBoletoDashboard] = useState<BoletoDashboard>(emptyBoletoDashboard);
  const [linxCustomerDirectory, setLinxCustomerDirectory] = useState<LinxCustomerDirectory>(emptyLinxCustomerDirectory);
  const [linxProductDirectory, setLinxProductDirectory] = useState<LinxProductDirectory>(emptyLinxProductDirectory);
  const [globalProductSearchInput, setGlobalProductSearchInput] = useState("");
  const [globalProductSearchResult, setGlobalProductSearchResult] = useState<LinxProductSearchResult>(
    emptyLinxProductSearchResult,
  );
  const [globalProductSearchModalOpen, setGlobalProductSearchModalOpen] = useState(false);
  const [globalProductSearchLoading, setGlobalProductSearchLoading] = useState(false);
  const [linxMovementDirectory, setLinxMovementDirectory] = useState<LinxMovementDirectory>(emptyLinxMovementDirectory);
  const [linxOpenReceivableDirectory, setLinxOpenReceivableDirectory] = useState<LinxOpenReceivableDirectory>(
    emptyLinxOpenReceivableDirectory,
  );
  const [showAllMonthlyMissingBoletos, setShowAllMonthlyMissingBoletos] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardOverview>(emptyDashboard);
  const [cashflow, setCashflow] = useState<CashflowOverview>(emptyCashflow);
  const [purchasePlanning, setPurchasePlanning] = useState<PurchasePlanningOverview>(emptyPurchasePlanning);
  const [purchaseReturns, setPurchaseReturns] = useState<PurchaseReturn[]>([]);
  const [reconciliation, setReconciliation] = useState<ReconciliationWorklist>(emptyReconciliation);
  const [reports, setReports] = useState<ReportsOverview>(emptyReports);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [backups, setBackups] = useState<BackupRead[]>([]);
  const [instanceInfo, setInstanceInfo] = useState<InstanceInfo | null>(null);
  const [linxSettings, setLinxSettings] = useState<LinxSettings | null>(null);
  const [mfaStatus, setMfaStatus] = useState<MfaStatus | null>(null);
  const [activeMfaSetup, setActiveMfaSetup] = useState<MfaSetup | null>(null);
  const [purchasePlanningLoadedMode, setPurchasePlanningLoadedMode] = useState<"summary" | "planning" | "returns" | null>(null);
  const [cadastrosLoadedPath, setCadastrosLoadedPath] = useState<string | null>(null);

  const [overviewFilters, setOverviewFilters] = useState(() => getCurrentMonthRange());
  const [entryFilters, setEntryFilters] = useState<Record<string, string | boolean>>(() => getDefaultEntryFilters());
  const [cashflowFilters, setCashflowFilters] = useState(() => getDefaultCashflowFilters());
  const [purchasePlanningFilters, setPurchasePlanningFilters] = useState(() => getDefaultPurchasePlanningFilters());
  const [linxProductFilters, setLinxProductFilters] = useState({
    search: "",
    status: "all",
    page: 1,
    page_size: 50,
  });
  const [linxMovementFilters, setLinxMovementFilters] = useState({
    search: "",
    group: "all",
    movement_type: "all",
    page: 1,
    page_size: 50,
  });
  const [linxOpenReceivableFilters, setLinxOpenReceivableFilters] = useState({
    search: "",
    page: 1,
    page_size: 50,
  });
  const [reportFilters, setReportFilters] = useState(() => getCurrentMonthRange());
  const [reconciliationFilters, setReconciliationFilters] = useState({
    account_id: "",
    ...getCurrentMonthRange(),
  });

  useEffect(() => {
    void bootstrapSession();
  }, []);

  useEffect(() => {
    if (session) {
      setLoadedSections({
        overview: false,
        cadastros: false,
        lancamentos: false,
        planejamento: false,
        operacoes: false,
        importacoes: false,
        boletos: false,
        conciliacao: false,
        caixa: false,
        relatorios: false,
        seguranca: false,
      });
      setPurchasePlanningLoadedMode(null);
      setCadastrosLoadedPath(null);
      setShowAllMonthlyMissingBoletos(false);
      setPendingAuth(null);
      void loadBaseData(session);
    }
  }, [session]);

  useEffect(() => {
    const defaultOfxAccount = accounts.find((account) => account.is_active && account.import_ofx_enabled);
    if (!defaultOfxAccount) {
      return;
    }
    setReconciliationFilters((current) => {
      const currentAccountIsValid = accounts.some(
        (account) => account.id === current.account_id && account.is_active && account.import_ofx_enabled,
      );
      if (currentAccountIsValid) {
        return current;
      }
      return { ...current, account_id: defaultOfxAccount.id };
    });
  }, [accounts]);

  useEffect(() => {
    if (!session) {
      return;
    }
    const requiredSections = getLegacySectionsForPath(location.pathname);
    const requiredPurchasePlanningMode = getPurchasePlanningMode(location.pathname);
    void (async () => {
      for (const targetSection of requiredSections) {
        const requiresPurchaseReload =
          targetSection === "planejamento" && purchasePlanningLoadedMode !== requiredPurchasePlanningMode;
        const requiresCadastrosReload =
          targetSection === "cadastros" && cadastrosLoadedPath !== normalizePath(location.pathname);
        if (!loadedSections[targetSection] || requiresPurchaseReload || requiresCadastrosReload) {
          const loadKey =
            targetSection === "planejamento"
              ? `${targetSection}:${requiredPurchasePlanningMode}`
              : targetSection === "cadastros"
                ? `${targetSection}:${normalizePath(location.pathname)}`
                : targetSection;
          if (autoLoadingSectionKeysRef.current.has(loadKey)) {
            continue;
          }
          autoLoadingSectionKeysRef.current.add(loadKey);
          try {
            await loadSectionData(session, targetSection, { force: true });
          } finally {
            autoLoadingSectionKeysRef.current.delete(loadKey);
          }
        }
      }
    })();
  }, [cadastrosLoadedPath, loadedSections, location.pathname, purchasePlanningLoadedMode, session]);

  useEffect(() => {
    if (!feedback.message) {
      return;
    }
    setToast(feedback);
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  async function bootstrapSession() {
    try {
      const [instance, user] = await Promise.all([
        fetchJson<InstanceInfo>("/meta/instance"),
        fetchJson<AuthUser>("/auth/me"),
      ]);
      setInstanceInfo(instance);
      setSession({ token: null, user });
      const status = await fetchJson<MfaStatus>("/auth/mfa/status");
      setMfaStatus(status);
    } catch {
      setSession(null);
      setPendingAuth(null);
      try {
        const instance = await fetchJson<InstanceInfo>("/meta/instance");
        setInstanceInfo(instance);
      } catch {
        setInstanceInfo(null);
      }
    } finally {
      setAuthLoading(false);
    }
  }

  async function loadBaseData(activeSession: SessionState) {
    setLoading(true);
    try {
      const [accountData, categoryData, categoryLookupData, brandData, supplierData, purchaseSupplierData, collectionData] = await Promise.all([
        fetchJson<Account[]>("/accounts", { token: activeSession.token }),
        fetchJson<Category[]>("/categories", { token: activeSession.token }),
        fetchJson<CategoryLookups>("/categories/lookups", { token: activeSession.token }),
        fetchJson<PurchaseBrand[]>("/brands", { token: activeSession.token }),
        fetchJson<Supplier[]>("/suppliers", { token: activeSession.token }),
        fetchJson<Supplier[]>("/purchase-suppliers", { token: activeSession.token }),
        fetchJson<CollectionSeason[]>("/collections", { token: activeSession.token }),
      ]);

      setAccounts(accountData);
      setCategories(categoryData);
      setCategoryLookups(categoryLookupData);
      setBrands(brandData);
      setSuppliers(supplierData);
      setPurchaseSuppliers(purchaseSupplierData);
      setCollections(collectionData);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setLoading(false);
    }
  }

  async function fetchBoletoDashboard(activeSession: SessionState, includeAllMonthlyMissing = showAllMonthlyMissingBoletos) {
    const query = includeAllMonthlyMissing ? "?include_all_monthly_missing=true" : "";
    const boletoData = await fetchJson<BoletoDashboard>(`/boletos/dashboard${query}`, { token: activeSession.token });
    setBoletoDashboard(normalizeBoletoDashboard(boletoData));
  }

  async function fetchLinxCustomerDirectory(activeSession: SessionState) {
    const response = await fetchJson<LinxCustomerDirectory>("/linx-customers", { token: activeSession.token });
    setLinxCustomerDirectory(response);
  }

  async function fetchLinxProductDirectory(
    activeSession: SessionState,
    overrides?: Partial<typeof linxProductFilters>,
  ) {
    const nextFilters = {
      ...linxProductFilters,
      ...overrides,
    };
    const query = new URLSearchParams();
    query.set("page", String(nextFilters.page));
    query.set("page_size", String(nextFilters.page_size));
    if (nextFilters.search.trim()) {
      query.set("search", nextFilters.search.trim());
    }
    if (nextFilters.status && nextFilters.status !== "all") {
      query.set("status", nextFilters.status);
    }
    const response = await fetchJson<LinxProductDirectory>(`/linx-products?${query.toString()}`, {
      token: activeSession.token,
    });
    setLinxProductDirectory(response);
    setLinxProductFilters(nextFilters);
  }

  async function searchProductsGlobally(rawQuery: string) {
    if (!session) return;
    const trimmedQuery = rawQuery.trim();
    setGlobalProductSearchInput(rawQuery);
    if (trimmedQuery.length < 2) {
      setFeedback({ tone: "info", message: "Digite pelo menos 2 caracteres para buscar produtos." });
      return;
    }

    setGlobalProductSearchModalOpen(true);
    setGlobalProductSearchLoading(true);
    try {
      const query = new URLSearchParams();
      query.set("q", trimmedQuery);
      query.set("limit", "60");
      const response = await fetchJson<LinxProductSearchResult>(`/linx-products/search?${query.toString()}`, {
        token: session.token,
      });
      setGlobalProductSearchResult(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setGlobalProductSearchLoading(false);
    }
  }

  async function fetchLinxMovementDirectory(
    activeSession: SessionState,
    overrides?: Partial<typeof linxMovementFilters>,
  ) {
    const nextFilters = {
      ...linxMovementFilters,
      ...overrides,
    };
    const query = new URLSearchParams();
    query.set("page", String(nextFilters.page));
    query.set("page_size", String(nextFilters.page_size));
    if (nextFilters.search.trim()) {
      query.set("search", nextFilters.search.trim());
    }
    if (nextFilters.group && nextFilters.group !== "all") {
      query.set("group", nextFilters.group);
    }
    if (nextFilters.movement_type && nextFilters.movement_type !== "all") {
      query.set("movement_type", nextFilters.movement_type);
    }
    const response = await fetchJson<LinxMovementDirectory>(`/linx-movements?${query.toString()}`, {
      token: activeSession.token,
    });
    setLinxMovementDirectory(response);
    setLinxMovementFilters(nextFilters);
  }

  async function fetchLinxOpenReceivableDirectory(
    activeSession: SessionState,
    overrides?: Partial<typeof linxOpenReceivableFilters>,
  ) {
    const nextFilters = {
      ...linxOpenReceivableFilters,
      ...overrides,
    };
    const query = new URLSearchParams();
    query.set("page", String(nextFilters.page));
    query.set("page_size", String(nextFilters.page_size));
    if (nextFilters.search.trim()) {
      query.set("search", nextFilters.search.trim());
    }
    const response = await fetchJson<LinxOpenReceivableDirectory>(
      `/linx-open-receivables?${query.toString()}`,
      { token: activeSession.token },
    );
    setLinxOpenReceivableDirectory(response);
    setLinxOpenReceivableFilters(nextFilters);
  }

  async function loadSectionData(activeSession: SessionState, targetSection: SectionId, options?: { force?: boolean }) {
    if (!options?.force && loadedSections[targetSection]) {
      return;
    }
    const isInitialSectionLoad = !loadedSections[targetSection];
    setLoading(true);
    try {
      switch (targetSection) {
        case "overview": {
          const effectiveOverviewFilters = isInitialSectionLoad ? getCurrentMonthRange() : overviewFilters;
          if (isInitialSectionLoad) {
            setOverviewFilters(effectiveOverviewFilters);
          }
          const [dashboardData, reportsData] = await Promise.all([
            fetchOverviewSnapshot(activeSession, effectiveOverviewFilters),
            fetchReportsSnapshot(activeSession, effectiveOverviewFilters),
          ]);
          setDashboard(dashboardData);
          setReports(reportsData);
          setReportFilters(effectiveOverviewFilters);
          break;
        }
        case "lancamentos": {
          const effectiveEntryFilters = isInitialSectionLoad ? getDefaultEntryFilters() : entryFilters;
          if (isInitialSectionLoad) {
            setEntryFilters(effectiveEntryFilters);
          }
          const entryData = await fetchJson<FinancialEntryListResponse>(
            `/entries?${buildQuery(effectiveEntryFilters)}`,
            { token: activeSession.token },
          );
          setEntryList(entryData);
          break;
        }
        case "planejamento": {
          const planningMode = getPurchasePlanningMode(location.pathname);
          const effectivePurchaseFilters = isInitialSectionLoad ? getDefaultPurchasePlanningFilters() : purchasePlanningFilters;
          if (isInitialSectionLoad) {
            setPurchasePlanningFilters(effectivePurchaseFilters);
          }
          const planningQuery = buildQuery({
            ...getPurchasePlanningRequestFilters(effectivePurchaseFilters, planningMode),
            mode: planningMode,
          });
          const [planningData, returnsData] = await Promise.all([
            fetchJson<PurchasePlanningOverview>(`/purchase-planning/overview?${planningQuery}`, {
              token: activeSession.token,
            }),
            fetchJson<PurchaseReturn[]>("/purchase-returns?limit=500", {
              token: activeSession.token,
            })
          ]);
          setPurchasePlanning(planningData);
          setPurchaseReturns(returnsData);
          setPurchasePlanningLoadedMode(planningMode);
          break;
        }
        case "operacoes": {
          const [transferData, recurrenceData, loanData] = await Promise.all([
            fetchJson<Transfer[]>("/transfers?limit=50", { token: activeSession.token }),
            fetchJson<RecurrenceRule[]>("/recurrences?limit=50", { token: activeSession.token }),
            fetchJson<LoanContract[]>("/loans?limit=20", { token: activeSession.token }),
          ]);
          setTransfers(transferData);
          setRecurrences(recurrenceData);
          setLoans(loanData);
          break;
        }
        case "cadastros": {
          if (location.pathname === "/cadastros/clientes") {
            await fetchLinxCustomerDirectory(activeSession);
          } else if (location.pathname === "/cadastros/produtos") {
            await fetchLinxProductDirectory(activeSession);
          } else if (location.pathname === "/cadastros/movimentos") {
            await fetchLinxMovementDirectory(activeSession);
          } else if (location.pathname === "/cadastros/faturas-a-receber") {
            await fetchLinxOpenReceivableDirectory(activeSession);
          }
          break;
        }
        case "importacoes": {
          const importData = await fetchJson<ImportSummary>("/imports/summary", { token: activeSession.token });
          setImportSummary(importData);
          break;
        }
        case "boletos": {
          await fetchBoletoDashboard(activeSession);
          break;
        }
        case "conciliacao": {
          const effectiveReconciliationFilters = isInitialSectionLoad
            ? { ...reconciliationFilters, ...getCurrentMonthRange() }
            : reconciliationFilters;
          if (isInitialSectionLoad) {
            setReconciliationFilters(effectiveReconciliationFilters);
          }
          const reconciliationData = await fetchJson<ReconciliationWorklist>(
            `/reconciliation/worklist?${buildQuery({
              ...effectiveReconciliationFilters,
              page: "1",
              limit: String(RECONCILIATION_WORKLIST_LIMIT),
            })}`,
            { token: activeSession.token },
          );
          setReconciliation(reconciliationData);
          break;
        }
        case "caixa": {
          const effectiveCashflowFilters = isInitialSectionLoad ? getDefaultCashflowFilters() : cashflowFilters;
          if (isInitialSectionLoad) {
            setCashflowFilters(effectiveCashflowFilters);
          }
          const cashflowData = await fetchCashflowSnapshot(activeSession, effectiveCashflowFilters);
          setCashflow(cashflowData);
          break;
        }
        case "relatorios": {
          const effectiveReportFilters = isInitialSectionLoad ? getCurrentMonthRange() : reportFilters;
          if (isInitialSectionLoad) {
            setReportFilters(effectiveReportFilters);
          }
          const [reportsData, dashboardData] = await Promise.all([
            fetchReportsSnapshot(activeSession, effectiveReportFilters),
            fetchOverviewSnapshot(activeSession, effectiveReportFilters),
          ]);
          setReports(reportsData);
          setDashboard(dashboardData);
          setOverviewFilters(effectiveReportFilters);
          break;
        }
        case "seguranca": {
          const statusData = await fetchJson<MfaStatus>("/auth/mfa/status", { token: activeSession.token });
          setMfaStatus(statusData);
          if (activeSession.user.role === "admin") {
            const [userData, backupData, linxSettingsData] = await Promise.all([
              fetchJson<AuthUser[]>("/auth/users", { token: activeSession.token }),
              fetchJson<BackupRead[]>("/backup", { token: activeSession.token }),
              fetchJson<LinxSettings>("/company-settings/linx", { token: activeSession.token }),
            ]);
            setUsers(userData);
            setBackups(backupData);
            setLinxSettings(linxSettingsData);
          } else {
            setUsers([]);
            setBackups([]);
            setLinxSettings(null);
          }
          break;
        }
        default:
          break;
      }
      if (targetSection === "cadastros") {
        setCadastrosLoadedPath(normalizePath(location.pathname));
      }
      setLoadedSections((current) => ({ ...current, [targetSection]: true }));
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setLoading(false);
    }
  }

  async function runMutation(
    action: () => Promise<void>,
    successMessage: string,
    options?: { refreshBase?: boolean; sections?: SectionId[] },
  ) {
    if (!session) return;
    setSubmitting(true);
    try {
      await action();
      if (options?.refreshBase) {
        await loadBaseData(session);
      }
      const sectionsToRefresh = options?.sections?.length ? options.sections : getLegacySectionsForPath(location.pathname);
      for (const targetSection of sectionsToRefresh) {
        await loadSectionData(session, targetSection, { force: true });
      }
      setFeedback({ tone: "success", message: successMessage });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogin(email: string, password: string) {
    setSubmitting(true);
    try {
      const response = await fetchJson<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (response.status === "authenticated") {
        setSession({ token: null, user: response.user });
        setPendingAuth(null);
        setFeedback({ tone: "success", message: `Sessao iniciada como ${response.user.full_name}.` });
      } else if (response.pending_token) {
        setPendingAuth({
          status: response.status,
          pendingToken: response.pending_token,
          user: response.user,
          mfaSetup: response.mfa_setup,
        });
        setFeedback({
          tone: "info",
          message:
            response.status === "mfa_setup_required"
              ? "Configure o MFA no autenticador e informe o codigo para concluir o acesso."
              : "Informe o codigo TOTP do autenticador para concluir a entrada.",
        });
      }
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
      setAuthLoading(false);
    }
  }

  async function handleVerifyMfa(code: string, rememberDevice: boolean) {
    if (!pendingAuth) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<LoginResponse>("/auth/mfa/verify", {
        method: "POST",
        body: JSON.stringify({ pending_token: pendingAuth.pendingToken, code, remember_device: rememberDevice }),
      });
      setSession({ token: null, user: response.user });
      setPendingAuth(null);
      setFeedback({ tone: "success", message: `Sessao iniciada como ${response.user.full_name}.` });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmMfaSetup(code: string, rememberDevice: boolean) {
    if (!pendingAuth) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<LoginResponse>("/auth/mfa/enroll/complete", {
        method: "POST",
        body: JSON.stringify({ pending_token: pendingAuth.pendingToken, code, remember_device: rememberDevice }),
      });
      setSession({ token: null, user: response.user });
      setPendingAuth(null);
      setFeedback({ tone: "success", message: "MFA ativado e sessao iniciada com sucesso." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  function handleCancelPendingAuth() {
    setPendingAuth(null);
  }

  async function handleLogout() {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchJson("/auth/logout", { method: "POST", token: session.token });
    } catch {
      // Ignora erro de sessao expirada na limpeza local.
    } finally {
      setSession(null);
      setMfaStatus(null);
      setActiveMfaSetup(null);
      setSubmitting(false);
      setFeedback({ tone: "info", message: "Sessao encerrada." });
    }
  }

  async function createAccount(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/accounts", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Conta criada.", { refreshBase: true });
  }

  async function updateAccount(accountId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/accounts/${accountId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Conta atualizada.", { refreshBase: true });
  }

  async function createCategory(payload: Record<string, unknown>) {
    if (!session) return;
    setSubmitting(true);
    try {
      const createdCategory = await fetchJson<Category>("/categories", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadBaseData(session);
      const sectionsToRefresh = getLegacySectionsForPath(location.pathname);
      for (const targetSection of sectionsToRefresh) {
        await loadSectionData(session, targetSection, { force: true });
      }
      setFeedback({ tone: "success", message: "Categoria criada." });
      return createdCategory;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function updateCategory(categoryId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/categories/${categoryId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Categoria atualizada.", { refreshBase: true });
  }

  async function deleteCategory(categoryId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/categories/${categoryId}`, { method: "DELETE", token: session.token });
    }, "Categoria excluida.", { refreshBase: true });
  }

  async function createEntry(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/entries", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Lançamento criado.", { refreshBase: true });
  }

  async function updateEntry(entryId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/entries/${entryId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Lançamento atualizado.", { refreshBase: true });
  }

  async function bulkUpdateEntryCategory(entryIds: string[], categoryId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<FinancialEntryBulkCategoryUpdateResponse>("/entries/bulk/category", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ entry_ids: entryIds, category_id: categoryId }),
      });
    }, "Categoria atualizada em massa.", { refreshBase: true, sections: ["lancamentos", "overview", "relatorios", "caixa"] });
  }

  async function bulkDeleteEntries(entryIds: string[]) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<FinancialEntryBulkDeleteResponse>("/entries/bulk/delete", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ entry_ids: entryIds }),
      });
    }, "Lançamentos excluídos em massa.", { refreshBase: true, sections: ["lancamentos", "overview", "relatorios", "caixa"] });
  }

  async function deleteEntry(entryId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/entries/${entryId}`, { method: "DELETE", token: session.token });
    }, "Lançamento excluído.", { refreshBase: true });
  }

  async function settleEntry(entryId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/entries/${entryId}/settle`, { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Baixa registrada.");
  }

  async function cancelEntry(entryId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/entries/${entryId}/cancel`, { method: "POST", token: session.token, body: JSON.stringify({ notes: "Cancelado pela interface." }) });
    }, "Lançamento cancelado.");
  }

  async function reverseEntry(entryId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/entries/${entryId}/reverse`, { method: "POST", token: session.token, body: JSON.stringify({ notes: "Estornado pela interface." }) });
    }, "Lançamento estornado.");
  }

  async function applyEntryFilters() {
    if (!session) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<FinancialEntryListResponse>(`/entries?${buildQuery(entryFilters)}`, { token: session.token });
      setEntryList(response);
      setFeedback({ tone: "success", message: "Consulta de lançamentos atualizada." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeEntryPage(page: number) {
    setEntryFilters((current) => ({ ...current, page: String(page) }));
    if (!session) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<FinancialEntryListResponse>(
        `/entries?${buildQuery({ ...entryFilters, page: String(page) })}`,
        { token: session.token },
      );
      setEntryList(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeEntryPageSize(pageSize: number) {
    const nextFilters = { ...entryFilters, page: "1", page_size: String(pageSize) };
    setEntryFilters(nextFilters);
    if (!session) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<FinancialEntryListResponse>(
        `/entries?${buildQuery(nextFilters)}`,
        { token: session.token },
      );
      setEntryList(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyOverviewFilters(nextFilters?: typeof overviewFilters) {
    if (!session) return;
    setSubmitting(true);
    try {
      const effectiveFilters = nextFilters ?? overviewFilters;
      const [dashboardData, reportsData] = await Promise.all([
        fetchOverviewSnapshot(session, effectiveFilters),
        fetchReportsSnapshot(session, effectiveFilters),
      ]);
      if (nextFilters) {
        setOverviewFilters(effectiveFilters);
      }
      setReportFilters(effectiveFilters);
      setDashboard(dashboardData);
      setReports(reportsData);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyCashflowFilters(nextFilters?: typeof cashflowFilters) {
    if (!session) return;
    setSubmitting(true);
    try {
      const effectiveFilters = nextFilters ?? cashflowFilters;
      const response = await fetchCashflowSnapshot(session, effectiveFilters);
      if (nextFilters) {
        setCashflowFilters(effectiveFilters);
      }
      setCashflow(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyPurchasePlanningFilters(
    overrides?: Partial<typeof purchasePlanningFilters>,
  ) {
    if (!session) return;
    setSubmitting(true);
    try {
      const nextFilters = { ...purchasePlanningFilters, ...overrides };
      const planningMode = getPurchasePlanningMode(location.pathname);
      const [planningData, returnsData] = await Promise.all([
        fetchJson<PurchasePlanningOverview>(
          `/purchase-planning/overview?${buildQuery({
            ...getPurchasePlanningRequestFilters(nextFilters, planningMode),
            mode: planningMode,
          })}`,
          { token: session.token }
        ),
        fetchJson<PurchaseReturn[]>("/purchase-returns?limit=500", {
          token: session.token,
        })
      ]);
      if (overrides) {
        setPurchasePlanningFilters(nextFilters);
      }
      setPurchasePlanning(planningData);
      setPurchaseReturns(returnsData);
      setPurchasePlanningLoadedMode(planningMode);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyReportFilters(nextFilters?: typeof reportFilters) {
    if (!session) return;
    setSubmitting(true);
    try {
      const effectiveFilters = nextFilters ?? reportFilters;
      const [reportsData, dashboardData] = await Promise.all([
        fetchReportsSnapshot(session, effectiveFilters),
        fetchOverviewSnapshot(session, effectiveFilters),
      ]);
      if (nextFilters) {
        setReportFilters(effectiveFilters);
      }
      setOverviewFilters(effectiveFilters);
      setReports(reportsData);
      setDashboard(dashboardData);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function loadReportConfig(kind: "dre" | "dro") {
    if (!session) {
      throw new Error("Sessao nao encontrada.");
    }
    return fetchJson<ReportConfig>(`/reports/config/${kind}`, { token: session.token });
  }

  async function saveReportConfig(kind: "dre" | "dro", payload: { lines: ReportConfig["lines"] }) {
    if (!session) {
      throw new Error("Sessao nao encontrada.");
    }
    setSubmitting(true);
    try {
      const response = await fetchJson<ReportConfig>(`/reports/config/${kind}`, {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadSectionData(session, "relatorios", { force: true });
      await loadSectionData(session, "overview", { force: true });
      setFeedback({ tone: "success", message: `${kind.toUpperCase()} atualizado.` });
      return response;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function applyReconciliationFilters(nextFilters?: typeof reconciliationFilters) {
    if (!session) return;
    setSubmitting(true);
    try {
      const effectiveFilters = nextFilters ?? reconciliationFilters;
      const response = await fetchJson<ReconciliationWorklist>(
        `/reconciliation/worklist?${buildQuery({
          ...effectiveFilters,
          page: "1",
          limit: String(RECONCILIATION_WORKLIST_LIMIT),
        })}`,
        { token: session.token },
      );
      setReconciliation(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function searchReconciliationEntries(params: Record<string, string | boolean>) {
    if (!session) {
      return emptyEntryList;
    }
    return fetchJson<FinancialEntryListResponse>(
      `/entries?${buildQuery({ page: "1", page_size: "50", include_legacy: false, ...params })}`,
      { token: session.token },
    );
  }

  async function createTransfer(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/transfers", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Transferência criada.");
  }

  async function createTransferFromEntries(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/transfers", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Transferência criada.", { sections: ["lancamentos", "caixa", "operacoes", "overview"] });
  }

  async function createRecurrence(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/recurrences", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Recorrência criada.");
  }

  async function generateRecurrences(untilDate: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/recurrences/generate", { method: "POST", token: session.token, body: JSON.stringify({ until_date: untilDate }) });
    }, "Recorrências geradas.");
  }

  async function createLoan(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/loans", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Empréstimo criado.");
  }

  async function uploadFile(
    path: string,
    file: File,
    fields?: Record<string, string>,
    options?: { sections?: SectionId[] },
  ) {
    if (!session) return;
    await runMutation(async () => {
      const formData = new FormData();
      formData.append("file", file);
      Object.entries(fields ?? {}).forEach(([key, value]) => formData.append(key, value));
      const result = await fetchJson<ImportResult>(path, { method: "POST", token: session.token, body: formData });
      setFeedback({ tone: "success", message: result.message });
    }, "Importação concluída.");
  }

  async function uploadManagedFile(
    path: string,
    file: File,
    sections: SectionId[],
    fields?: Record<string, string>,
  ) {
    if (!session) return;
    await runMutation(async () => {
      const formData = new FormData();
      formData.append("file", file);
      Object.entries(fields ?? {}).forEach(([key, value]) => formData.append(key, value));
      const result = await fetchJson<ImportResult>(path, { method: "POST", token: session.token, body: formData });
      setFeedback({ tone: "success", message: result.message });
    }, "Importação concluída.", { sections });
  }

  async function uploadSalesImport(file: File) {
    await uploadManagedFile("/imports/linx-sales", file, ["relatorios", "overview", "importacoes"]);
  }

  async function syncLinxSalesImport(period: { start: string; end: string }) {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-sales/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ start_date: period.start, end_date: period.end }),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Faturamento Linx sincronizado.", { sections: ["relatorios", "overview", "importacoes"] });
  }

  async function syncLinxReceivablesImport() {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-open-receivables/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Faturas a receber sincronizadas do Linx.", { sections: ["boletos", "caixa", "importacoes"] });
  }

  async function syncLinxCustomersImport() {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-customers/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Clientes e fornecedores do Linx atualizados.", { sections: ["cadastros", "importacoes"] });
  }

  async function applyLinxProductFilters(filters: { search: string; status: string }) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxProductDirectory(session, { ...filters, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxProductPage(page: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxProductDirectory(session, { page });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxProductPageSize(pageSize: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxProductDirectory(session, { page_size: pageSize, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function syncLinxProductsImport() {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-products/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Produtos do Linx atualizados.", { sections: ["cadastros", "importacoes"] });
  }

  async function applyLinxMovementFilters(filters: { search: string; group: string; movement_type: string }) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxMovementDirectory(session, { ...filters, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxMovementPage(page: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxMovementDirectory(session, { page });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxMovementPageSize(pageSize: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxMovementDirectory(session, { page_size: pageSize, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function syncLinxMovementsImport() {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-movements/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Movimentos do Linx atualizados.", { sections: ["cadastros", "relatorios", "overview", "importacoes"] });
  }

  async function applyLinxOpenReceivableFilters(filters: { search: string }) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxOpenReceivableDirectory(session, { ...filters, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxOpenReceivablePage(page: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxOpenReceivableDirectory(session, { page });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function changeLinxOpenReceivablePageSize(pageSize: number) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchLinxOpenReceivableDirectory(session, { page_size: pageSize, page: 1 });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function syncLinxOpenReceivablesImport() {
    if (!session) return;
    await runMutation(async () => {
      const result = await fetchJson<ImportResult>("/imports/linx-open-receivables/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      setFeedback({ tone: "success", message: result.message });
    }, "Faturas a receber do Linx atualizadas.", { sections: ["cadastros", "importacoes"] });
  }

  async function uploadOfxImport(file: File, accountId: string) {
    await uploadManagedFile("/imports/ofx", file, ["conciliacao", "caixa", "overview", "importacoes"], {
      account_id: accountId,
    });
  }

  async function uploadHistoricalCashbookImport(file: File) {
    await uploadManagedFile("/imports/historical-cashbook", file, ["importacoes", "lancamentos", "caixa", "overview", "relatorios"]);
  }

  async function syncInterStatementImport() {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>("/imports/inter/statement-sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
    }, "Extrato do Inter sincronizado.", { sections: ["importacoes", "conciliacao", "caixa", "overview"] });
  }

  async function uploadBoletoInterImport(file: File) {
    await uploadManagedFile("/boletos/import/inter", file, ["boletos", "importacoes"]);
  }

  async function uploadBoletoC6Import(file: File) {
    await uploadManagedFile("/boletos/import/c6", file, ["boletos", "importacoes"]);
  }

  async function uploadBoletoCustomerDataImport(file: File) {
    await uploadManagedFile("/boletos/import/customer-data", file, ["boletos", "importacoes"]);
  }

  async function syncInterChargesImport() {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>("/boletos/inter/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
    }, "Cobranças do Inter sincronizadas.", { sections: ["boletos", "importacoes"] });
  }

  async function issueInterCharges(selectionKeys: string[]) {
    if (!session) return;
    setSubmitting(true);
    try {
      await fetchJson<ImportResult>("/boletos/inter/issue", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ selection_keys: selectionKeys }),
      });
      setShowMissingBoletosExportFallback(false);
      for (const targetSection of ["boletos", "importacoes"] as const) {
        await loadSectionData(session, targetSection, { force: true });
      }
      setFeedback({ tone: "success", message: "Boletos emitidos no Inter." });
    } catch (error) {
      setShowMissingBoletosExportFallback(true);
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function refreshAnalyticsData() {
    if (!session) return;
    setSubmitting(true);
    try {
      const [dashboardData, reportsData, cashflowData] = await Promise.all([
        fetchOverviewSnapshot(session, overviewFilters, { refresh: true }),
        fetchReportsSnapshot(session, reportFilters, { refresh: true }),
        fetchCashflowSnapshot(session, cashflowFilters, { refresh: true }),
      ]);
      setDashboard(dashboardData);
      setReports(reportsData);
      setCashflow(cashflowData);
      setFeedback({ tone: "success", message: "Dados analiticos atualizados." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function downloadInterBoletoPdf(boletoId: string) {
    if (!session) return;
    setSubmitting(true);
    try {
      await downloadFile(`/boletos/inter/${boletoId}/pdf`, {
        token: session.token,
        filename: `boleto-inter-${boletoId}.pdf`,
      });
      setFeedback({ tone: "success", message: "PDF do boleto baixado." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function downloadInterBoletoPdfBatch(boletoIds: string[]) {
    if (!session) return;
    setSubmitting(true);
    try {
      await downloadFile("/boletos/inter/pdf-batch", {
        method: "POST",
        token: session.token,
        filename: "boletos-inter.zip",
        body: JSON.stringify({ boleto_ids: boletoIds }),
      });
      setFeedback({ tone: "success", message: "PDFs dos boletos baixados." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelInterBoleto(boletoId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>(`/boletos/inter/${boletoId}/cancel`, {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ motivo_cancelamento: "Cancelado pelo ERP" }),
      });
    }, "Boleto do Inter cancelado.", { sections: ["boletos", "importacoes"] });
  }

  async function receiveInterBoleto(boletoId: string, payWith: "BOLETO" | "PIX" = "BOLETO") {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>(`/boletos/inter/${boletoId}/receive`, {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ pagar_com: payWith }),
      });
    }, "Baixa do boleto do Inter concluída.", { sections: ["boletos", "importacoes"] });
  }

  async function createStandaloneBoleto(payload: {
    account_id: string | null;
    client_name: string;
    amount: string;
    due_date: string;
    notes: string | null;
  }) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>("/boletos/standalone", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
    }, "Boleto avulso emitido.", { sections: ["boletos", "importacoes"] });
  }

  async function cancelStandaloneBoleto(boletoId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>(`/boletos/standalone/${boletoId}/cancel`, {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ motivo_cancelamento: "Cancelado pelo ERP" }),
      });
    }, "Boleto avulso cancelado.", { sections: ["boletos", "importacoes"] });
  }

  async function syncStandaloneBoletos() {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<ImportResult>("/boletos/standalone/sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
    }, "Boletos avulsos sincronizados.", { sections: ["boletos", "importacoes"] });
  }

  async function downloadStandaloneBoletoPdf(boletoId: string) {
    if (!session) return;
    setSubmitting(true);
    try {
      await downloadFile(`/boletos/standalone/${boletoId}/pdf`, {
        token: session.token,
        filename: `boleto-avulso-${boletoId}.pdf`,
      });
      setFeedback({ tone: "success", message: "PDF do boleto avulso baixado." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function markStandaloneBoletoDownloaded(boletoId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson<void>(`/boletos/standalone/${boletoId}/downloaded`, {
        method: "POST",
        token: session.token,
      });
    }, "Boleto avulso marcado como baixado.", { sections: ["boletos"] });
  }

  async function importPurchaseInvoiceText(rawText: string) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const draft = await fetchJson<PurchaseInvoiceDraft>("/purchase-invoices/import-text", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ raw_text: rawText }),
      });
      setFeedback({ tone: "success", message: "Dados da nota extraidos para revisao." });
      return draft;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function importPurchaseInvoiceXml(file: File) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const draft = await fetchJson<PurchaseInvoiceDraft>("/purchase-invoices/import-xml", {
        method: "POST",
        token: session.token,
        body: formData,
      });
      setFeedback({ tone: "success", message: "XML lido para revisao." });
      return draft;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function savePurchaseInvoice(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/purchase-invoices", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
    }, "Nota de compra salva.", { refreshBase: true, sections: ["planejamento", "caixa"] });
  }

  async function syncLinxPurchaseInvoices() {
    if (!session) return;
    setSubmitting(true);
    try {
      const result = await fetchJson<ImportResult>("/purchase-invoices/linx-sync", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({}),
      });
      await loadBaseData(session);
      await loadSectionData(session, "planejamento", { force: true });
      if (loadedSections.caixa) {
        await loadSectionData(session, "caixa", { force: true });
      }
      if (loadedSections.lancamentos) {
        await loadSectionData(session, "lancamentos", { force: true });
      }
      setFeedback({ tone: "success", message: result.message });
      return result.message;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function createSupplier(payload: Record<string, unknown>) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const supplier = await fetchJson<Supplier>("/suppliers", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadBaseData(session);
      await loadSectionData(session, "planejamento", { force: true });
      if (loadedSections.lancamentos) {
        await loadSectionData(session, "lancamentos", { force: true });
      }
      setFeedback({ tone: "success", message: "Fornecedor criado." });
      return supplier;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function updateSupplier(supplierId: string, payload: Record<string, unknown>) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const supplier = await fetchJson<Supplier>(`/suppliers/${supplierId}`, {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadBaseData(session);
      await loadSectionData(session, "planejamento", { force: true });
      if (loadedSections.lancamentos) {
        await loadSectionData(session, "lancamentos", { force: true });
      }
      setFeedback({ tone: "success", message: "Fornecedor atualizado." });
      return supplier;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteSupplier(supplierId: string) {
    if (!session) {
      return;
    }
    await runMutation(async () => {
      await fetchJson(`/suppliers/${supplierId}`, {
        method: "DELETE",
        token: session.token,
      });
    }, "Fornecedor excluído.", { refreshBase: true, sections: ["planejamento", "lancamentos"] });
  }

  async function createBrand(payload: Record<string, unknown>) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const brand = await fetchJson<PurchaseBrand>("/brands", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadBaseData(session);
      await loadSectionData(session, "planejamento", { force: true });
      setFeedback({ tone: "success", message: "Marca criada." });
      return brand;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function updateBrand(brandId: string, payload: Record<string, unknown>) {
    if (!session) {
      return null as never;
    }
    setSubmitting(true);
    try {
      const brand = await fetchJson<PurchaseBrand>(`/brands/${brandId}`, {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
      await loadBaseData(session);
      await loadSectionData(session, "planejamento", { force: true });
      setFeedback({ tone: "success", message: "Marca atualizada." });
      return brand;
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
      throw error;
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteBrand(brandId: string) {
    if (!session) {
      return;
    }
    await runMutation(async () => {
      await fetchJson(`/brands/${brandId}`, {
        method: "DELETE",
        token: session.token,
      });
    }, "Marca excluída.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function createCollection(collectionPayload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/collections", { method: "POST", token: session.token, body: JSON.stringify(collectionPayload) });
    }, "Coleção criada.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function updateCollection(collectionId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/collections/${collectionId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Coleção atualizada.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function deleteCollection(collectionId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/collections/${collectionId}`, { method: "DELETE", token: session.token });
    }, "Coleção excluída.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function createPurchasePlan(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/purchase-plans", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Posicao de compra criada.", { sections: ["planejamento"] });
  }

  async function updatePurchasePlan(planId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-plans/${planId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Posicao de compra atualizada.", { sections: ["planejamento"] });
  }

  async function deletePurchasePlan(planId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-plans/${planId}`, { method: "DELETE", token: session.token });
    }, "Posicao de compra excluida.", { sections: ["planejamento", "caixa"] });
  }

  async function createPurchaseReturn(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/purchase-returns", {
        method: "POST",
        token: session.token,
        body: JSON.stringify(payload),
      });
    }, "Devolução de compra criada.", { sections: ["planejamento"] });
  }

  async function updatePurchaseReturn(purchaseReturnId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-returns/${purchaseReturnId}`, {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
    }, "Devolução de compra atualizada.", { sections: ["planejamento"] });
  }

  async function deletePurchaseReturn(purchaseReturnId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-returns/${purchaseReturnId}`, {
        method: "DELETE",
        token: session.token,
      });
    }, "Devolução de compra excluída.", { sections: ["planejamento"] });
  }

  async function linkPurchaseInstallment(installmentId: string, financialEntryId: string | null) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-installments/${installmentId}/link-entry`, {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ financial_entry_id: financialEntryId }),
      });
    }, "Vínculo da parcela atualizado.", { sections: ["planejamento", "caixa", "lancamentos"] });
  }

  async function reconcile(
    bankTransactionIds: string[],
    financialEntryIds: string[],
    adjustments?: Record<string, string | null>,
  ) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/reconciliation/matches", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({
          bank_transaction_ids: bankTransactionIds,
          financial_entry_ids: financialEntryIds,
          match_type: "manual",
          ...(adjustments ?? {}),
        }),
      });
    }, "Conciliação registrada.");
  }

  async function reconciliationAction(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/reconciliation/actions", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Ação rápida aplicada.");
  }

  async function unreconcile(bankTransactionId: string, deleteGeneratedEntries = false) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/reconciliation/unmatch", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({
          bank_transaction_id: bankTransactionId,
          delete_generated_entries: deleteGeneratedEntries,
        }),
      });
    }, "Conciliação desfeita.", { sections: ["conciliacao", "lancamentos", "caixa"] });
  }

  async function exportReport(kind: "dre" | "dro", format: "pdf" | "csv" | "xls") {
    if (!session) return;
    setSubmitting(true);
    try {
      await downloadFile(`/reports/export?${buildQuery({ ...reportFilters, kind, format })}`, {
        token: session.token,
        filename: `${kind}.${format}`,
      });
      setFeedback({ tone: "success", message: `Exportação ${kind.toUpperCase()} pronta.` });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function createUser(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/auth/users", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Usuário criado.");
  }

  async function updateCredentials(payload: UserCredentialsUpdatePayload) {
    if (!session) return;
    setSubmitting(true);
    try {
      const updatedUser = await fetchJson<AuthUser>("/auth/me/credentials", {
        method: "PATCH",
        token: session.token,
        body: JSON.stringify(payload),
      });
      setSession((current) => (current ? { ...current, user: updatedUser } : current));
      setUsers((current) => current.map((item) => (item.id === updatedUser.id ? updatedUser : item)));
      setFeedback({ tone: "success", message: "Credenciais atualizadas." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function updateLinxSettings(payload: LinxSettingsUpdatePayload) {
    if (!session) return;
    setSubmitting(true);
    try {
      const updated = await fetchJson<LinxSettings>("/company-settings/linx", {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
      setLinxSettings(updated);
      setFeedback({ tone: "success", message: "Configuracao do Linx atualizada." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function deactivateUser(userId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/auth/users/${userId}`, { method: "DELETE", token: session.token });
    }, "Usuário desativado.");
  }

  async function startMfaEnrollment() {
    if (!session) return;
    setSubmitting(true);
    try {
      const setup = await fetchJson<MfaSetup>("/auth/mfa/enroll/start", { method: "POST", token: session.token });
      setActiveMfaSetup(setup);
      setFeedback({ tone: "info", message: "Use a chave no autenticador e confirme com o codigo TOTP." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmMfaEnrollment(code: string) {
    if (!session) return;
    setSubmitting(true);
    try {
      const status = await fetchJson<MfaStatus>("/auth/mfa/enroll/confirm", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ code }),
      });
      setMfaStatus(status);
      setActiveMfaSetup(null);
      await loadSectionData(session, "seguranca", { force: true });
      setFeedback({ tone: "success", message: "MFA ativado com sucesso." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function resetUserMfa(userId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/auth/mfa/reset", {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ user_id: userId }),
      });
    }, "MFA resetado.", { sections: ["seguranca"] });
  }

  async function createBackup() {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/backup", { method: "POST", token: session.token });
    }, "Backup criado.");
  }

  async function restoreBackup(file: File) {
    if (!session) return;
    await runMutation(async () => {
      const formData = new FormData();
      formData.append("file", file);
      await fetchJson("/backup/restore", { method: "POST", token: session.token, body: formData });
    }, "Backup restaurado.");
  }

  async function saveBoletoClients(payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson("/boletos/clients", { method: "POST", token: session.token, body: JSON.stringify(payload) });
    }, "Configurações de boletos salvas.", { sections: ["boletos"] });
  }

  async function exportMissingBoletos(selectionKeys: string[]) {
    if (!session) return;
    setSubmitting(true);
    try {
      await downloadFile("/boletos/missing/export", {
        method: "POST",
        token: session.token,
        filename: "boletos-emissao.xlsx",
        body: JSON.stringify({ selection_keys: selectionKeys }),
      });
      setFeedback({ tone: "success", message: "Arquivo de emissao de boletos gerado." });
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleAllMonthlyMissingBoletos(showAll: boolean) {
    if (!session) return;
    const previousValue = showAllMonthlyMissingBoletos;
    setShowAllMonthlyMissingBoletos(showAll);
    setLoading(true);
    try {
      await fetchBoletoDashboard(session, showAll);
    } catch (error) {
      setShowAllMonthlyMissingBoletos(previousValue);
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setLoading(false);
    }
  }

  const activeChildSection = findChildNavItem(location.pathname);
  const overviewNavigation = getNavigationSection("overview");
  const entriesNavigation = getNavigationSection("lancamentos");
  const reconciliationNavigation = getNavigationSection("conciliacao");
  const billingNavigation = getNavigationSection("cobranca");
  const purchaseNavigation = getNavigationSection("compras");
  const resultsNavigation = getNavigationSection("resultados");
  const systemNavigation = getNavigationSection("sistema");
  const systemTabs = systemNavigation.children;
  const systemAccountsTab = systemTabs.find((tab) => tab.key === "contas") ?? systemTabs[0];
  const systemCategoriesTab = systemTabs.find((tab) => tab.key === "categorias") ?? systemTabs[0];
  const systemSecurityTab = systemTabs.find((tab) => tab.key === "seguranca") ?? systemTabs[0];
  const purchasePageProps = {
    embedded: true,
    brands,
    collections,
    purchaseSuppliers,
    filters: purchasePlanningFilters,
    loading: loading || submitting,
    onApplyFilters: applyPurchasePlanningFilters,
    onChangeFilters: setPurchasePlanningFilters,
    onCreateCollection: createCollection,
    onCreateBrand: createBrand,
    onDeleteBrand: deleteBrand,
    onDeleteCollection: deleteCollection,
    onDeletePlan: deletePurchasePlan,
    onDeletePurchaseReturn: deletePurchaseReturn,
    onDeleteSupplier: deleteSupplier,
    onCreatePlan: createPurchasePlan,
    onCreatePurchaseReturn: createPurchaseReturn,
    onCreateSupplier: createSupplier,
    onImportText: importPurchaseInvoiceText,
    onImportXml: importPurchaseInvoiceXml,
    onLinkInstallment: linkPurchaseInstallment,
    onSyncLinxPurchaseInvoices: syncLinxPurchaseInvoices,
    onUpdatePurchaseReturn: updatePurchaseReturn,
    onSaveInvoice: savePurchaseInvoice,
    onUpdateCollection: updateCollection,
    onUpdateBrand: updateBrand,
    onUpdatePlan: updatePurchasePlan,
    onUpdateSupplier: updateSupplier,
    overview: purchasePlanning,
    purchaseReturns,
    suppliers,
  };

  const shellBusy = routeLoading || loading || submitting;
  const shellBusyLabel = routeLoading
    ? "Abrindo modulo..."
    : submitting
      ? "Salvando e atualizando dados..."
      : loading
        ? "Atualizando dados..."
        : "";

  if (authLoading) {
    return (
      <LoginPage
        loading={true}
        challenge={pendingAuth}
        onLogin={handleLogin}
        onVerifyMfa={handleVerifyMfa}
        onConfirmMfaSetup={handleConfirmMfaSetup}
        onCancelChallenge={handleCancelPendingAuth}
      />
    );
  }

  if (!session) {
    return (
      <>
        <LoginPage
          loading={submitting}
          challenge={pendingAuth}
          onLogin={handleLogin}
          onVerifyMfa={handleVerifyMfa}
          onConfirmMfaSetup={handleConfirmMfaSetup}
          onCancelChallenge={handleCancelPendingAuth}
        />
        {toast && (
          <div className={`toast-notification ${toast.tone}`}>
            <div className="toast-notification-copy">
              <strong>{toast.tone === "error" ? "Erro" : toast.tone === "success" ? "Sucesso" : "Aviso"}</strong>
              <span>{toast.message}</span>
            </div>
            <button className="toast-close-button" onClick={() => setToast(null)} type="button">
              x
            </button>
          </div>
        )}
      </>
    );
  }

  return (
    <AppShell
      user={session.user}
      mainNavigation={mainNavigation}
      globalProductSearch={globalProductSearchInput}
      onGlobalProductSearchChange={setGlobalProductSearchInput}
      onSubmitGlobalProductSearch={() => {
        void searchProductsGlobally(globalProductSearchInput);
      }}
      onLogout={() => void handleLogout()}
      busy={shellBusy}
      busyLabel={shellBusyLabel}
    >
      <Suspense fallback={<RouteLoadingFallback onVisibilityChange={setRouteLoading} />}>
        <Routes>
          <Route element={<Navigate replace to="/overview/resumo" />} path="/" />

          {Object.entries(legacySectionPathMap).map(([legacyPath, targetPath]) => (
            <Route key={legacyPath} element={<Navigate replace to={targetPath} />} path={`/${legacyPath}`} />
          ))}

          <Route
            element={
              <OverviewSectionPage
                dashboard={dashboard}
                filters={overviewFilters}
                loading={submitting}
                onApplyFilters={applyOverviewFilters}
                onChangeFilters={setOverviewFilters}
                onRefreshData={refreshAnalyticsData}
                tabs={overviewNavigation.children}
              />
            }
            path="/overview/resumo"
          />
          <Route element={<Navigate replace to="/overview/resumo" />} path="/overview/pendencias" />
          <Route element={<Navigate replace to="/overview/resumo" />} path="/overview/indicadores" />
          <Route element={<Navigate replace to="/overview/resumo" />} path="/overview/saldos" />

          <Route
            element={
              <SectionChrome
                description={entriesNavigation.children[0].description}
                sectionLabel="Lançamentos"
                tabLabel={entriesNavigation.children[0].label}
                tabs={entriesNavigation.children}
                title={entriesNavigation.children[0].title}
              >
                <EntriesPage
                embedded
                accounts={accounts}
                suppliers={suppliers}
                categories={categories}
                entryList={entryList}
                  filters={entryFilters}
                  submitting={submitting}
                  onCancelEntry={cancelEntry}
                  onChangeFilters={setEntryFilters}
                  onChangePage={changeEntryPage}
                  onChangePageSize={changeEntryPageSize}
                  onCreateEntry={createEntry}
                  onCreateSupplier={createSupplier}
                  onCreateTransfer={createTransferFromEntries}
                  onDeleteEntry={deleteEntry}
                  onBulkDeleteEntries={bulkDeleteEntries}
                  onReverseEntry={reverseEntry}
                  onSettleEntry={settleEntry}
                  onUpdateEntry={updateEntry}
                  onBulkUpdateCategory={bulkUpdateEntryCategory}
                  onApplyFilters={applyEntryFilters}
                  />
              </SectionChrome>
            }
            path="/financeiro/lancamentos"
          />
        <Route element={<Navigate replace to="/financeiro/lancamentos" />} path="/financeiro/em-aberto" />
        <Route
          element={
            <SectionChrome
              description={reconciliationNavigation.children[0].description}
              sectionLabel="Conciliação"
              tabLabel={reconciliationNavigation.children[0].label}
              tabs={reconciliationNavigation.children}
              title={reconciliationNavigation.children[0].title}
            >
              <ReconciliationPage
                embedded
                accounts={accounts}
                categories={categories}
                importSummary={importSummary}
                submitting={submitting}
                suppliers={suppliers}
                filters={reconciliationFilters}
                loading={submitting}
                onApplyFilters={applyReconciliationFilters}
                onChangeFilters={setReconciliationFilters}
                onSyncInterStatement={syncInterStatementImport}
                onQuickAction={reconciliationAction}
                onReconcile={reconcile}
                onSearchEntries={searchReconciliationEntries}
                onCreateCategory={createCategory}
                onCreateSupplier={createSupplier}
                onUnreconcile={unreconcile}
                worklist={reconciliation}
              />
            </SectionChrome>
          }
          path="/financeiro/conciliacao"
        />
        <Route element={<Navigate replace to="/financeiro/cobranca/faturas-em-aberto" />} path="/financeiro/cobranca" />
        <Route element={<Navigate replace to="/financeiro/cobranca/faturas-em-aberto" />} path="/financeiro/cobranca/resumo" />
        {[
        { key: "faturas-em-aberto", path: "/financeiro/cobranca/faturas-em-aberto", view: "open" as const },
        { key: "boletos-em-aberto", path: "/financeiro/cobranca/boletos-em-aberto", view: "open-boletos" as const },
        { key: "atrasados", path: "/financeiro/cobranca/atrasados", view: "overdue" as const },
        { key: "pagas-sem-baixa", path: "/financeiro/cobranca/pagas-sem-baixa", view: "paid-pending" as const },
        { key: "boletos-faltando", path: "/financeiro/cobranca/boletos-faltando", view: "missing" as const },
        { key: "boletos-avulsos", path: "/financeiro/cobranca/boletos-avulsos", view: "standalone" as const },
        { key: "boletos-em-excesso", path: "/financeiro/cobranca/boletos-em-excesso", view: "excess" as const },
      ].map((billingRoute) => {
          const billingTab =
            billingNavigation.children.find((item) => item.key === billingRoute.key) ?? billingNavigation.children[0];
          return (
          <Route
            key={billingRoute.path}
            element={
              <SectionChrome
                description={billingTab.description}
                sectionLabel="Cobrança"
                tabLabel={billingTab.label}
                tabs={billingNavigation.children}
                title={billingTab.title}
              >
                <BoletosPage
                  accounts={accounts}
                  view={billingRoute.view}
                  onCancelInterBoleto={cancelInterBoleto}
                  onCancelStandaloneBoleto={cancelStandaloneBoleto}
                  dashboard={boletoDashboard}
                  onDownloadInterBoletoPdf={downloadInterBoletoPdf}
                  onDownloadInterBoletoPdfBatch={downloadInterBoletoPdfBatch}
                  onExportMissingBoletos={exportMissingBoletos}
                  onIssueInterCharges={issueInterCharges}
                  onReceiveInterBoleto={receiveInterBoleto}
                  onCreateStandaloneBoleto={createStandaloneBoleto}
                  onDownloadStandaloneBoletoPdf={downloadStandaloneBoletoPdf}
                  onMarkStandaloneBoletoDownloaded={markStandaloneBoletoDownloaded}
                  onSaveClients={saveBoletoClients}
                  onSyncStandaloneBoletos={syncStandaloneBoletos}
                  onToggleAllMonthlyMissingBoletos={toggleAllMonthlyMissingBoletos}
                  onUploadBoletoC6={uploadBoletoC6Import}
                  onUploadClientData={uploadBoletoCustomerDataImport}
                  showMissingExportFallback={showMissingBoletosExportFallback}
                  showAllMonthlyMissingBoletos={showAllMonthlyMissingBoletos}
                  submitting={submitting}
                />
              </SectionChrome>
            }
            path={billingRoute.path}
          />
        )})}
        <Route element={<Navigate replace to="/sistema/importacoes-gerais" />} path="/financeiro/importacoes" />

        <Route
          element={
            <SectionChrome
              description={purchaseNavigation.children[0].description}
              sectionLabel="Compras"
              tabLabel={purchaseNavigation.children[0].label}
              tabs={purchaseNavigation.children}
              title={purchaseNavigation.children[0].title}
            >
              <PurchasePlanningPage {...purchasePageProps} view="planejamento" />
            </SectionChrome>
          }
          path="/compras/planejamento"
        />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/resumo" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/devolucoes" />
        <Route
          element={<Navigate replace to="/compras/planejamento" />}
          path="/compras/cadastros"
        />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/notas-fiscais" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/posicoes-compra" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/parcelas-previstas" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/fornecedores" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/colecoes" />

        <Route
          element={
            <SectionChrome
              description={resultsNavigation.children[0].description}
              sectionLabel="Resultados"
              tabLabel={resultsNavigation.children[0].label}
              tabs={resultsNavigation.children}
              title={resultsNavigation.children[0].title}
            >
              <CashflowPage
                embedded
                accounts={accounts}
                cashflow={cashflow}
                filters={cashflowFilters}
                loading={submitting}
                onApplyFilters={applyCashflowFilters}
                onChangeFilters={setCashflowFilters}
                onRefreshData={refreshAnalyticsData}
              />
            </SectionChrome>
          }
          path="/caixa-resultados/fluxo-caixa"
        />
        <Route
          element={
            <SectionChrome
              description={resultsNavigation.children[1].description}
              sectionLabel="Resultados"
              tabLabel={resultsNavigation.children[1].label}
              tabs={resultsNavigation.children}
              title={resultsNavigation.children[1].title}
            >
              <ReportsPage
                embedded
                forcedTab="dre"
                filters={reportFilters}
                importSummary={importSummary}
                loading={submitting}
                onApplyFilters={applyReportFilters}
                onChangeFilters={setReportFilters}
                onLoadConfig={loadReportConfig}
                onExport={exportReport}
                onRefreshData={refreshAnalyticsData}
                onSaveConfig={saveReportConfig}
                onSyncMovements={syncLinxMovementsImport}
                reports={reports}
              />
            </SectionChrome>
          }
          path="/caixa-resultados/dre"
        />
        <Route
          element={
            <SectionChrome
              description={resultsNavigation.children[2].description}
              sectionLabel="Resultados"
              tabLabel={resultsNavigation.children[2].label}
              tabs={resultsNavigation.children}
              title={resultsNavigation.children[2].title}
            >
              <ReportsPage
                embedded
                forcedTab="dro"
                filters={reportFilters}
                importSummary={importSummary}
                loading={submitting}
                onApplyFilters={applyReportFilters}
                onChangeFilters={setReportFilters}
                onLoadConfig={loadReportConfig}
                onExport={exportReport}
                onRefreshData={refreshAnalyticsData}
                onSaveConfig={saveReportConfig}
                onSyncMovements={syncLinxMovementsImport}
                reports={reports}
              />
            </SectionChrome>
          }
          path="/caixa-resultados/dro"
        />
        <Route
          element={
            <SectionChrome
              description={resultsNavigation.children[3].description}
              sectionLabel="Resultados"
              tabLabel={resultsNavigation.children[3].label}
              tabs={resultsNavigation.children}
              title={resultsNavigation.children[3].title}
            >
              <OperationsPage
                embedded
                accounts={accounts}
                categories={categories}
                loans={loans}
                onCreateLoan={createLoan}
                onCreateRecurrence={createRecurrence}
                onGenerateRecurrences={generateRecurrences}
                recurrences={recurrences}
                submitting={submitting}
                transfers={transfers}
              />
            </SectionChrome>
          }
          path="/caixa-resultados/projecoes"
        />
        <Route
          element={
            <ResultsComparativesPage
              dashboard={dashboard}
              tabs={resultsNavigation.children}
            />
          }
          path="/caixa-resultados/comparativos"
        />

        <Route
          element={
            <SectionChrome
              description={systemAccountsTab.description}
              sectionLabel="Sistema"
              tabLabel={systemAccountsTab.label}
              tabs={systemTabs}
              title={systemAccountsTab.title}
            >
              <MasterDataPage
                embedded
                view="accounts"
                accounts={accounts}
                categories={categories}
                lookups={categoryLookups}
                onCreateAccount={createAccount}
                onCreateCategory={createCategory}
                onDeleteCategory={deleteCategory}
                onUpdateAccount={updateAccount}
                onUpdateCategory={updateCategory}
                submitting={submitting}
              />
            </SectionChrome>
          }
          path="/cadastros/contas"
        />
        <Route
          element={
            <SectionChrome
              description={systemCategoriesTab.description}
              sectionLabel="Sistema"
              tabLabel={systemCategoriesTab.label}
              tabs={systemTabs}
              title={systemCategoriesTab.title}
            >
              <MasterDataPage
                embedded
                view="categories"
                accounts={accounts}
                categories={categories}
                lookups={categoryLookups}
                onCreateAccount={createAccount}
                onCreateCategory={createCategory}
                onDeleteCategory={deleteCategory}
                onUpdateAccount={updateAccount}
                onUpdateCategory={updateCategory}
                submitting={submitting}
              />
            </SectionChrome>
          }
          path="/cadastros/categorias"
        />
        <Route
          element={
            <CadastrosClientsPage
              directory={linxCustomerDirectory}
              importSummary={importSummary}
              loading={loading || submitting}
              onSyncLinxCustomers={syncLinxCustomersImport}
              tabs={systemTabs}
            />
          }
          path="/cadastros/clientes"
        />
        <Route
          element={
            <CadastrosProductsPage
              directory={linxProductDirectory}
              filters={{ search: linxProductFilters.search, status: linxProductFilters.status }}
              importSummary={importSummary}
              loading={loading || submitting}
              onApplyFilters={applyLinxProductFilters}
              onChangePage={changeLinxProductPage}
              onChangePageSize={changeLinxProductPageSize}
              onSyncLinxProducts={syncLinxProductsImport}
              tabs={systemTabs}
            />
          }
          path="/cadastros/produtos"
        />
        <Route
          element={
            <CadastrosMovementsPage
              directory={linxMovementDirectory}
              filters={{
                search: linxMovementFilters.search,
                group: linxMovementFilters.group,
                movement_type: linxMovementFilters.movement_type,
              }}
              importSummary={importSummary}
              loading={loading || submitting}
              onApplyFilters={applyLinxMovementFilters}
              onChangePage={changeLinxMovementPage}
              onChangePageSize={changeLinxMovementPageSize}
              onSyncLinxMovements={syncLinxMovementsImport}
              tabs={systemTabs}
            />
          }
          path="/cadastros/movimentos"
        />
        <Route
          element={
            <CadastrosOpenReceivablesPage
              directory={linxOpenReceivableDirectory}
              filters={{ search: linxOpenReceivableFilters.search }}
              importSummary={importSummary}
              loading={loading || submitting}
              onApplyFilters={applyLinxOpenReceivableFilters}
              onChangePage={changeLinxOpenReceivablePage}
              onChangePageSize={changeLinxOpenReceivablePageSize}
              onSyncLinxOpenReceivables={syncLinxOpenReceivablesImport}
              tabs={systemTabs}
            />
          }
          path="/cadastros/faturas-a-receber"
        />
        <Route
          element={<CadastrosRulesPage loans={loans} recurrences={recurrences} tabs={systemTabs} />}
          path="/cadastros/regras"
        />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/cadastros/fornecedores" />
        <Route element={<Navigate replace to="/sistema/seguranca" />} path="/sistema/usuarios" />
        <Route element={<Navigate replace to="/sistema/seguranca" />} path="/sistema/backup" />
        <Route
          element={
            <SectionChrome
              description={systemSecurityTab.description}
              sectionLabel="Sistema"
              tabLabel={systemSecurityTab.label}
              tabs={systemTabs}
              title={systemSecurityTab.title}
            >
              <SecurityPage
                embedded
                view="all"
                backups={backups}
                currentUser={session.user}
                instanceInfo={instanceInfo}
                linxSettings={linxSettings}
                mfaStatus={mfaStatus}
                activeMfaSetup={activeMfaSetup}
                onCreateBackup={createBackup}
                onCreateUser={createUser}
                onDeactivateUser={deactivateUser}
                onRestoreBackup={restoreBackup}
                onStartMfaEnrollment={startMfaEnrollment}
                onConfirmMfaEnrollment={confirmMfaEnrollment}
                onResetMfa={resetUserMfa}
                onUpdateCredentials={updateCredentials}
                onUpdateLinxSettings={updateLinxSettings}
                submitting={submitting}
                users={users}
              />
            </SectionChrome>
          }
          path="/sistema/seguranca"
        />
        <Route
          element={
            <SystemImportsGeneralPage
              accounts={accounts}
              importSummary={importSummary}
              onSyncCustomers={syncLinxCustomersImport}
              onSyncInterCharges={syncInterChargesImport}
              onSyncInterStatement={syncInterStatementImport}
              onSyncReceivables={syncLinxReceivablesImport}
              onUploadBoletoInter={uploadBoletoInterImport}
              onUploadHistorical={uploadHistoricalCashbookImport}
              submitting={submitting}
              tabs={systemTabs}
            />
          }
          path="/sistema/importacoes-gerais"
        />
        <Route element={<Navigate replace to="/sistema/importacoes-gerais" />} path="/sistema/auditoria" />

        <Route element={<Navigate replace to={activeChildSection.path} />} path="*" />
      </Routes>
      </Suspense>
      {toast && (
        <div className={`toast-notification ${toast.tone}`}>
          <div className="toast-notification-copy">
            <strong>{loading ? "Sincronizando" : toast.tone === "error" ? "Erro" : toast.tone === "success" ? "Sucesso" : "Aviso"}</strong>
            <span>{toast.message}</span>
          </div>
          <button className="toast-close-button" onClick={() => setToast(null)} type="button">
            x
          </button>
        </div>
      )}
      <GlobalProductSearchModal
        loading={globalProductSearchLoading}
        onChangeSearchInput={setGlobalProductSearchInput}
        onClose={() => setGlobalProductSearchModalOpen(false)}
        onSearch={searchProductsGlobally}
        open={globalProductSearchModalOpen}
        result={globalProductSearchResult}
        searchInput={globalProductSearchInput}
      />
    </AppShell>
  );
}

export default App;



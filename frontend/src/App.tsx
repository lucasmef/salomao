import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { RouteLoadingFallback } from "./components/RouteLoadingFallback";
import { SectionChrome } from "./components/SectionChrome";
import { findChildNavItem, legacySectionPathMap, mainNavigation } from "./data/navigation";
import { downloadFile, fetchJson } from "./lib/api";
import { parseApiError } from "./lib/format";
import { useNetworkActivityCount } from "./hooks/useNetworkActivityCount";
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
  LoanContract,
  LoginResponse,
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
  page_size: 2000,
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
  revenue_comparison: [],
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
  overdue_boletos: [],
  overdue_invoices: [],
  paid_pending: [],
  missing_boletos: [],
  excess_boletos: [],
};

const BoletosPage = lazy(() => import("./pages/BoletosPage").then((module) => ({ default: module.BoletosPage })));
const CadastrosClientsPage = lazy(() =>
  import("./pages/CadastrosClientsPage").then((module) => ({ default: module.CadastrosClientsPage })),
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
const SystemAuditPage = lazy(() =>
  import("./pages/SystemAuditPage").then((module) => ({ default: module.SystemAuditPage })),
);
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
}) {
  const query = new URLSearchParams();
  query.set("start", params.start);
  query.set("end", params.end);
  if (params.account_id) {
    query.set("account_id", params.account_id);
  }
  query.set("include_purchase_planning", String(params.include_purchase_planning));
  query.set("include_crediario_receivables", String(params.include_crediario_receivables));
  return query.toString();
}

function getNavigationSection(key: string) {
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
  if (currentPath === "/financeiro/cobranca") {
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
  if (currentPath === "/cadastros/fornecedores") {
    return ["planejamento"];
  }
  if (currentPath === "/cadastros/clientes") {
    return ["boletos"];
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
    return ["importacoes", "seguranca"];
  }
  return ["overview"];
}

function App() {
  return (
    <BrowserRouter>
      <AppRuntime />
    </BrowserRouter>
  );
}

function AppRuntime() {
  const location = useLocation();
  const networkActivityCount = useNetworkActivityCount();
  const autoLoadingSectionKeysRef = useRef<Set<string>>(new Set());
  const [session, setSession] = useState<SessionState | null>(null);
  const [pendingAuth, setPendingAuth] = useState<PendingAuthState | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackState>({ tone: "info", message: "" });
  const [toast, setToast] = useState<FeedbackState | null>(null);
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
  const [payables, setPayables] = useState<FinancialEntryListResponse>(emptyEntryList);
  const [receivables, setReceivables] = useState<FinancialEntryListResponse>(emptyEntryList);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [recurrences, setRecurrences] = useState<RecurrenceRule[]>([]);
  const [loans, setLoans] = useState<LoanContract[]>([]);
  const [importSummary, setImportSummary] = useState<ImportSummary>(emptyImportSummary);
  const [boletoDashboard, setBoletoDashboard] = useState<BoletoDashboard>(emptyBoletoDashboard);
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
  const [mfaStatus, setMfaStatus] = useState<MfaStatus | null>(null);
  const [activeMfaSetup, setActiveMfaSetup] = useState<MfaSetup | null>(null);
  const [purchasePlanningLoadedMode, setPurchasePlanningLoadedMode] = useState<"summary" | "planning" | "returns" | null>(null);

  const [overviewFilters, setOverviewFilters] = useState(() => getCurrentMonthRange());
  const [entryFilters, setEntryFilters] = useState<Record<string, string | boolean>>(() => getDefaultEntryFilters());
  const [cashflowFilters, setCashflowFilters] = useState(() => getDefaultCashflowFilters());
  const [purchasePlanningFilters, setPurchasePlanningFilters] = useState({
    year: String(new Date().getFullYear()),
    brand_id: "",
    supplier_id: "",
    collection_id: "",
    status: "",
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
        if (!loadedSections[targetSection] || requiresPurchaseReload) {
          const loadKey =
            targetSection === "planejamento" ? `${targetSection}:${requiredPurchasePlanningMode}` : targetSection;
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
  }, [loadedSections, location.pathname, purchasePlanningLoadedMode, session]);

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
    setBoletoDashboard(boletoData);
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
          const dashboardData = await fetchJson<DashboardOverview>(
            `/dashboard/overview?${buildQuery(effectiveOverviewFilters)}`,
            { token: activeSession.token },
          );
          setDashboard(dashboardData);
          break;
        }
        case "lancamentos": {
          const effectiveEntryFilters = isInitialSectionLoad ? getDefaultEntryFilters() : entryFilters;
          if (isInitialSectionLoad) {
            setEntryFilters(effectiveEntryFilters);
          }
          const [entryData, payableData, receivableData] = await Promise.all([
            fetchJson<FinancialEntryListResponse>(`/entries?${buildQuery(effectiveEntryFilters)}`, { token: activeSession.token }),
            fetchJson<FinancialEntryListResponse>("/entries/payables?page=1&page_size=100", { token: activeSession.token }),
            fetchJson<FinancialEntryListResponse>("/entries/receivables?page=1&page_size=100", { token: activeSession.token }),
          ]);
          setEntryList(entryData);
          setPayables(payableData);
          setReceivables(receivableData);
          break;
        }
        case "planejamento": {
          const planningMode = getPurchasePlanningMode(location.pathname);
          if (planningMode === "returns") {
            const returnData = await fetchJson<PurchaseReturn[]>("/purchase-returns?limit=500", {
              token: activeSession.token,
            });
            setPurchaseReturns(returnData);
          } else {
            const planningQuery =
              planningMode === "summary"
                ? buildQuery({ ...purchasePlanningFilters, mode: planningMode })
                : buildQuery({ mode: planningMode });
            const planningData = await fetchJson<PurchasePlanningOverview>(`/purchase-planning/overview?${planningQuery}`, {
              token: activeSession.token,
            });
            setPurchasePlanning(planningData);
          }
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
            `/reconciliation/worklist?${buildQuery({ ...effectiveReconciliationFilters, page: "1", limit: "2000" })}`,
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
          const cashflowData = await fetchJson<CashflowOverview>(
            `/cashflow/overview?${buildCashflowQuery(effectiveCashflowFilters)}`,
            { token: activeSession.token },
          );
          setCashflow(cashflowData);
          break;
        }
        case "relatorios": {
          const effectiveReportFilters = isInitialSectionLoad ? getCurrentMonthRange() : reportFilters;
          if (isInitialSectionLoad) {
            setReportFilters(effectiveReportFilters);
          }
          const reportsData = await fetchJson<ReportsOverview>(
            `/reports/overview?${buildQuery(effectiveReportFilters)}`,
            { token: activeSession.token },
          );
          setReports(reportsData);
          break;
        }
        case "seguranca": {
          const statusData = await fetchJson<MfaStatus>("/auth/mfa/status", { token: activeSession.token });
          setMfaStatus(statusData);
          if (activeSession.user.role === "admin") {
            const [userData, backupData] = await Promise.all([
              fetchJson<AuthUser[]>("/auth/users", { token: activeSession.token }),
              fetchJson<BackupRead[]>("/backup", { token: activeSession.token }),
            ]);
            setUsers(userData);
            setBackups(backupData);
          } else {
            setUsers([]);
            setBackups([]);
          }
          break;
        }
        default:
          break;
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
      const response = await fetchJson<DashboardOverview>(`/dashboard/overview?${buildQuery(effectiveFilters)}`, { token: session.token });
      setDashboard(response);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyCashflowFilters() {
    if (!session) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<CashflowOverview>(`/cashflow/overview?${buildCashflowQuery(cashflowFilters)}`, { token: session.token });
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
      if (planningMode === "returns") {
        const response = await fetchJson<PurchaseReturn[]>("/purchase-returns?limit=500", {
          token: session.token,
        });
        setPurchaseReturns(response);
        setPurchasePlanningLoadedMode(planningMode);
        return;
      }
      const response = await fetchJson<PurchasePlanningOverview>(
        `/purchase-planning/overview?${buildQuery({ ...nextFilters, mode: planningMode })}`,
        {
          token: session.token,
        },
      );
      if (overrides) {
        setPurchasePlanningFilters(nextFilters);
      }
      setPurchasePlanning(response);
      setPurchasePlanningLoadedMode(planningMode);
    } catch (error) {
      setFeedback({ tone: "error", message: parseApiError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  async function applyReportFilters() {
    if (!session) return;
    setSubmitting(true);
    try {
      const response = await fetchJson<ReportsOverview>(`/reports/overview?${buildQuery(reportFilters)}`, { token: session.token });
      setReports(response);
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
        `/reconciliation/worklist?${buildQuery({ ...effectiveFilters, page: "1", limit: "2000" })}`,
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
    }, "Transferencia criada.", { sections: ["lancamentos", "caixa", "operacoes", "overview"] });
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
    }, "Importacao concluida.", { sections });
  }

  async function uploadSalesImport(file: File) {
    await uploadManagedFile("/imports/linx-sales", file, ["relatorios", "overview", "importacoes"]);
  }

  async function uploadReceivablesImport(file: File) {
    await uploadManagedFile("/imports/linx-receivables", file, ["boletos", "caixa", "importacoes"]);
  }

  async function uploadOfxImport(file: File, accountId: string) {
    await uploadManagedFile("/imports/ofx", file, ["conciliacao", "caixa", "overview", "importacoes"], {
      account_id: accountId,
    });
  }

  async function uploadHistoricalCashbookImport(file: File) {
    await uploadManagedFile("/imports/historical-cashbook", file, ["importacoes", "lancamentos", "caixa", "overview", "relatorios"]);
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
    }, "Colecao criada.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function updateCollection(collectionId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/collections/${collectionId}`, { method: "PUT", token: session.token, body: JSON.stringify(payload) });
    }, "Colecao atualizada.", { refreshBase: true, sections: ["planejamento"] });
  }

  async function deleteCollection(collectionId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/collections/${collectionId}`, { method: "DELETE", token: session.token });
    }, "Colecao excluida.", { refreshBase: true, sections: ["planejamento"] });
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
    }, "Devolucao de compra criada.", { sections: ["planejamento"] });
  }

  async function updatePurchaseReturn(purchaseReturnId: string, payload: Record<string, unknown>) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-returns/${purchaseReturnId}`, {
        method: "PUT",
        token: session.token,
        body: JSON.stringify(payload),
      });
    }, "Devolucao de compra atualizada.", { sections: ["planejamento"] });
  }

  async function deletePurchaseReturn(purchaseReturnId: string) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-returns/${purchaseReturnId}`, {
        method: "DELETE",
        token: session.token,
      });
    }, "Devolucao de compra excluida.", { sections: ["planejamento"] });
  }

  async function linkPurchaseInstallment(installmentId: string, financialEntryId: string | null) {
    if (!session) return;
    await runMutation(async () => {
      await fetchJson(`/purchase-installments/${installmentId}/link-entry`, {
        method: "POST",
        token: session.token,
        body: JSON.stringify({ financial_entry_id: financialEntryId }),
      });
    }, "Vinculo da parcela atualizado.", { sections: ["planejamento", "caixa", "lancamentos"] });
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
    }, "Conciliacao desfeita.", { sections: ["conciliacao", "lancamentos", "caixa"] });
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
    }, "Configuracoes de boletos salvas.", { sections: ["boletos"] });
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
  const financeNavigation = getNavigationSection("financeiro");
  const purchaseNavigation = getNavigationSection("compras");
  const resultsNavigation = getNavigationSection("caixa-resultados");
  const masterDataNavigation = getNavigationSection("cadastros");
  const systemNavigation = getNavigationSection("sistema");
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

  const hasNetworkActivity = networkActivityCount > 0;
  const shellBusy = routeLoading || loading || submitting || hasNetworkActivity;
  const shellBusyLabel = routeLoading
    ? "Abrindo modulo..."
    : submitting
      ? "Salvando e atualizando dados..."
      : loading || hasNetworkActivity
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
                description={financeNavigation.children[0].description}
                sectionLabel="Financeiro"
                tabLabel={financeNavigation.children[0].label}
                tabs={financeNavigation.children}
                title={financeNavigation.children[0].title}
              >
                <EntriesPage
                  embedded
                  accounts={accounts}
                  suppliers={suppliers}
                  categories={categories}
                  entryList={entryList}
                  payables={payables}
                  receivables={receivables}
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
              description={financeNavigation.children[1].description}
              sectionLabel="Financeiro"
              tabLabel={financeNavigation.children[1].label}
              tabs={financeNavigation.children}
              title={financeNavigation.children[1].title}
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
                onUploadOfx={uploadOfxImport}
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
        <Route
          element={
            <SectionChrome
              description={financeNavigation.children[2].description}
              sectionLabel="Financeiro"
              tabLabel={financeNavigation.children[2].label}
              tabs={financeNavigation.children}
              title={financeNavigation.children[2].title}
            >
              <BoletosPage
                dashboard={boletoDashboard}
                onExportMissingBoletos={exportMissingBoletos}
                onSaveClients={saveBoletoClients}
                onToggleAllMonthlyMissingBoletos={toggleAllMonthlyMissingBoletos}
                onUploadBoletoC6={uploadBoletoC6Import}
                onUploadClientData={uploadBoletoCustomerDataImport}
                onUploadBoletoInter={uploadBoletoInterImport}
                onUploadReceivables={uploadReceivablesImport}
                showAllMonthlyMissingBoletos={showAllMonthlyMissingBoletos}
                submitting={submitting}
              />
            </SectionChrome>
          }
          path="/financeiro/cobranca"
        />
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
              <PurchasePlanningPage {...purchasePageProps} view="resumo" />
            </SectionChrome>
          }
          path="/compras/resumo"
        />
        <Route
          element={
            <SectionChrome
              description={purchaseNavigation.children[1].description}
              sectionLabel="Compras"
              tabLabel={purchaseNavigation.children[1].label}
              tabs={purchaseNavigation.children}
              title={purchaseNavigation.children[1].title}
            >
              <PurchasePlanningPage {...purchasePageProps} view="planejamento" />
            </SectionChrome>
          }
          path="/compras/planejamento"
        />
        <Route
          element={
            <SectionChrome
              description={purchaseNavigation.children[2].description}
              sectionLabel="Compras"
              tabLabel={purchaseNavigation.children[2].label}
              tabs={purchaseNavigation.children}
              title={purchaseNavigation.children[2].title}
            >
              <PurchasePlanningPage {...purchasePageProps} view="devolucoes" />
            </SectionChrome>
          }
          path="/compras/devolucoes"
        />
        <Route
          element={<Navigate replace to="/compras/planejamento" />}
          path="/compras/cadastros"
        />
        <Route element={<Navigate replace to="/compras/resumo" />} path="/compras/notas-fiscais" />
        <Route element={<Navigate replace to="/compras/planejamento" />} path="/compras/posicoes-compra" />
        <Route element={<Navigate replace to="/compras/resumo" />} path="/compras/parcelas-previstas" />
        <Route element={<Navigate replace to="/cadastros/fornecedores" />} path="/compras/fornecedores" />
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
                onSaveConfig={saveReportConfig}
                onUploadSales={uploadSalesImport}
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
                onSaveConfig={saveReportConfig}
                onUploadSales={uploadSalesImport}
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
              description={masterDataNavigation.children[0].description}
              sectionLabel="Cadastros"
              tabLabel={masterDataNavigation.children[0].label}
              tabs={masterDataNavigation.children}
              title={masterDataNavigation.children[0].title}
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
              description={masterDataNavigation.children[1].description}
              sectionLabel="Cadastros"
              tabLabel={masterDataNavigation.children[1].label}
              tabs={masterDataNavigation.children}
              title={masterDataNavigation.children[1].title}
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
          element={<CadastrosClientsPage dashboard={boletoDashboard} tabs={masterDataNavigation.children} />}
          path="/cadastros/clientes"
        />
        <Route
          element={<CadastrosRulesPage loans={loans} recurrences={recurrences} tabs={masterDataNavigation.children} />}
          path="/cadastros/regras"
        />
        <Route
          element={
            <SectionChrome
              description={masterDataNavigation.children[4].description}
              sectionLabel="Cadastros"
              tabLabel={masterDataNavigation.children[4].label}
              tabs={masterDataNavigation.children}
              title={masterDataNavigation.children[4].title}
            >
              <PurchasePlanningPage {...purchasePageProps} view="fornecedores" />
            </SectionChrome>
          }
          path="/cadastros/fornecedores"
        />

        <Route
          element={
            <SectionChrome
              description={systemNavigation.children[0].description}
              sectionLabel="Sistema"
              tabLabel={systemNavigation.children[0].label}
              tabs={systemNavigation.children}
              title={systemNavigation.children[0].title}
            >
              <SecurityPage
                embedded
                view="users"
                backups={backups}
                currentUser={session.user}
                instanceInfo={instanceInfo}
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
                submitting={submitting}
                users={users}
              />
            </SectionChrome>
          }
          path="/sistema/usuarios"
        />
        <Route
          element={
            <SectionChrome
              description={systemNavigation.children[1].description}
              sectionLabel="Sistema"
              tabLabel={systemNavigation.children[1].label}
              tabs={systemNavigation.children}
              title={systemNavigation.children[1].title}
            >
              <SecurityPage
                embedded
                view="backup"
                backups={backups}
                currentUser={session.user}
                instanceInfo={instanceInfo}
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
                submitting={submitting}
                users={users}
              />
            </SectionChrome>
          }
          path="/sistema/backup"
        />
        <Route
          element={
            <SectionChrome
              description={systemNavigation.children[2].description}
              sectionLabel="Sistema"
              tabLabel={systemNavigation.children[2].label}
              tabs={systemNavigation.children}
              title={systemNavigation.children[2].title}
            >
              <SecurityPage
                embedded
                view="security"
                backups={backups}
                currentUser={session.user}
                instanceInfo={instanceInfo}
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
              importSummary={importSummary}
              onUploadHistorical={uploadHistoricalCashbookImport}
              submitting={submitting}
              tabs={systemNavigation.children}
            />
          }
          path="/sistema/importacoes-gerais"
        />
        <Route
          element={<SystemAuditPage backups={backups} importSummary={importSummary} tabs={systemNavigation.children} />}
          path="/sistema/auditoria"
        />

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
    </AppShell>
  );
}

export default App;

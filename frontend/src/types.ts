export type SectionId =
  | "overview"
  | "cadastros"
  | "lancamentos"
  | "planejamento"
  | "operacoes"
  | "importacoes"
  | "boletos"
  | "conciliacao"
  | "caixa"
  | "relatorios"
  | "seguranca";

export type NavIconName =
  | "overview"
  | "finance"
  | "operations"
  | "planning"
  | "imports"
  | "billing"
  | "reconciliation"
  | "cashflow"
  | "reports"
  | "security";

export type NavItem = {
  id: SectionId;
  label: string;
  description: string;
  group: string;
  icon: NavIconName;
};

export type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

export type PlanCard = { title: string; description: string; phase: string };

export type AuthUser = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  mfa_enabled: boolean;
  mfa_required: boolean;
};

export type MfaSetup = {
  secret: string;
  provisioning_uri: string;
  issuer: string;
  account_name: string;
};

export type LoginResponse = {
  status: "authenticated" | "mfa_required" | "mfa_setup_required";
  token: string | null;
  trusted_device_token?: string | null;
  expires_at: string | null;
  trusted_device_expires_at?: string | null;
  pending_token: string | null;
  user: AuthUser;
  mfa_setup: MfaSetup | null;
};

export type MfaStatus = {
  enabled: boolean;
  required: boolean;
  setup_pending: boolean;
  issuer: string;
  mode: string;
};

export type InstanceInfo = {
  app: string;
  api: string;
  app_mode: string;
  auth_mode: string;
  backup_mode: string;
  database_backend: string;
  mfa_required: boolean;
  purchase_planning_enabled: boolean;
  features: string[];
};

export type Account = {
  id: string;
  name: string;
  account_type: string;
  bank_code: string | null;
  branch_number: string | null;
  account_number: string | null;
  opening_balance: string;
  is_active?: boolean;
  import_ofx_enabled?: boolean;
  exclude_from_balance?: boolean;
  inter_api_enabled?: boolean;
  inter_environment?: string;
  inter_api_base_url?: string | null;
  inter_api_key?: string | null;
  inter_account_number?: string | null;
  has_inter_client_secret?: boolean;
  has_inter_certificate?: boolean;
  has_inter_private_key?: boolean;
};

export type Category = {
  id: string;
  code: string | null;
  name: string;
  entry_kind: string;
  report_group: string | null;
  report_subgroup: string | null;
  entry_count: number;
  is_financial_expense: boolean;
  is_active?: boolean;
};

export type CategoryGroupOption = {
  name: string;
  entry_kind: string;
};

export type CategorySubgroupOption = {
  name: string;
  entry_kind: string;
  report_group: string;
};

export type CategoryLookups = {
  group_options: CategoryGroupOption[];
  subgroup_options: CategorySubgroupOption[];
};

export type Supplier = {
  id: string;
  name: string;
  default_payment_term: string | null;
  notes: string | null;
  has_purchase_invoices: boolean;
  ignore_in_purchase_planning: boolean;
  is_active: boolean;
};

export type PurchaseBrand = {
  id: string;
  name: string;
  planning_basis: "brand" | "supplier";
  linx_brand_names: string[];
  supplier_ids: string[];
  suppliers: Supplier[];
  default_payment_term: string | null;
  notes: string | null;
  is_active: boolean;
};

export type CollectionSeason = {
  id: string;
  name: string;
  season_year: number;
  season_type: "summer" | "winter";
  season_label: string;
  start_date: string;
  end_date: string;
  notes: string | null;
  is_active: boolean;
};

export type FinancialEntry = {
  id: string;
  company_id: string;
  account_id: string | null;
  category_id: string | null;
  interest_category_id: string | null;
  transfer_id: string | null;
  loan_installment_id: string | null;
  supplier_id: string | null;
  collection_id: string | null;
  purchase_invoice_id: string | null;
  purchase_installment_id: string | null;
  entry_type: string;
  status: string;
  title: string;
  description: string | null;
  notes: string | null;
  counterparty_name: string | null;
  document_number: string | null;
  issue_date: string | null;
  competence_date: string | null;
  due_date: string | null;
  settled_at: string | null;
  principal_amount: string;
  interest_amount: string;
  discount_amount: string;
  penalty_amount: string;
  total_amount: string;
  paid_amount: string;
  expected_amount: string | null;
  external_source: string | null;
  source_system: string | null;
  source_reference: string | null;
  is_recurring_generated: boolean;
  is_deleted: boolean;
  transfer_direction: string | null;
  account_name: string | null;
  category_name: string | null;
  category_group: string | null;
  category_subgroup: string | null;
  interest_category_name: string | null;
  supplier_name: string | null;
  collection_name: string | null;
  is_legacy: boolean;
};

export type FinancialEntryListResponse = {
  items: FinancialEntry[];
  total: number;
  page: number;
  page_size: number;
  total_amount: string;
  paid_amount: string;
};

export type FinancialEntryBulkCategoryUpdateResponse = {
  updated_count: number;
  category_id: string;
  category_name: string;
  entry_ids: string[];
};

export type FinancialEntryBulkDeleteResponse = {
  deleted_count: number;
  entry_ids: string[];
};

export type Transfer = {
  id: string;
  company_id: string;
  source_account_id: string;
  destination_account_id: string;
  transfer_date: string;
  amount: string;
  status: string;
  description: string | null;
  notes: string | null;
  source_entry_id: string | null;
  destination_entry_id: string | null;
  source_account_name: string | null;
  destination_account_name: string | null;
};

export type RecurrenceRule = {
  id: string;
  company_id: string;
  name: string;
  title_template: string | null;
  entry_type: string;
  frequency: string;
  interval_value: number;
  day_of_month: number | null;
  start_date: string;
  end_date: string | null;
  next_run_date: string | null;
  amount: string;
  principal_amount: string;
  interest_amount: string;
  discount_amount: string;
  penalty_amount: string;
  account_id: string | null;
  category_id: string | null;
  interest_category_id: string | null;
  counterparty_name: string | null;
  document_number: string | null;
  description: string | null;
  notes: string | null;
  is_active: boolean;
};

export type LoanInstallment = {
  id: string;
  contract_id: string;
  installment_number: number;
  due_date: string;
  principal_amount: string;
  interest_amount: string;
  total_amount: string;
  status: string;
  financial_entry_id: string | null;
};

export type LoanContract = {
  id: string;
  company_id: string;
  account_id: string | null;
  lender_name: string;
  contract_number: string | null;
  title: string;
  start_date: string;
  first_due_date: string;
  installments_count: number;
  principal_total: string;
  interest_total: string;
  installment_amount: string;
  notes: string | null;
  is_active: boolean;
  installments: LoanInstallment[];
};

export type ImportBatch = {
  id: string;
  source_type: string;
  filename: string;
  status: string;
  records_total: number;
  records_valid: number;
  records_invalid: number;
  error_summary: string | null;
  created_at: string;
};

export type ImportSummary = {
  import_batches: ImportBatch[];
  sales_snapshot_count: number;
  receivable_title_count: number;
  bank_transaction_count: number;
  historical_cashbook_count: number;
  latest_ofx_transaction_date: string | null;
};

export type ImportResult = {
  batch: ImportBatch;
  message: string;
};

export type BoletoSummary = {
  receivable_count: number;
  receivable_total: string;
  boleto_count: number;
  overdue_boleto_count: number;
  overdue_invoice_client_count: number;
  paid_pending_count: number;
  missing_boleto_count: number;
  excess_boleto_count: number;
  boleto_clients_count: number;
};

export type BoletoClient = {
  client_key: string;
  client_name: string;
  client_code: string | null;
  uses_boleto: boolean;
  mode: string;
  boleto_due_day: number | null;
  include_interest: boolean;
  notes: string | null;
  auto_uses_boleto: boolean;
  receivable_count: number;
  overdue_boleto_count: number;
  total_amount: string;
  matched_paid_count: number;
  address_street: string | null;
  address_number: string | null;
  address_complement: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  tax_id: string | null;
  state_registration: string | null;
  phone_primary: string | null;
  phone_secondary: string | null;
  mobile: string | null;
};

export type BoletoAlertItem = {
  selection_key: string;
  client_key: string;
  type: string;
  client_name: string;
  mode: string | null;
  due_date: string | null;
  days_overdue: number;
  status: string;
  amount: string;
  reason: string;
  receivable_count: number;
  bank: string | null;
  competence: string | null;
  receivables: Array<{
    client_name: string;
    client_code: string | null;
    invoice_number: string;
    installment: string;
    issue_date: string | null;
    due_date: string | null;
    amount: string;
    corrected_amount: string;
    document: string;
    status: string;
  }>;
  boletos: Array<{
    id: string;
    bank: string;
    client_name: string;
    document_id: string;
    issue_date: string | null;
    due_date: string | null;
    amount: string;
    paid_amount: string;
    status: string;
    barcode: string | null;
    linha_digitavel: string | null;
    pix_copia_e_cola: string | null;
    inter_codigo_solicitacao: string | null;
    inter_account_id: string | null;
    pdf_available: boolean;
  }>;
};

export type BoletoOverdueInvoiceItem = {
  client_name: string;
  invoice_count: number;
  days_overdue: number;
  overdue_amount: string;
  oldest_due_date: string | null;
};

export type BoletoFileInfo = {
  source_type: string;
  name: string;
  updated_at: string;
};

export type BoletoDashboard = {
  generated_at: string;
  files: BoletoFileInfo[];
  summary: BoletoSummary;
  clients: BoletoClient[];
  receivables: Array<{
    client_name: string;
    client_code: string | null;
    invoice_number: string;
    installment: string;
    issue_date: string | null;
    due_date: string | null;
    amount: string;
    corrected_amount: string;
    document: string;
    status: string;
    status_bucket: string;
  }>;
  invoice_items: Array<{
    client_name: string;
    client_code: string | null;
    invoice_number: string;
    installment: string;
    issue_date: string | null;
    due_date: string | null;
    amount: string;
    corrected_amount: string;
    document: string;
    status: string;
    status_bucket: string;
  }>;
  open_boletos: Array<{
    id: string;
    bank: string;
    client_name: string;
    document_id: string;
    issue_date: string | null;
    due_date: string | null;
    payment_date?: string | null;
    amount: string;
    paid_amount: string;
    status: string;
    status_bucket: string;
    barcode: string | null;
    linha_digitavel: string | null;
    pix_copia_e_cola: string | null;
    inter_codigo_solicitacao: string | null;
    inter_account_id: string | null;
    pdf_available: boolean;
  }>;
  all_boletos: Array<{
    id: string;
    bank: string;
    client_name: string;
    document_id: string;
    issue_date: string | null;
    due_date: string | null;
    payment_date?: string | null;
    amount: string;
    paid_amount: string;
    status: string;
    status_bucket: string;
    barcode: string | null;
    linha_digitavel: string | null;
    pix_copia_e_cola: string | null;
    inter_codigo_solicitacao: string | null;
    inter_account_id: string | null;
    pdf_available: boolean;
  }>;
  overdue_boletos: BoletoAlertItem[];
  overdue_invoices: BoletoOverdueInvoiceItem[];
  paid_pending: BoletoAlertItem[];
  missing_boletos: BoletoAlertItem[];
  excess_boletos: BoletoAlertItem[];
  standalone_boletos: Array<{
    id: string;
    bank: string;
    client_name: string;
    document_id: string;
    issue_date: string | null;
    due_date: string | null;
    amount: string;
    paid_amount: string;
    status: string;
    status_bucket: string;
    local_status: string;
    description: string | null;
    notes: string | null;
    tax_id: string | null;
    email: string | null;
    barcode: string | null;
    linha_digitavel: string | null;
    pix_copia_e_cola: string | null;
    inter_codigo_solicitacao: string | null;
    inter_account_id: string | null;
    pdf_available: boolean;
    downloaded_at: string | null;
  }>;
};

export type AccountBalance = {
  account_id: string;
  account_name: string;
  account_type: string;
  current_balance: string;
  exclude_from_balance?: boolean;
};

export type CashflowPoint = {
  reference: string;
  opening_balance: string;
  crediario_inflows: string;
  card_inflows: string;
  launched_outflows: string;
  planned_purchase_outflows: string;
  inflows: string;
  outflows: string;
  closing_balance: string;
};

export type CashflowOverview = {
  current_balance: string;
  projected_inflows: string;
  projected_outflows: string;
  planned_purchase_outflows: string;
  projected_ending_balance: string;
  alerts: string[];
  account_balances: AccountBalance[];
  daily_projection: CashflowPoint[];
  weekly_projection: CashflowPoint[];
  monthly_projection: CashflowPoint[];
};

export type PurchaseInstallmentDraft = {
  installment_number: number;
  installment_label: string | null;
  due_date: string | null;
  amount: string;
};

export type PurchaseInvoiceDraft = {
  brand_id?: string | null;
  supplier_id?: string | null;
  supplier_name: string;
  collection_id: string | null;
  season_phase: "main" | "high";
  invoice_number: string | null;
  series: string | null;
  nfe_key: string | null;
  issue_date: string | null;
  entry_date: string | null;
  total_amount: string;
  payment_description: string | null;
  payment_term: string | null;
  notes: string | null;
  raw_text: string | null;
  raw_xml: string | null;
  installments: PurchaseInstallmentDraft[];
};

export type PurchaseInstallmentCandidate = {
  entry_id: string;
  title: string;
  due_date: string | null;
  total_amount: string;
  paid_amount: string;
  status: string;
  counterparty_name: string | null;
};

export type PurchaseInstallment = {
  id: string;
  purchase_invoice_id: string;
  installment_number: number;
  installment_label: string | null;
  due_date: string | null;
  amount: string;
  status: string;
  financial_entry_id: string | null;
  brand_name: string | null;
  supplier_name: string | null;
  collection_name: string | null;
  invoice_number: string | null;
  candidates: PurchaseInstallmentCandidate[];
};

export type PurchaseInvoice = {
  id: string;
  brand_id: string | null;
  brand_name: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  collection_id: string | null;
  collection_name: string | null;
  season_phase: "main" | "high";
  season_phase_label: string | null;
  purchase_plan_id: string | null;
  invoice_number: string | null;
  series: string | null;
  nfe_key: string | null;
  issue_date: string | null;
  entry_date: string | null;
  total_amount: string;
  payment_description: string | null;
  payment_term: string | null;
  source_type: string;
  status: string;
  notes: string | null;
  installments: PurchaseInstallment[];
};

export type PurchasePlan = {
  id: string;
  brand_id: string | null;
  supplier_id: string | null;
  supplier_ids: string[];
  collection_id: string | null;
  season_phase: "main" | "high";
  title: string;
  order_date: string | null;
  expected_delivery_date: string | null;
  purchased_amount: string;
  payment_term: string | null;
  status: string;
  notes: string | null;
  brand_name: string | null;
  supplier_name: string | null;
  supplier_names: string[];
  collection_name: string | null;
  season_year: number | null;
  season_type: "summer" | "winter" | null;
  season_label: string | null;
  season_phase_label: string | null;
  billing_deadline: string | null;
  received_amount: string;
  amount_to_receive: string;
  prior_year_same_season_amount: string;
  current_year_same_season_amount: string;
  current_year_other_seasons_amount: string;
  suggested_remaining_amount: string;
  sold_total: string;
  profit_margin: string;
};

export type PurchaseReturn = {
  id: string;
  supplier_id: string;
  supplier_name: string | null;
  return_date: string;
  amount: string;
  invoice_number: string | null;
  status: string;
  notes: string | null;
  refund_entry_id: string | null;
};

export type PurchasePlanningRow = {
  plan_id?: string | null;
  brand_id?: string | null;
  brand_name: string;
  supplier_ids: string[];
  supplier_names: string[];
  collection_id?: string | null;
  collection_name: string;
  season_year?: number | null;
  season_type?: "summer" | "winter" | null;
  season_label?: string | null;
  billing_deadline?: string | null;
  payment_term?: string | null;
  status?: string | null;
  order_date?: string | null;
  expected_delivery_date?: string | null;
  purchased_total: string;
  returns_total: string;
  received_total: string;
  delivered_total: string;
  launched_financial_total: string;
  paid_total: string;
  outstanding_goods_total: string;
  delivered_not_recorded_total: string;
  outstanding_payable_total: string;
  sold_total: string;
  profit_margin: string;
};

export type PurchasePlanningMonthlyProjection = {
  reference: string;
  planned_outflows: string;
  linked_payments: string;
  open_balance: string;
};

export type PurchasePlanningUngroupedSupplier = {
  supplier_label: string;
  collection_name: string | null;
  season_label: string | null;
  period_start: string | null;
  period_end: string | null;
  entry_count: number;
  total_amount: string;
};

export type PurchasePlanningCostRow = {
  collection_name: string;
  brand_name: string | null;
  supplier_name: string;
  purchase_cost_total: string;
  purchase_return_cost_total: string;
  net_cost_total: string;
};

export type PurchasePlanningOverview = {
  summary: {
    purchased_total: string;
    delivered_total: string;
    launched_financial_total: string;
    paid_total: string;
    outstanding_goods_total: string;
    delivered_not_recorded_total: string;
    outstanding_payable_total: string;
  sold_total: string;
  profit_margin: string;
  };
  rows: PurchasePlanningRow[];
  cost_totals: PurchasePlanningCostRow[];
  monthly_projection: PurchasePlanningMonthlyProjection[];
  invoices: PurchaseInvoice[];
  open_installments: PurchaseInstallment[];
  plans: PurchasePlan[];
  ungrouped_suppliers: PurchasePlanningUngroupedSupplier[];
};

export type ReconciliationCandidate = {
  financial_entry_id: string;
  title: string;
  counterparty_name: string | null;
  entry_type: string;
  status: string;
  due_date: string | null;
  total_amount: string;
  account_name: string | null;
  score: number;
  reasons: string[];
};

export type ReconciliationAppliedEntry = {
  financial_entry_id: string;
  title: string;
  amount_applied: string;
  status: string;
  can_delete_on_unreconcile: boolean;
};

export type ReconciliationItem = {
  bank_transaction_id: string;
  account_id: string | null;
  posted_at: string;
  amount: string;
  trn_type: string;
  fit_id: string;
  memo: string | null;
  name: string | null;
  account_name: string | null;
  reconciliation_status: string;
  undo_mode: string | null;
  applied_entries: ReconciliationAppliedEntry[];
  candidates: ReconciliationCandidate[];
};

export type ReconciliationWorklist = {
  unreconciled_count: number;
  overall_unreconciled_count: number;
  matched_count: number;
  total: number;
  page: number;
  page_size: number;
  total_account_balance: string;
  account_balances: DashboardAccountBalance[];
  items: ReconciliationItem[];
};

export type ReportLine = { label: string; amount: string };

export type ReportTreeNode = {
  key: string;
  label: string;
  code: string | null;
  amount: string;
  percent: string | null;
  tone: string;
  children: ReportTreeNode[];
};

export type DreReport = {
  period_label: string;
  gross_revenue: string;
  deductions: string;
  net_revenue: string;
  cmv: string;
  gross_profit: string;
  other_operating_income: string;
  operating_expenses: string;
  financial_expenses: string;
  non_operating_income: string;
  non_operating_expenses: string;
  taxes_on_profit: string;
  net_profit: string;
  profit_distribution: string;
  remaining_profit: string;
  dashboard_cards: ReportDashboardCard[];
  statement: ReportTreeNode[];
};

export type DroReport = {
  period_label: string;
  bank_revenue: string;
  sales_taxes: string;
  purchases_paid: string;
  contribution_margin: string;
  operating_expenses: string;
  financial_expenses: string;
  non_operating_income: string;
  non_operating_expenses: string;
  net_profit: string;
  profit_distribution: string;
  remaining_profit: string;
  dashboard_cards: ReportDashboardCard[];
  statement: ReportTreeNode[];
};

export type ReportsOverview = {
  dre: DreReport;
  dro: DroReport;
};

export type ReportOption = {
  value: string;
  label: string;
};

export type ReportGroupOption = {
  value: string;
  name: string;
  entry_kind: string;
  scope: "group" | "subgroup";
};

export type ReportFormulaItem = {
  referenced_line_id: string;
  operation: "add" | "subtract";
};

export type ReportGroupSelection = {
  group_name: string;
  operation: "add" | "subtract";
};

export type ReportConfigLine = {
  id: string;
  name: string;
  order: number;
  line_type: "source" | "totalizer";
  operation: "add" | "subtract";
  special_source: string | null;
  category_groups: ReportGroupSelection[];
  formula: ReportFormulaItem[];
  show_on_dashboard: boolean;
  show_percent: boolean;
  percent_mode: "reference_line" | "grouped_children";
  percent_reference_line_id: string | null;
  is_active: boolean;
  is_hidden: boolean;
  summary_binding: string | null;
};

export type ReportDashboardCard = {
  key: string;
  label: string;
  amount: string;
};

export type ReportConfig = {
  kind: "dre" | "dro";
  lines: ReportConfigLine[];
  available_groups: ReportGroupOption[];
  unmapped_groups: string[];
  special_source_options: ReportOption[];
};

export type BackupRead = {
  filename: string;
  created_at: string;
  size_bytes: number;
  storage_mode: string;
  encrypted: boolean;
};

export type DashboardSeriesPoint = {
  label: string;
  value: string;
};

export type DashboardRevenueComparisonPoint = {
  month: number;
  label: string;
  current_year_value: string;
  previous_year_value: string;
};

export type DashboardRevenueComparison = {
  current_year: number;
  previous_year: number;
  points: DashboardRevenueComparisonPoint[];
};

export type DashboardPendingItem = {
  id: string;
  title: string;
  due_date: string | null;
  amount: string;
  counterparty_name: string | null;
  account_name: string | null;
};

export type DashboardAccountBalance = {
  account_id: string;
  account_name: string;
  account_type: string;
  current_balance: string;
  exclude_from_balance?: boolean;
};

export type DashboardBirthdayItem = {
  linx_code: number;
  customer_name: string;
  birth_date: string;
  birthday_date: string;
  last_purchase_date: string;
};

export type DashboardWeekBirthdays = {
  week_label: string | null;
  items: DashboardBirthdayItem[];
};

export type DashboardTodaySales = {
  sales_date: string;
  gross_revenue: string;
  updated_at: string | null;
};

export type DashboardOverview = {
  period_label: string;
  kpis: {
    gross_revenue: string;
    net_revenue: string;
    cmv: string;
    purchases_paid: string;
    operating_expenses: string;
    financial_expenses: string;
    net_profit: string;
    profit_distribution: string;
    remaining_profit: string;
    current_balance: string;
    projected_balance: string;
    overdue_payables: number;
    overdue_receivables: number;
    pending_reconciliations: number;
  };
  dre_cards: DashboardSeriesPoint[];
  dre_chart: DashboardSeriesPoint[];
  revenue_comparison: DashboardRevenueComparison;
  account_balances: DashboardAccountBalance[];
  overdue_payables: DashboardPendingItem[];
  overdue_receivables: DashboardPendingItem[];
  pending_reconciliations: number;
  week_birthdays: DashboardWeekBirthdays;
  today_sales: DashboardTodaySales | null;
};

export type UserCreatePayload = {
  full_name: string;
  email: string;
  password: string;
  role: string;
};

export type UserCredentialsUpdatePayload = {
  email: string;
  password?: string;
};

export type LinxSettings = {
  base_url: string;
  username: string;
  api_base_url: string;
  api_cnpj: string | null;
  sales_view_name: string;
  receivables_view_name: string;
  payables_view_name: string;
  has_password: boolean;
  has_api_key: boolean;
  auto_sync_enabled: boolean;
  auto_sync_alert_email: string | null;
  auto_sync_last_run_at: string | null;
  auto_sync_last_status: string | null;
  auto_sync_last_error: string | null;
};

export type LinxSettingsUpdatePayload = {
  base_url: string;
  username: string;
  password?: string;
  api_base_url: string;
  api_cnpj?: string;
  api_key?: string;
  sales_view_name: string;
  receivables_view_name: string;
  payables_view_name: string;
  auto_sync_enabled: boolean;
  auto_sync_alert_email?: string;
};

export type LinxCustomerDirectorySummary = {
  total_count: number;
  client_count: number;
  supplier_count: number;
  transporter_count: number;
  active_count: number;
  boleto_enabled_count: number;
};

export type LinxCustomerDirectoryItem = {
  id: string;
  linx_code: number;
  legal_name: string;
  display_name: string | null;
  document_number: string | null;
  birth_date: string | null;
  registration_type: string | null;
  registration_type_label: string;
  person_type: string | null;
  person_type_label: string;
  is_active: boolean;
  city: string | null;
  state: string | null;
  email: string | null;
  phone_primary: string | null;
  mobile: string | null;
  uses_boleto: boolean;
  mode: string;
  boleto_due_day: number | null;
  include_interest: boolean;
  notes: string | null;
  supports_boleto_config: boolean;
  has_boleto_config: boolean;
  missing_boleto_fields: string[];
  linx_updated_at: string | null;
};

export type LinxCustomerDirectory = {
  generated_at: string;
  summary: LinxCustomerDirectorySummary;
  items: LinxCustomerDirectoryItem[];
};

export type LinxProductDirectorySummary = {
  total_count: number;
  active_count: number;
  inactive_count: number;
  with_supplier_count: number;
  with_collection_count: number;
};

export type LinxProductListItem = {
  id: string;
  linx_code: number;
  description: string;
  reference: string | null;
  barcode: string | null;
  unit: string | null;
  brand_name: string | null;
  line_name: string | null;
  sector_name: string | null;
  supplier_code: number | null;
  supplier_name: string | null;
  collection_id: number | null;
  collection_name: string | null;
  collection_name_raw: string | null;
  price_cost: string | null;
  price_sale: string | null;
  stock_quantity: string | null;
  is_active: boolean;
  linx_updated_at: string | null;
};

export type LinxProductDirectory = {
  generated_at: string;
  summary: LinxProductDirectorySummary;
  items: LinxProductListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type LinxProductSearchResult = {
  generated_at: string;
  query: string;
  total: number;
  items: LinxProductListItem[];
};

export type LinxOpenReceivableDirectorySummary = {
  total_count: number;
  overdue_count: number;
  due_today_count: number;
  total_amount: string;
};

export type LinxOpenReceivableListItem = {
  id: string;
  linx_code: number;
  customer_code: number | null;
  customer_name: string;
  issue_date: string | null;
  due_date: string | null;
  amount: string | null;
  paid_amount: string | null;
  document_number: string | null;
  document_series: string | null;
  installment_number: number | null;
  installment_count: number | null;
  identifier: string | null;
  payment_method_name: string | null;
  payment_plan_code: number | null;
  linx_row_timestamp: number | null;
};

export type LinxOpenReceivableDirectory = {
  generated_at: string;
  summary: LinxOpenReceivableDirectorySummary;
  items: LinxOpenReceivableListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type LinxMovementDirectorySummary = {
  total_count: number;
  sales_total_amount: string;
  sales_return_total_amount: string;
  purchases_total_amount: string;
  purchase_returns_total_amount: string;
};

export type LinxMovementListItem = {
  id: string;
  linx_transaction: number;
  movement_group: string;
  movement_type: string;
  document_number: string | null;
  document_series: string | null;
  identifier: string | null;
  issue_date: string | null;
  launch_date: string | null;
  customer_code: number | null;
  product_code: number | null;
  product_description: string | null;
  product_reference: string | null;
  collection_name: string | null;
  quantity: string | null;
  cost_price: string | null;
  unit_price: string | null;
  net_amount: string | null;
  total_amount: string | null;
  item_discount_amount: string | null;
  nature_code: string | null;
  nature_description: string | null;
  cfop_description: string | null;
  linx_updated_at: string | null;
  linx_row_timestamp: number | null;
};

export type LinxMovementDirectory = {
  generated_at: string;
  summary: LinxMovementDirectorySummary;
  items: LinxMovementListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type FeedbackState = {
  tone: "info" | "success" | "error";
  message: string;
};

export type BoletoExportJob = {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  total_count: number;
  processed_count: number;
  error_message: string | null;
  filename: string | null;
};

import { useEffect, useMemo, useRef, useState } from "react";
import Select, { type MultiValue, type SingleValue } from "react-select";

import { MoneyInput } from "../components/MoneyInput";
import { ModalCloseButton } from "../components/ModalCloseButton";
import {
  formatDate,
  formatEntryStatus,
  formatMoney,
  normalizeDisplayText,
} from "../lib/format";
import { formatPtBrMoneyInput, normalizePtBrMoneyInput } from "../lib/money";
import type {
  CollectionSeason,
  PurchaseBrand,
  PurchaseInvoiceDraft,
  PurchaseInstallment,
  PurchasePlan,
  PurchasePlanningOverview,
  PurchaseReturn,
  Supplier,
} from "../types";

type PurchasePlanningView =
  | "resumo"
  | "planejamento"
  | "fornecedores"
  | "devolucoes";
const zeroMoneyInput = formatPtBrMoneyInput(0);

type PurchaseFilters = {
  year: string;
  brand_id: string;
  supplier_id: string;
  collection_id: string;
  status: string;
};

type Props = {
  embedded?: boolean;
  view: PurchasePlanningView;
  brands: PurchaseBrand[];
  collections: CollectionSeason[];
  suppliers: Supplier[];
  purchaseSuppliers: Supplier[];
  filters: PurchaseFilters;
  loading?: boolean;
  overview: PurchasePlanningOverview;
  purchaseReturns: PurchaseReturn[];
  onApplyFilters: (
    overrides?: Partial<PurchaseFilters>,
  ) => Promise<void> | void;
  onChangeFilters: (value: PurchaseFilters) => void;
  onCreateSupplier: (
    payload: Record<string, unknown>,
  ) => Promise<Supplier | void>;
  onUpdateSupplier: (
    supplierId: string,
    payload: Record<string, unknown>,
  ) => Promise<Supplier | void>;
  onDeleteSupplier: (supplierId: string) => Promise<void>;
  onCreateBrand: (
    payload: Record<string, unknown>,
  ) => Promise<PurchaseBrand | void>;
  onUpdateBrand: (
    brandId: string,
    payload: Record<string, unknown>,
  ) => Promise<PurchaseBrand | void>;
  onDeleteBrand: (brandId: string) => Promise<void>;
  onCreateCollection: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateCollection: (
    collectionId: string,
    payload: Record<string, unknown>,
  ) => Promise<void>;
  onDeleteCollection: (collectionId: string) => Promise<void>;
  onCreatePlan: (payload: Record<string, unknown>) => Promise<void>;
  onUpdatePlan: (
    planId: string,
    payload: Record<string, unknown>,
  ) => Promise<void>;
  onDeletePlan: (planId: string) => Promise<void>;
  onCreatePurchaseReturn: (payload: Record<string, unknown>) => Promise<void>;
  onUpdatePurchaseReturn: (
    purchaseReturnId: string,
    payload: Record<string, unknown>,
  ) => Promise<void>;
  onDeletePurchaseReturn: (purchaseReturnId: string) => Promise<void>;
  onImportText: (rawText: string) => Promise<PurchaseInvoiceDraft>;
  onImportXml: (file: File) => Promise<PurchaseInvoiceDraft>;
  onSaveInvoice: (payload: Record<string, unknown>) => Promise<void>;
  onLinkInstallment: (
    installmentId: string,
    financialEntryId: string | null,
  ) => Promise<void>;
  onSyncLinxPurchaseInvoices: () => Promise<string | void>;
};

type SelectOption = { value: string; label: string };
type SyncFeedbackTone = "info" | "success" | "error";

type SupplierModalState = {
  id: string | null;
  name: string;
  default_payment_term: string;
  notes: string;
  is_active: boolean;
};

type BrandModalState = {
  id: string | null;
  name: string;
  supplier_ids: string[];
  default_payment_term: string;
  notes: string;
  is_active: boolean;
};

type CollectionModalState = {
  id: string | null;
  season_year: string;
  season_type: "summer" | "winter";
  start_date: string;
  end_date: string;
  notes: string;
  is_active: boolean;
};

type PurchaseReturnModalState = {
  id: string | null;
  supplier_id: string;
  return_date: string;
  amount: string;
  invoice_number: string;
  status: string;
  notes: string;
};

type CollectionObservationModalState = {
  brandKey: string;
  collectionId: string;
  notes: string;
};

type PlanningInlineEditState = {
  brand_key: string;
  collection_id: string;
  plan_id: string | null;
  value: string;
  creating: boolean;
};

type PlanningCollectionSnapshot = {
  collection: CollectionSeason;
  row: {
    purchased_total: string;
    returns_total: string;
    launched_financial_total: string;
    outstanding_payable_total: string;
    sold_total: string;
    profit_margin: string;
  } | null;
  plans: PurchasePlan[];
  plannedAmount: string;
  returnsAmount: string;
  receivedAmount: string;
  outstandingAmount: string;
  soldAmount: string;
  profitMargin: string;
  paymentTerm: string | null;
  isConfirmed: boolean;
};

type PlanningBrandSnapshot = {
  key: string;
  brandId: string | null;
  brandName: string;
  supplierIds: string[];
  supplierNames: string[];
  collections: Map<string, PlanningCollectionSnapshot>;
  isInactiveGroup?: boolean;
  groupedBrandIds?: string[];
};

const PAYMENT_TERM_OPTIONS = [
  "14 dias",
  "1x",
  "2x",
  "3x",
  "4x",
  "5x",
  "6x",
  "7x",
  "8x",
  "9x",
  "10x",
];

const purchaseSelectStyles = {
  control: (base: Record<string, unknown>, state: { isFocused: boolean }) => ({
    ...base,
    minHeight: 34,
    borderRadius: 8,
    borderColor: state.isFocused ? "#93c5fd" : "#cbd5e1",
    boxShadow: state.isFocused ? "0 0 0 3px rgba(29, 78, 216, 0.08)" : "none",
    backgroundColor: "#ffffff",
    fontSize: "0.82rem",
    ":hover": {
      borderColor: state.isFocused ? "#93c5fd" : "#94a3b8",
    },
  }),
  valueContainer: (base: Record<string, unknown>) => ({
    ...base,
    padding: "0 8px",
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
  option: (
    base: Record<string, unknown>,
    state: { isFocused: boolean; isSelected: boolean },
  ) => ({
    ...base,
    fontSize: "0.82rem",
    backgroundColor: state.isSelected
      ? "#1d4ed8"
      : state.isFocused
        ? "#eff6ff"
        : "#fff",
    color: state.isSelected ? "#fff" : "#24364f",
  }),
  indicatorsContainer: (base: Record<string, unknown>) => ({
    ...base,
    paddingRight: 4,
  }),
  multiValue: (base: Record<string, unknown>) => ({
    ...base,
    backgroundColor: "#eef2f7",
    borderRadius: 6,
  }),
  multiValueLabel: (base: Record<string, unknown>) => ({
    ...base,
    color: "#334155",
    fontSize: "0.76rem",
  }),
  multiValueRemove: (base: Record<string, unknown>) => ({
    ...base,
    color: "#475569",
    ":hover": {
      backgroundColor: "#dbe4f0",
      color: "#0f172a",
    },
  }),
  menu: (base: Record<string, unknown>) => ({
    ...base,
    borderRadius: 10,
    overflow: "hidden",
    border: "1px solid #dbe4f1",
    boxShadow: "0 10px 30px rgba(15, 23, 42, 0.12)",
  }),
  menuPortal: (base: Record<string, unknown>) => ({
    ...base,
    zIndex: 9999,
  }),
};

const PLAN_STATUS_FALLBACK = [
  { value: "planned", label: "Planejado" },
  { value: "confirmed", label: "Confirmado" },
];
const SEASON_TYPE_OPTIONS = [
  { value: "summer", label: "Verão" },
  { value: "winter", label: "Inverno" },
] as const;
const SEASON_PHASE_OPTIONS = [
  { value: "main", label: "Principal" },
  { value: "high", label: "Alto" },
] as const;
const PURCHASE_RETURN_STATUS_OPTIONS: SelectOption[] = [
  { value: "request_open", label: "Abrir solicitação" },
  { value: "factory_pending", label: "Aguardando fábrica" },
  { value: "send", label: "Enviar" },
  { value: "sent_waiting_analysis", label: "Enviado/Aguardando Análise" },
  { value: "refund_approved", label: "Reembolso aprovado" },
  { value: "refunded", label: "Reembolsado" },
];
const ALL_PURCHASE_RETURN_STATUSES = PURCHASE_RETURN_STATUS_OPTIONS.map(
  (option) => option.value,
);
const DEFAULT_VISIBLE_PURCHASE_RETURN_STATUSES =
  PURCHASE_RETURN_STATUS_OPTIONS.filter(
    (option) => option.value !== "refunded",
  ).map((option) => option.value);
const PURCHASE_RETURN_STATUS_LABELS = Object.fromEntries(
  PURCHASE_RETURN_STATUS_OPTIONS.map((option) => [option.value, option.label]),
) as Record<string, string>;

const emptySupplierModal = (): SupplierModalState => ({
  id: null,
  name: "",
  default_payment_term: "1x",
  notes: "",
  is_active: true,
});

const emptyBrandModal = (): BrandModalState => ({
  id: null,
  name: "",
  supplier_ids: [],
  default_payment_term: "1x",
  notes: "",
  is_active: true,
});

const emptyCollectionModal = (): CollectionModalState => ({
  id: null,
  season_year: String(new Date().getFullYear()),
  season_type: "summer",
  start_date: "",
  end_date: "",
  notes: "",
  is_active: true,
});

const emptyPurchaseReturnModal = (today: string): PurchaseReturnModalState => ({
  id: null,
  supplier_id: "",
  return_date: today,
  amount: zeroMoneyInput,
  invoice_number: "",
  status: "request_open",
  notes: "",
});

const emptyInvoiceDraft = (): PurchaseInvoiceDraft => ({
  supplier_id: null,
  supplier_name: "",
  collection_id: null,
  season_phase: "main",
  invoice_number: null,
  series: null,
  nfe_key: null,
  issue_date: null,
  entry_date: null,
  total_amount: zeroMoneyInput,
  payment_description: null,
  payment_term: "1x",
  notes: null,
  raw_text: null,
  raw_xml: null,
  installments: [],
});

function toInputAmount(value: string | number | null | undefined) {
  return formatPtBrMoneyInput(value);
}
function sortByLabel<T extends { label: string }>(items: T[]) {
  return [...items].sort((left, right) =>
    left.label.localeCompare(right.label, "pt-BR"),
  );
}

function toCents(value: string | number | null | undefined) {
  return Math.round(Number(normalizePtBrMoneyInput(value)) * 100);
}

function centsToAmount(value: number) {
  return (value / 100).toFixed(2);
}

function calculatePurchaseProfitMargin(
  soldAmount: string | number | null | undefined,
  receivedAmount: string | number | null | undefined,
  returnsAmount: string | number | null | undefined,
) {
  const soldCents = toCents(soldAmount);
  const netReceivedCents = toCents(receivedAmount) - toCents(returnsAmount);
  if (soldCents <= 0 || netReceivedCents <= 0) {
    return 0;
  }
  return (soldCents / netReceivedCents - 1) * 100;
}

function formatPurchaseDisplayAmount(
  value: string | number | null | undefined,
) {
  const normalized = Number(normalizePtBrMoneyInput(value));
  const integerValue = Number.isFinite(normalized) ? Math.trunc(normalized) : 0;
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(integerValue);
}

function formatPurchaseShortDate(value: string | null | undefined) {
  const formatted = formatDate(value);
  const parts = formatted.split("/");
  if (parts.length >= 2) {
    return `${parts[0]}/${parts[1]}`;
  }
  return formatted;
}

function renderResponsivePurchaseDate(value: string | null | undefined) {
  return (
    <>
      <span className="purchase-date-desktop">{formatDate(value)}</span>
      <span className="purchase-date-mobile">{formatPurchaseShortDate(value)}</span>
    </>
  );
}

function renderPurchaseStatusBadge(value: string | null | undefined, label?: string) {
  const normalized = String(value ?? "").trim().toLowerCase();
  const statusLabel = label ?? labelizeStatus(value);
  let tone: "success" | "warning" | "danger" | "neutral" = "warning";

  if (
    normalized.includes("confirm") ||
    normalized.includes("settled") ||
    normalized.includes("paid") ||
    normalized.includes("approved") ||
    normalized.includes("refunded") ||
    normalized === "active" ||
    normalized === "ativa" ||
    normalized === "ativo"
  ) {
    tone = "success";
  } else if (
    normalized.includes("cancel") ||
    normalized.includes("inactive") ||
    normalized === "inativa" ||
    normalized === "inativo"
  ) {
    tone = "neutral";
  } else if (normalized.includes("overdue") || normalized.includes("atras")) {
    tone = "danger";
  }

  return (
    <span className={`purchase-status-badge purchase-status-badge--${tone}`} title={statusLabel}>
      <span className="purchase-status-badge-icon" aria-hidden="true">
        {tone === "success" ? <CheckIcon /> : tone === "danger" || tone === "neutral" ? <CloseIcon /> : <InvoiceIcon />}
      </span>
      <span className="purchase-status-badge-label">{statusLabel}</span>
    </span>
  );
}

function buildPurchaseNetDisplayLine(
  plannedAmount: string | number | null | undefined,
  returnsAmount: string | number | null | undefined,
) {
  const returnsCents = toCents(returnsAmount);
  if (returnsCents <= 0) {
    return null;
  }
  const plannedCents = toCents(plannedAmount);
  const netAmount = centsToAmount(plannedCents - returnsCents);
  return `(-) ${formatPurchaseDisplayAmount(returnsAmount)} = ${formatPurchaseDisplayAmount(netAmount)}`;
}

function renderOutstandingReceiptHint(
  outstandingAmount: string | number | null | undefined,
) {
  const formattedAmount = formatPurchaseDisplayAmount(outstandingAmount);
  return (
    <span
      className="purchase-outstanding-receipt-hint"
      title={`Falta receber: ${formattedAmount}`}
      aria-label={`Falta receber: ${formattedAmount}`}
    >
      {formattedAmount}
    </span>
  );
}

function buildBrandKey(
  brandId: string | null | undefined,
  brandName: string | null | undefined,
) {
  if (brandId) return `brand:${brandId}`;
  return `name:${normalizeDisplayText(brandName) || "sem-marca"}`;
}

function sortCollectionsChronologically(items: CollectionSeason[]) {
  return [...items].sort((left, right) => {
    if (left.season_year !== right.season_year) {
      return left.season_year - right.season_year;
    }
    return left.start_date.localeCompare(right.start_date);
  });
}

function labelizeStatus(value: string | null | undefined) {
  if (!value) return "-";
  const normalized = value.trim().toLowerCase();
  const labels: Record<string, string> = {
    active: "Ativo",
    inactive: "Inativo",
    open: "Aberto",
    planned: "Planejado",
    confirmed: "Confirmado",
    linked: "Vinculada",
    partial: "Parcial",
    paid: "Paga",
    imported: "Importada",
  };
  return labels[normalized] ?? formatEntryStatus(value);
}

function labelizePurchaseReturnStatus(value: string | null | undefined) {
  if (!value) return "-";
  return PURCHASE_RETURN_STATUS_LABELS[value] ?? value;
}

function isPurchaseReturnActionRequired(status: string | null | undefined) {
  return status === "request_open" || status === "send";
}

function getPurchaseReturnStatusOptions(currentStatus: string | null) {
  return PURCHASE_RETURN_STATUS_OPTIONS;
}

function normalizePurchaseReturnVisibleStatuses(values: string[]) {
  return values.length ? values : DEFAULT_VISIBLE_PURCHASE_RETURN_STATUSES;
}

function parseInstallmentsCount(paymentTerm: string | null | undefined) {
  const match = paymentTerm?.match(/(\d+)/);
  return match ? match[1] : "1";
}

function stripSupplierCodePrefix(value: string | null | undefined) {
  return normalizeDisplayText(value)
    .replace(/^\s*\d+\s+(?=\S)/, "")
    .trim();
}

function normalizeSupplierLookupKey(value: string | null | undefined) {
  return stripSupplierCodePrefix(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function normalizeSearchText(value: string | null | undefined) {
  return normalizeDisplayText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function getYearFromDate(value: string | null | undefined) {
  return value ? value.slice(0, 4) : "";
}

function buildSeasonLabel(
  seasonType: "summer" | "winter" | string | null | undefined,
  seasonYear: string | number | null | undefined,
) {
  const seasonName =
    seasonType === "winter"
      ? "Inverno"
      : seasonType === "summer"
        ? "Verão"
        : "";
  return seasonName && seasonYear ? `${seasonName} ${seasonYear}` : "";
}

function asSingleValue(option: SingleValue<SelectOption>) {
  return option?.value ?? "";
}

function asMultiValue(options: MultiValue<SelectOption>) {
  return options.map((option) => option.value);
}

function renderMetricCard(title: string, value: string) {
  return (
    <article className="kpi-card" key={title}>
      <span>{title}</span>
      <strong>{value}</strong>
    </article>
  );
}

function EditIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M3 11.75V13h1.25l6.47-6.47-1.25-1.25L3 11.75ZM11.7 5.3l.93-.93a.75.75 0 0 0 0-1.06l-.94-.94a.75.75 0 0 0-1.06 0l-.93.93 1.99 2Z"
        fill="currentColor"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
        fill="currentColor"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.75.75 0 1 1 1.06 1.06L9.06 8l3.22 3.22a.75.75 0 1 1-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 0 1-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z"
        fill="currentColor"
      />
    </svg>
  );
}

function ConfirmIcon({ confirmed }: { confirmed: boolean }) {
  return confirmed ? (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
        fill="currentColor"
      />
    </svg>
  ) : (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M2 8a.75.75 0 0 1 .75-.75h10.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 8Z"
        fill="currentColor"
      />
    </svg>
  );
}

function DeleteIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M5.5 2.75h5M2.75 4.25h10.5M6.25 2.75l.22-.66A.75.75 0 0 1 7.18 1.5h1.64a.75.75 0 0 1 .71.59l.22.66M5 6.25V11m3-4.75V11m3-4.75V11M4.5 13.25h7a1 1 0 0 0 1-1l.42-8H3.08l.42 8a1 1 0 0 0 1 1Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
    </svg>
  );
}

function ObservationIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon collection-observation-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M4.25 3.25h7.5A1.75 1.75 0 0 1 13.5 5v4a1.75 1.75 0 0 1-1.75 1.75H8.4L5.6 12.9a.75.75 0 0 1-1.2-.6v-1.55H4.25A1.75 1.75 0 0 1 2.5 9V5a1.75 1.75 0 0 1 1.75-1.75Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
      <path
        d="M5.5 6.25h5M5.5 8.5h3.25"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.2"
      />
    </svg>
  );
}

function TagIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M2.5 8.5v3.5l1.5 1.5h3.5l6-6L10 4l-6 6L2.5 8.5Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
      <circle cx="5" cy="11" fill="currentColor" r="1" />
    </svg>
  );
}

function InvoiceIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M3.75 2.25h8.5a1 1 0 0 1 1 1v9.5a1 1 0 0 1-1 1h-8.5a1 1 0 0 1-1-1v-9.5a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
      <path
        d="M6 5h4M6 8h4M6 11h2.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.2"
      />
    </svg>
  );
}

function ReturnsIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <path
        d="M13.25 8a5.25 5.25 0 1 1-10.5 0M2.75 8l-1.5 1.5M2.75 8l1.5 1.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.2"
      />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg
      aria-hidden="true"
      className="button-icon"
      fill="none"
      viewBox="0 0 16 16"
    >
      <circle cx="8" cy="8" fill="currentColor" r="1.5" />
      <path
        d="M8 3c-3 0-5.5 2-6.5 4.5 1 2.5 3.5 4.5 6.5 4.5s5.5-2 6.5-4.5C13.5 5 11 3 8 3Zm0 8.5c-2.5 0-4.5-1.5-5.5-3.5 1-2 3-3.5 5.5-3.5s4.5 1.5 5.5 3.5c-1 2-3 3.5-5.5 3.5Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function PurchasePlanningPage({
  view,
  brands,
  collections,
  suppliers,
  purchaseSuppliers,
  filters,
  loading = false,
  overview,
  purchaseReturns,
  onApplyFilters,
  onChangeFilters,
  onCreateBrand,
  onUpdateBrand,
  onDeleteBrand,
  onCreateSupplier,
  onUpdateSupplier,
  onDeleteSupplier,
  onCreateCollection,
  onUpdateCollection,
  onDeleteCollection,
  onCreatePlan,
  onUpdatePlan,
  onDeletePlan,
  onCreatePurchaseReturn,
  onUpdatePurchaseReturn,
  onDeletePurchaseReturn,
  onImportText,
  onImportXml,
  onSaveInvoice,
  onLinkInstallment,
  onSyncLinxPurchaseInvoices,
}: Props) {
  const portalTarget =
    typeof document !== "undefined" ? document.body : undefined;
  const today = new Date().toISOString().slice(0, 10);
  const hasMountedAutoApplyRef = useRef(false);

  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false);
  const [invoiceText, setInvoiceText] = useState("");
  const [invoiceDraft, setInvoiceDraft] =
    useState<PurchaseInvoiceDraft>(emptyInvoiceDraft());
  const [uploadingXml, setUploadingXml] = useState(false);
  const [syncingLinxInvoices, setSyncingLinxInvoices] = useState(false);
  const [linxSyncFeedback, setLinxSyncFeedback] = useState<{
    tone: SyncFeedbackTone;
    message: string;
  } | null>(null);

  const [brandModalOpen, setBrandModalOpen] = useState(false);
  const [inactiveBrandsModalOpen, setInactiveBrandsModalOpen] = useState(false);
  const [unassignedSuppliersModalOpen, setUnassignedSuppliersModalOpen] =
    useState(false);
  const [supplierModalOpen, setSupplierModalOpen] = useState(false);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [purchaseReturnModalOpen, setPurchaseReturnModalOpen] = useState(false);
  const [purchaseReturnsPanelOpen, setPurchaseReturnsPanelOpen] =
    useState(false);
  const [brandModal, setBrandModal] =
    useState<BrandModalState>(emptyBrandModal());
  const [brandModalDetailed, setBrandModalDetailed] = useState(false);
  const [supplierModal, setSupplierModal] =
    useState<SupplierModalState>(emptySupplierModal());
  const [collectionModal, setCollectionModal] = useState<CollectionModalState>(
    emptyCollectionModal(),
  );
  const [collectionObservationModal, setCollectionObservationModal] =
    useState<CollectionObservationModalState | null>(null);
  const [purchaseReturnModal, setPurchaseReturnModal] =
    useState<PurchaseReturnModalState>(emptyPurchaseReturnModal(today));
  const [purchaseReturnFilter, setPurchaseReturnFilter] = useState("");
  const [purchaseReturnDateFrom, setPurchaseReturnDateFrom] = useState("");
  const [purchaseReturnDateTo, setPurchaseReturnDateTo] = useState("");
  const [purchaseReturnVisibleStatuses, setPurchaseReturnVisibleStatuses] =
    useState<string[]>(DEFAULT_VISIBLE_PURCHASE_RETURN_STATUSES);
  const [planningCollectionId, setPlanningCollectionId] = useState("");
  const [compareCollectionIds, setCompareCollectionIds] = useState<string[]>(
    [],
  );
  const [showPlanningReturns, setShowPlanningReturns] = useState(false);
  const [showPlanningSales, setShowPlanningSales] = useState(false);
  const [showPlanningProfit, setShowPlanningProfit] = useState(true);
  const [showPlanningDetail, setShowPlanningDetail] = useState(false);
  const [inlinePlanEdit, setInlinePlanEdit] =
    useState<PlanningInlineEditState | null>(null);
  const [unassignedSupplierTargets, setUnassignedSupplierTargets] = useState<
    Record<string, string>
  >({});
  const [selectedUnassignedSupplierIds, setSelectedUnassignedSupplierIds] =
    useState<string[]>([]);
  const [bulkUnassignedBrandId, setBulkUnassignedBrandId] = useState("");
  const hasInitializedCompareCollectionsRef = useRef(false);
  const lastAutoCompareCollectionIdRef = useRef("");

  useEffect(() => {
    if (view === "resumo" && (filters.brand_id || filters.status)) {
      void onApplyFilters({ brand_id: "", status: "" });
    }
  }, [filters.brand_id, filters.status, filters.year, onApplyFilters, view]);

  const supplierMap = useMemo(
    () => new Map(suppliers.map((supplier) => [supplier.id, supplier])),
    [suppliers],
  );
  const collectionMap = useMemo(
    () => new Map(collections.map((collection) => [collection.id, collection])),
    [collections],
  );
  const brandMap = useMemo(
    () => new Map(brands.map((brand) => [brand.id, brand])),
    [brands],
  );
  const collectionsChronological = useMemo(
    () => sortCollectionsChronologically(collections),
    [collections],
  );
  const supplierBrandMap = useMemo(() => {
    const map = new Map<string, PurchaseBrand>();
    brands.forEach((brand) => {
      brand.supplier_ids.forEach((supplierId) => {
        if (!map.has(supplierId)) {
          map.set(supplierId, brand);
        }
      });
    });
    return map;
  }, [brands]);

  const brandOptions = useMemo<SelectOption[]>(
    () =>
      sortByLabel(
        brands.map((brand) => ({ value: brand.id, label: brand.name })),
      ),
    [brands],
  );
  const activeBrandOptions = useMemo<SelectOption[]>(
    () =>
      sortByLabel(
        brands
          .filter((brand) => brand.is_active)
          .map((brand) => ({ value: brand.id, label: brand.name })),
      ),
    [brands],
  );
  const supplierOptions = useMemo<SelectOption[]>(
    () =>
      sortByLabel(
        suppliers.map((supplier) => ({
          value: supplier.id,
          label: supplier.name,
        })),
      ),
    [suppliers],
  );
  const purchaseSupplierOptions = useMemo<SelectOption[]>(
    () =>
      sortByLabel(
        purchaseSuppliers.map((supplier) => ({
          value: supplier.id,
          label: supplier.name,
        })),
      ),
    [purchaseSuppliers],
  );
  const purchaseSupplierIds = useMemo(
    () => new Set(purchaseSuppliers.map((supplier) => supplier.id)),
    [purchaseSuppliers],
  );
  const assignedActiveBrandSupplierIds = useMemo(() => {
    const ids = new Set<string>();
    brands.forEach((brand) => {
      if (!brand.is_active || brand.id === brandModal.id) {
        return;
      }
      brand.supplier_ids.forEach((supplierId) => ids.add(supplierId));
    });
    return ids;
  }, [brands, brandModal.id]);
  const brandSupplierOptions = useMemo<SelectOption[]>(() => {
    const options = new Map<string, SelectOption>();
    purchaseSuppliers.forEach((supplier) => {
      if (assignedActiveBrandSupplierIds.has(supplier.id)) {
        return;
      }
      options.set(supplier.id, { value: supplier.id, label: supplier.name });
    });
    brandModal.supplier_ids.forEach((supplierId) => {
      const supplier = supplierMap.get(supplierId);
      if (supplier) {
        options.set(supplier.id, { value: supplier.id, label: supplier.name });
      }
    });
    return sortByLabel(Array.from(options.values()));
  }, [
    assignedActiveBrandSupplierIds,
    brandModal.supplier_ids,
    purchaseSuppliers,
    supplierMap,
  ]);
  const collectionOptions = useMemo<SelectOption[]>(
    () =>
      sortByLabel(
        collections.map((collection) => ({
          value: collection.id,
          label: collection.season_label || collection.name,
        })),
      ),
    [collections],
  );
  const comparisonCollectionOptions = useMemo<SelectOption[]>(
    () =>
      [...collectionsChronological].reverse().map((collection) => ({
        value: collection.id,
        label: collection.season_label || collection.name,
      })),
    [collectionsChronological],
  );
  const planningCollectionOptions = useMemo<SelectOption[]>(
    () => comparisonCollectionOptions,
    [comparisonCollectionOptions],
  );
  const yearOptions = useMemo<SelectOption[]>(() => {
    const years = new Set<string>();
    collections.forEach((collection) => {
      if (collection.season_year) years.add(String(collection.season_year));
    });
    overview.invoices.forEach((invoice) => {
      const year = getYearFromDate(invoice.issue_date ?? invoice.entry_date);
      if (year) years.add(year);
    });
    overview.open_installments.forEach((installment) => {
      const year = getYearFromDate(installment.due_date);
      if (year) years.add(year);
    });
    overview.plans.forEach((plan) => {
      const year = getYearFromDate(
        plan.expected_delivery_date ?? plan.order_date,
      );
      if (year) years.add(year);
    });
    if (filters.year) {
      years.add(filters.year);
    }
    return sortByLabel(
      Array.from(years).map((year) => ({ value: year, label: year })),
    );
  }, [
    collections,
    filters.year,
    overview.invoices,
    overview.open_installments,
    overview.plans,
  ]);
  const paymentTermOptions = useMemo<SelectOption[]>(
    () => PAYMENT_TERM_OPTIONS.map((term) => ({ value: term, label: term })),
    [],
  );
  const planningStatusOptions = useMemo<SelectOption[]>(() => {
    const values = new Set<string>(
      PLAN_STATUS_FALLBACK.map((item) => item.value),
    );
    overview.plans.forEach((plan) => {
      if (plan.status) {
        values.add(plan.status);
      }
    });
    return Array.from(values).map((status) => ({
      value: status,
      label: labelizeStatus(status),
    }));
  }, [overview.plans]);

  const selectedYearOption =
    yearOptions.find((option) => option.value === filters.year) ?? null;
  const selectedSupplierOption =
    purchaseSupplierOptions.find(
      (option) => option.value === filters.supplier_id,
    ) ?? null;
  const selectedCollectionOption =
    collectionOptions.find(
      (option) => option.value === filters.collection_id,
    ) ?? null;
  const selectedFilterCollection = filters.collection_id
    ? (collectionMap.get(filters.collection_id) ?? null)
    : null;
  const selectedPlanningStatusOption =
    planningStatusOptions.find((option) => option.value === filters.status) ??
    null;
  const selectedBrandSupplierOptions = brandSupplierOptions.filter((option) =>
    brandModal.supplier_ids.includes(option.value),
  );
  const selectedCollectionSeasonTypeOption =
    SEASON_TYPE_OPTIONS.find(
      (option) => option.value === collectionModal.season_type,
    ) ?? SEASON_TYPE_OPTIONS[0];
  const selectedInvoiceSeasonPhaseOption =
    SEASON_PHASE_OPTIONS.find(
      (option) => option.value === invoiceDraft.season_phase,
    ) ?? SEASON_PHASE_OPTIONS[0];
  const selectedComparisonCollectionOptions =
    comparisonCollectionOptions.filter((option) =>
      compareCollectionIds.includes(option.value),
    );
  const comparisonCollectionsPlaceholder =
    selectedComparisonCollectionOptions.length === 0
      ? "Selecione as coleções"
      : selectedComparisonCollectionOptions.length === 1
        ? (selectedComparisonCollectionOptions[0]?.label ??
          "1 coleção selecionada")
        : `${selectedComparisonCollectionOptions.length} coleções selecionadas`;

  const filteredSuppliers = useMemo(() => {
    return suppliers.filter((supplier) => {
      if (filters.supplier_id && supplier.id !== filters.supplier_id)
        return false;
      return true;
    });
  }, [filters.supplier_id, suppliers]);

  const filteredCollections = useMemo(() => {
    return collections.filter((collection) => {
      if (filters.collection_id && collection.id !== filters.collection_id)
        return false;
      return true;
    });
  }, [collections, filters.collection_id]);

  const selectedInvoiceSupplierOption =
    supplierOptions.find(
      (option) => option.value === (invoiceDraft.supplier_id ?? ""),
    ) ?? null;
  const selectedInvoiceCollectionOption =
    collectionOptions.find(
      (option) => option.value === (invoiceDraft.collection_id ?? ""),
    ) ?? null;
  const selectedInvoiceTermOption =
    paymentTermOptions.find(
      (option) => option.value === (invoiceDraft.payment_term ?? ""),
    ) ?? null;

  const selectedBrandTermOption =
    paymentTermOptions.find(
      (option) => option.value === brandModal.default_payment_term,
    ) ?? null;
  const selectedSupplierTermOption =
    paymentTermOptions.find(
      (option) => option.value === supplierModal.default_payment_term,
    ) ?? null;
  const selectedPurchaseReturnSupplierOption =
    supplierOptions.find(
      (option) => option.value === purchaseReturnModal.supplier_id,
    ) ?? null;
  const purchaseReturnStatusOptions = getPurchaseReturnStatusOptions(
    purchaseReturnModal.id ? purchaseReturnModal.status : null,
  );
  const normalizedPurchaseReturnVisibleStatuses =
    normalizePurchaseReturnVisibleStatuses(purchaseReturnVisibleStatuses);
  const selectedPurchaseReturnVisibleStatusOptions =
    PURCHASE_RETURN_STATUS_OPTIONS.filter((option) =>
      normalizedPurchaseReturnVisibleStatuses.includes(option.value),
    );
  const purchaseReturnStatusPlaceholder =
    normalizedPurchaseReturnVisibleStatuses.length ===
    PURCHASE_RETURN_STATUS_OPTIONS.length
      ? "Todos os status"
      : normalizedPurchaseReturnVisibleStatuses.length === 1
        ? `${selectedPurchaseReturnVisibleStatusOptions[0]?.label ?? "1 status"}`
        : `${normalizedPurchaseReturnVisibleStatuses.length} status selecionados`;
  const filteredPurchaseReturns = useMemo(() => {
    const normalizedFilter = normalizeSearchText(purchaseReturnFilter).trim();
    return purchaseReturns.filter((purchaseReturn) => {
      if (
        !normalizedPurchaseReturnVisibleStatuses.includes(purchaseReturn.status)
      ) {
        return false;
      }
      if (
        purchaseReturnDateFrom &&
        purchaseReturn.return_date < purchaseReturnDateFrom
      ) {
        return false;
      }
      if (
        purchaseReturnDateTo &&
        purchaseReturn.return_date > purchaseReturnDateTo
      ) {
        return false;
      }
      if (!normalizedFilter) {
        return true;
      }
      const formattedDate = formatDate(purchaseReturn.return_date);
      const formattedAmount = formatPurchaseDisplayAmount(
        purchaseReturn.amount,
      );
      const haystack = normalizeSearchText(
        [
          purchaseReturn.supplier_name,
          formattedDate,
          formattedAmount,
          purchaseReturn.invoice_number,
          labelizePurchaseReturnStatus(purchaseReturn.status),
          purchaseReturn.notes,
        ]
          .filter(Boolean)
          .join(" "),
      );
      return haystack.includes(normalizedFilter);
    });
  }, [
    normalizedPurchaseReturnVisibleStatuses,
    purchaseReturnDateFrom,
    purchaseReturnDateTo,
    purchaseReturnFilter,
    purchaseReturns,
  ]);
  const purchaseCostTotal = useMemo(
    () =>
      overview.cost_totals.reduce(
        (sum, item) => sum + Number(item.purchase_cost_total),
        0,
      ),
    [overview.cost_totals],
  );
  const purchaseReturnCostTotal = useMemo(
    () =>
      overview.cost_totals.reduce(
        (sum, item) => sum + Number(item.purchase_return_cost_total),
        0,
      ),
    [overview.cost_totals],
  );
  const netPurchaseCostTotal = useMemo(
    () =>
      overview.cost_totals.reduce(
        (sum, item) => sum + Number(item.net_cost_total),
        0,
      ),
    [overview.cost_totals],
  );
  const currentCollection = useMemo(() => {
    const matchedCurrent = collectionsChronological.find(
      (collection) =>
        collection.start_date <= today && collection.end_date >= today,
    );
    return (
      matchedCurrent ??
      collectionsChronological[collectionsChronological.length - 1] ??
      null
    );
  }, [collectionsChronological, today]);
  const planningCollection = useMemo(() => {
    if (planningCollectionId) {
      return collectionMap.get(planningCollectionId) ?? null;
    }
    return currentCollection;
  }, [collectionMap, currentCollection, planningCollectionId]);
  const previousSimilarCollection = useMemo(() => {
    if (!currentCollection) return null;
    return (
      collectionsChronological.find(
        (collection) =>
          collection.season_type === currentCollection.season_type &&
          collection.season_year === currentCollection.season_year - 1,
      ) ?? null
    );
  }, [collectionsChronological, currentCollection]);

  function buildDefaultComparisonCollectionIds(
    referenceCollection: CollectionSeason | null,
  ) {
    if (!referenceCollection) {
      return [];
    }
    const referenceIndex = collectionsChronological.findIndex(
      (collection) => collection.id === referenceCollection.id,
    );
    if (referenceIndex < 0) {
      return [referenceCollection.id];
    }
    return [
      referenceIndex - 2,
      referenceIndex - 1,
      referenceIndex,
      referenceIndex + 1,
    ]
      .map((index) => collectionsChronological[index])
      .filter((collection): collection is CollectionSeason =>
        Boolean(collection),
      )
      .map((collection) => collection.id);
  }

  function isPastCollection(collection: CollectionSeason) {
    return collection.end_date < today;
  }

  function isCollectionConfirmationEditable(collection: CollectionSeason) {
    return !isPastCollection(collection);
  }

  function hasCollectionConfirmableOrder(
    collectionSnapshot: PlanningCollectionSnapshot | null | undefined,
  ) {
    return (collectionSnapshot?.plans ?? []).some(
      (plan) => toCents(plan.purchased_amount) > 0,
    );
  }

  function getCollectionObservationText(
    collectionSnapshot: PlanningCollectionSnapshot | null | undefined,
  ) {
    const uniqueNotes = Array.from(
      new Set(
        (collectionSnapshot?.plans ?? [])
          .map((plan) => normalizeDisplayText(plan.notes).trim())
          .filter((value): value is string => Boolean(value)),
      ),
    );
    return uniqueNotes.join(" | ");
  }

  function getCollectionConfirmedState(
    collection: CollectionSeason,
    collectionSnapshot: PlanningCollectionSnapshot | null | undefined,
  ) {
    if (isPastCollection(collection)) {
      return true;
    }
    return collectionSnapshot?.isConfirmed ?? false;
  }

  useEffect(() => {
    if (
      view === "resumo" ||
      hasInitializedCompareCollectionsRef.current ||
      !currentCollection
    ) {
      return;
    }
    setPlanningCollectionId(currentCollection.id);
    hasInitializedCompareCollectionsRef.current = true;
  }, [currentCollection, view]);

  useEffect(() => {
    if (view === "resumo" || !planningCollection) {
      return;
    }
    if (lastAutoCompareCollectionIdRef.current === planningCollection.id) {
      return;
    }
    const defaults = buildDefaultComparisonCollectionIds(planningCollection);
    setCompareCollectionIds(defaults);
    lastAutoCompareCollectionIdRef.current = planningCollection.id;
  }, [planningCollection, view]);

  const planningBrands = useMemo<PlanningBrandSnapshot[]>(() => {
    const brandSnapshots = new Map<string, PlanningBrandSnapshot>();
    const resolvePlanSnapshotTarget = (plan: PurchasePlan) => {
      const supplierIds = plan.supplier_ids ?? [];
      const hasAssignedSupplier = supplierIds.some((supplierId) =>
        supplierBrandMap.has(supplierId),
      );

      if (plan.brand_id) {
        const explicitBrand = brandMap.get(plan.brand_id);
        return {
          brandId: plan.brand_id,
          brandName:
            explicitBrand?.name ?? plan.brand_name ?? plan.title ?? "Sem marca",
        };
      }

      if (hasAssignedSupplier) {
        return null;
      }

      return {
        brandId: null,
        brandName: plan.brand_name ?? "Sem marca",
      };
    };
    const ensureBrandSnapshot = ({
      brandId,
      brandName,
      supplierIds,
      supplierNames,
    }: {
      brandId: string | null;
      brandName: string;
      supplierIds?: string[];
      supplierNames?: string[];
    }) => {
      const key = buildBrandKey(brandId, brandName);
      if (!brandSnapshots.has(key)) {
        brandSnapshots.set(key, {
          key,
          brandId,
          brandName,
          supplierIds: supplierIds ?? [],
          supplierNames: supplierNames ?? [],
          collections: new Map<string, PlanningCollectionSnapshot>(),
        });
      }
      const snapshot = brandSnapshots.get(key) as PlanningBrandSnapshot;
      if (!snapshot.brandId && brandId) {
        snapshot.brandId = brandId;
      }
      snapshot.brandName = snapshot.brandName || brandName;
      for (const supplierId of supplierIds ?? []) {
        if (!snapshot.supplierIds.includes(supplierId)) {
          snapshot.supplierIds.push(supplierId);
        }
      }
      for (const supplierName of supplierNames ?? []) {
        if (supplierName && !snapshot.supplierNames.includes(supplierName)) {
          snapshot.supplierNames.push(supplierName);
        }
      }
      return snapshot;
    };

    brands.forEach((brand) => {
      ensureBrandSnapshot({
        brandId: brand.id,
        brandName: brand.name,
        supplierIds: brand.supplier_ids,
        supplierNames: brand.suppliers.map((supplier) => supplier.name),
      });
    });

    const rowMap = new Map<string, (typeof overview.rows)[number]>();
    overview.rows.forEach((row) => {
      const collectionId = row.collection_id;
      if (!collectionId) return;
      const snapshot = ensureBrandSnapshot({
        brandId: row.brand_id ?? null,
        brandName: row.brand_name,
        supplierIds: row.supplier_ids,
        supplierNames: row.supplier_names,
      });
      rowMap.set(`${snapshot.key}::${collectionId}`, row);
    });

    const planGroupMap = new Map<string, PurchasePlan[]>();
    overview.plans.forEach((plan) => {
      const collectionId = plan.collection_id;
      if (!collectionId) return;
      if (plan.status === "imported") return;
      const target = resolvePlanSnapshotTarget(plan);
      if (!target) return;
      const snapshot = ensureBrandSnapshot({
        brandId: target.brandId,
        brandName: target.brandName,
        supplierIds: plan.supplier_ids ?? [],
        supplierNames: plan.supplier_names ?? [],
      });
      const key = `${snapshot.key}::${collectionId}`;
      planGroupMap.set(key, [...(planGroupMap.get(key) ?? []), plan]);
    });

    brandSnapshots.forEach((snapshot) => {
      collectionsChronological.forEach((collection) => {
        const key = `${snapshot.key}::${collection.id}`;
        const row = rowMap.get(key) ?? null;
        const plans = planGroupMap.get(key) ?? [];
        const plannedAmountCents = plans.reduce(
          (sum, plan) => sum + toCents(plan.purchased_amount),
          0,
        );
        const returnsAmountCents = toCents(row?.returns_total ?? "0.00");
        const receivedAmountCents = toCents(row?.received_total ?? "0.00");
        const plannedAmount = centsToAmount(plannedAmountCents);
        const returnsAmount = centsToAmount(returnsAmountCents);
        const receivedAmount = centsToAmount(receivedAmountCents);
        const outstandingAmount = centsToAmount(
          Math.max(plannedAmountCents - receivedAmountCents, 0),
        );
        const brandPaymentTerm = snapshot.brandId
          ? (brandMap.get(snapshot.brandId)?.default_payment_term ?? null)
          : null;
        const fallbackPlanPaymentTerm =
          plans.find((plan) => plan.payment_term)?.payment_term ?? null;
        snapshot.collections.set(collection.id, {
          collection,
          row:
            row === null
              ? null
              : {
                  purchased_total: row.purchased_total,
                  returns_total: row.returns_total,
                  launched_financial_total: row.launched_financial_total,
                  outstanding_payable_total: row.outstanding_payable_total,
                  sold_total: row.sold_total,
                  profit_margin: row.profit_margin,
                },
          plans,
          plannedAmount,
          returnsAmount,
          receivedAmount,
          outstandingAmount,
          soldAmount: row?.sold_total ?? "0.00",
          profitMargin: row?.profit_margin ?? "0.00",
          paymentTerm: brandPaymentTerm || fallbackPlanPaymentTerm,
          isConfirmed:
            plans.length > 0 &&
            plans.every((plan) => plan.status === "confirmed"),
        });
      });
    });

    return [...brandSnapshots.values()]
      .filter((snapshot) => snapshot.brandName.trim())
      .sort((left, right) =>
        left.brandName.localeCompare(right.brandName, "pt-BR"),
      );
  }, [
    brandMap,
    brands,
    collectionsChronological,
    overview.plans,
    overview.rows,
    supplierBrandMap,
  ]);

  const planningTableBrands = useMemo<PlanningBrandSnapshot[]>(() => {
    const activeSnapshots = planningBrands.filter((snapshot) => {
      if (!snapshot.brandId) {
        return true;
      }
      return brandMap.get(snapshot.brandId)?.is_active !== false;
    });
    const inactiveSnapshots = planningBrands.filter(
      (snapshot) =>
        snapshot.brandId && brandMap.get(snapshot.brandId)?.is_active === false,
    );
    if (!inactiveSnapshots.length) {
      return activeSnapshots;
    }

    const groupedSnapshot: PlanningBrandSnapshot = {
      key: "inactive-brands-group",
      brandId: null,
      brandName: "Marcas desativadas",
      supplierIds: Array.from(
        new Set(inactiveSnapshots.flatMap((snapshot) => snapshot.supplierIds)),
      ).sort(),
      supplierNames: Array.from(
        new Set(
          inactiveSnapshots.flatMap((snapshot) => snapshot.supplierNames),
        ),
      ).sort((left, right) => left.localeCompare(right, "pt-BR")),
      collections: new Map<string, PlanningCollectionSnapshot>(),
      isInactiveGroup: true,
      groupedBrandIds: inactiveSnapshots
        .map((snapshot) => snapshot.brandId)
        .filter((value): value is string => Boolean(value)),
    };

    collectionsChronological.forEach((collection) => {
      const collectionSnapshots = inactiveSnapshots
        .map((snapshot) => snapshot.collections.get(collection.id))
        .filter((value): value is PlanningCollectionSnapshot => Boolean(value));
      const plannedAmountCents = collectionSnapshots.reduce(
        (sum, snapshot) => sum + toCents(snapshot.plannedAmount),
        0,
      );
      const returnsAmountCents = collectionSnapshots.reduce(
        (sum, snapshot) => sum + toCents(snapshot.returnsAmount),
        0,
      );
      const receivedAmountCents = collectionSnapshots.reduce(
        (sum, snapshot) => sum + toCents(snapshot.receivedAmount),
        0,
      );
      const soldAmountCents = collectionSnapshots.reduce(
        (sum, snapshot) => sum + toCents(snapshot.soldAmount),
        0,
      );
      const outstandingAmountCents = Math.max(
        plannedAmountCents - receivedAmountCents,
        0,
      );
      const paymentTerms = Array.from(
        new Set(
          collectionSnapshots
            .map((snapshot) => snapshot.paymentTerm)
            .filter((value): value is string => Boolean(value)),
        ),
      );
      groupedSnapshot.collections.set(collection.id, {
        collection,
        row: {
          purchased_total: centsToAmount(
            collectionSnapshots.reduce(
              (sum, snapshot) =>
                sum + toCents(snapshot.row?.purchased_total ?? "0.00"),
              0,
            ),
          ),
          returns_total: centsToAmount(
            collectionSnapshots.reduce(
              (sum, snapshot) =>
                sum + toCents(snapshot.row?.returns_total ?? "0.00"),
              0,
            ),
          ),
          launched_financial_total: centsToAmount(
            collectionSnapshots.reduce(
              (sum, snapshot) =>
                sum + toCents(snapshot.row?.launched_financial_total ?? "0.00"),
              0,
            ),
          ),
          outstanding_payable_total: centsToAmount(
            collectionSnapshots.reduce(
              (sum, snapshot) =>
                sum +
                toCents(snapshot.row?.outstanding_payable_total ?? "0.00"),
              0,
            ),
          ),
          sold_total: centsToAmount(
            collectionSnapshots.reduce(
              (sum, snapshot) =>
                sum + toCents(snapshot.row?.sold_total ?? "0.00"),
              0,
            ),
          ),
          profit_margin: "0.00", // Will be calculated below
        },
        plans: collectionSnapshots.flatMap((snapshot) => snapshot.plans),
        plannedAmount: centsToAmount(plannedAmountCents),
        returnsAmount: centsToAmount(returnsAmountCents),
        receivedAmount: centsToAmount(receivedAmountCents),
        outstandingAmount: centsToAmount(outstandingAmountCents),
        soldAmount: centsToAmount(soldAmountCents),
        profitMargin: "0.00", // Will be calculated below
        paymentTerm:
          paymentTerms.length <= 1 ? (paymentTerms[0] ?? "-") : "Diversos",
        isConfirmed:
          collectionSnapshots.flatMap((snapshot) => snapshot.plans).length >
            0 &&
          collectionSnapshots
            .flatMap((snapshot) => snapshot.plans)
            .every((plan) => plan.status === "confirmed"),
      });

      // Reapply the same profit formula used per collection to the grouped total.
      const snap = groupedSnapshot.collections.get(collection.id);
      if (snap) {
        const aggregatedMargin = calculatePurchaseProfitMargin(
          snap.soldAmount,
          snap.receivedAmount,
          snap.returnsAmount,
        );
        snap.profitMargin = aggregatedMargin.toFixed(2);
        if (snap.row) snap.row.profit_margin = snap.profitMargin;
      }
    });

    return [...activeSnapshots, groupedSnapshot];
  }, [brandMap, collectionsChronological, planningBrands]);

  const inactiveBrands = useMemo(
    () =>
      brands
        .filter((brand) => !brand.is_active)
        .sort((left, right) => left.name.localeCompare(right.name, "pt-BR")),
    [brands],
  );
  const unassignedSuppliersSnapshot = useMemo(
    () =>
      planningBrands.find(
        (snapshot) => !snapshot.brandId && snapshot.brandName === "Sem marca",
      ) ?? null,
    [planningBrands],
  );
  const unassignedSuppliers = useMemo(
    () =>
      (unassignedSuppliersSnapshot?.supplierIds ?? [])
        .map((supplierId) => supplierMap.get(supplierId))
        .filter((supplier): supplier is Supplier => Boolean(supplier))
        .filter((supplier) => purchaseSupplierIds.has(supplier.id))
        .filter((supplier) => !supplierBrandMap.has(supplier.id))
        .sort((left, right) => left.name.localeCompare(right.name, "pt-BR")),
    [
      purchaseSupplierIds,
      supplierBrandMap,
      supplierMap,
      unassignedSuppliersSnapshot,
    ],
  );

  const selectedComparisonCollections = useMemo(() => {
    const ensuredIds =
      planningCollection?.id &&
      !compareCollectionIds.includes(planningCollection.id)
        ? [...compareCollectionIds, planningCollection.id]
        : compareCollectionIds;
    return ensuredIds
      .map((collectionId) => collectionMap.get(collectionId))
      .filter((collection): collection is CollectionSeason =>
        Boolean(collection),
      );
  }, [collectionMap, compareCollectionIds, planningCollection]);
  const collectionTotals = useMemo(() => {
    const totals = new Map<string, string>();
    collectionsChronological.forEach((collection) => {
      const totalCents = planningBrands.reduce((sum, snapshot) => {
        const collectionSnapshot = snapshot.collections.get(collection.id);
        return sum + toCents(collectionSnapshot?.plannedAmount ?? "0.00");
      }, 0);
      totals.set(collection.id, centsToAmount(totalCents));
    });
    return totals;
  }, [collectionsChronological, planningBrands]);

  function openInvoiceModal() {
    setInvoiceModalOpen(true);
    setInvoiceText("");
    setInvoiceDraft(emptyInvoiceDraft());
    setLinxSyncFeedback(null);
    setSyncingLinxInvoices(false);
  }

  function closeInvoiceModal() {
    setInvoiceModalOpen(false);
    setInvoiceText("");
    setInvoiceDraft(emptyInvoiceDraft());
    setLinxSyncFeedback(null);
    setSyncingLinxInvoices(false);
  }

  function closeBrandModal() {
    setBrandModalOpen(false);
    setCollectionObservationModal(null);
  }

  function closeCollectionObservationModal() {
    setCollectionObservationModal(null);
  }

  function openBrandModal(brand?: PurchaseBrand) {
    setCollectionObservationModal(null);
    setBrandModal(
      brand
        ? {
            id: brand.id,
            name: brand.name,
            supplier_ids: brand.supplier_ids,
            default_payment_term: brand.default_payment_term ?? "1x",
            notes: brand.notes ?? "",
            is_active: brand.is_active,
          }
        : emptyBrandModal(),
    );
    setBrandModalOpen(true);
  }

  function openCollectionObservationModal(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
  ) {
    const collectionSnapshot = snapshot.collections.get(collection.id);
    setCollectionObservationModal({
      brandKey: snapshot.key,
      collectionId: collection.id,
      notes: getCollectionObservationText(collectionSnapshot),
    });
  }

  function openInactiveBrandsModal() {
    setInactiveBrandsModalOpen(true);
  }

  function openUnassignedSuppliersModal() {
    setUnassignedSupplierTargets({});
    setSelectedUnassignedSupplierIds([]);
    setBulkUnassignedBrandId("");
    setUnassignedSuppliersModalOpen(true);
  }

  function openSupplierModal(supplier?: Supplier) {
    setSupplierModal(
      supplier
        ? {
            id: supplier.id,
            name: supplier.name,
            default_payment_term: supplier.default_payment_term ?? "1x",
            notes: supplier.notes ?? "",
            is_active: supplier.is_active,
          }
        : emptySupplierModal(),
    );
    setSupplierModalOpen(true);
  }

  function openCollectionModal(collection?: CollectionSeason) {
    setCollectionModal(
      collection
        ? {
            id: collection.id,
            season_year: String(collection.season_year),
            season_type: collection.season_type,
            start_date: collection.start_date,
            end_date: collection.end_date,
            notes: collection.notes ?? "",
            is_active: collection.is_active,
          }
        : emptyCollectionModal(),
    );
    setCollectionModalOpen(true);
  }

  function openPurchaseReturnModal(purchaseReturn?: PurchaseReturn) {
    setPurchaseReturnModal(
      purchaseReturn
        ? {
            id: purchaseReturn.id,
            supplier_id: purchaseReturn.supplier_id,
            return_date: purchaseReturn.return_date,
            amount: toInputAmount(purchaseReturn.amount),
            invoice_number: purchaseReturn.invoice_number ?? "",
            status: purchaseReturn.status,
            notes: purchaseReturn.notes ?? "",
          }
        : emptyPurchaseReturnModal(today),
    );
    setPurchaseReturnModalOpen(true);
  }

  async function handleApplySummaryFilters() {
    await onApplyFilters({
      year: filters.year,
      brand_id: "",
      supplier_id: filters.supplier_id,
      collection_id: filters.collection_id,
      status: "",
    });
  }

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    if (view === "resumo") {
      void handleApplySummaryFilters();
    }
  }, [filters.collection_id, filters.supplier_id, filters.year, view]);

  async function handleExtractInvoice() {
    if (!invoiceText.trim()) return;
    const draft = await onImportText(invoiceText);
    const canonicalSupplierName = stripSupplierCodePrefix(draft.supplier_name);
    const matchedSupplier = suppliers.find(
      (supplier) =>
        normalizeSupplierLookupKey(supplier.name) ===
        normalizeSupplierLookupKey(canonicalSupplierName),
    );
    setInvoiceDraft({
      ...emptyInvoiceDraft(),
      ...draft,
      supplier_id: matchedSupplier?.id ?? draft.supplier_id ?? null,
      supplier_name: matchedSupplier?.name ?? canonicalSupplierName,
      total_amount: formatPtBrMoneyInput(draft.total_amount),
      installments: draft.installments.map((installment) => ({
        ...installment,
        amount: normalizePtBrMoneyInput(installment.amount),
      })),
    });
  }

  async function handleXmlImport(file: File | null) {
    if (!file) return;
    setUploadingXml(true);
    try {
      const draft = await onImportXml(file);
      const canonicalSupplierName = stripSupplierCodePrefix(
        draft.supplier_name,
      );
      const matchedSupplier = suppliers.find(
        (supplier) =>
          normalizeSupplierLookupKey(supplier.name) ===
          normalizeSupplierLookupKey(canonicalSupplierName),
      );
      setInvoiceDraft({
        ...emptyInvoiceDraft(),
        ...draft,
        supplier_id: matchedSupplier?.id ?? draft.supplier_id ?? null,
        supplier_name: matchedSupplier?.name ?? canonicalSupplierName,
        total_amount: formatPtBrMoneyInput(draft.total_amount),
        installments: draft.installments.map((installment) => ({
          ...installment,
          amount: normalizePtBrMoneyInput(installment.amount),
        })),
      });
    } finally {
      setUploadingXml(false);
    }
  }

  async function handleSaveInvoice() {
    const supplierName =
      (invoiceDraft.supplier_id
        ? supplierMap.get(invoiceDraft.supplier_id)?.name
        : "") || invoiceDraft.supplier_name;
    if (!supplierName.trim()) return;

    await onSaveInvoice({
      ...invoiceDraft,
      supplier_id: invoiceDraft.supplier_id || null,
      collection_id: invoiceDraft.collection_id || null,
      season_phase: invoiceDraft.season_phase || "main",
      supplier_name: supplierName.trim(),
      total_amount: normalizePtBrMoneyInput(String(invoiceDraft.total_amount)),
      installments: invoiceDraft.installments.map((installment) => ({
        ...installment,
        amount: normalizePtBrMoneyInput(String(installment.amount)),
      })),
    });
    closeInvoiceModal();
  }

  async function handleSyncLinxPurchaseInvoices() {
    setSyncingLinxInvoices(true);
    setLinxSyncFeedback({
      tone: "info",
      message:
        "Sincronizando notas do Linx. Isso pode levar alguns segundos...",
    });
    try {
      const message = await onSyncLinxPurchaseInvoices();
      setLinxSyncFeedback({
        tone: "success",
        message:
          normalizeDisplayText(message ?? "") ||
          "Sincronizacao do Linx concluida.",
      });
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? normalizeDisplayText(error.message)
          : "Nao foi possivel concluir a sincronizacao do Linx.";
      setLinxSyncFeedback({
        tone: "error",
        message,
      });
    } finally {
      setSyncingLinxInvoices(false);
    }
  }

  async function handleSaveBrand() {
    if (!brandModal.name.trim()) return;
    const payload = {
      name: brandModal.name.trim(),
      supplier_ids: Array.from(
        new Set(brandModal.supplier_ids.filter(Boolean)),
      ),
      default_payment_term: brandModal.default_payment_term.trim() || null,
      notes: brandModal.notes.trim() || null,
      is_active: brandModal.is_active,
    };
    if (brandModal.id) {
      await onUpdateBrand(brandModal.id, payload);
    } else {
      await onCreateBrand(payload);
    }
    closeBrandModal();
    setBrandModal(emptyBrandModal());
  }

  async function handleSaveSupplier() {
    if (!supplierModal.name.trim()) return;
    const payload = {
      name: supplierModal.name.trim(),
      default_payment_term: supplierModal.default_payment_term.trim() || null,
      notes: supplierModal.notes.trim() || null,
      is_active: supplierModal.is_active,
    };
    if (supplierModal.id) {
      await onUpdateSupplier(supplierModal.id, payload);
    } else {
      await onCreateSupplier(payload);
    }
    setSupplierModalOpen(false);
    setSupplierModal(emptySupplierModal());
  }

  async function handleSaveCollection() {
    if (
      !collectionModal.season_year.trim() ||
      !collectionModal.start_date ||
      !collectionModal.end_date
    )
      return;
    const payload = {
      season_year: Number(collectionModal.season_year),
      season_type: collectionModal.season_type,
      start_date: collectionModal.start_date,
      end_date: collectionModal.end_date,
      notes: collectionModal.notes.trim() || null,
      is_active: collectionModal.is_active,
    };
    if (collectionModal.id) {
      await onUpdateCollection(collectionModal.id, payload);
    } else {
      await onCreateCollection(payload);
    }
    setCollectionModalOpen(false);
    setCollectionModal(emptyCollectionModal());
  }

  async function handleSavePurchaseReturn() {
    if (!purchaseReturnModal.supplier_id || !purchaseReturnModal.return_date)
      return;
    const payload = {
      supplier_id: purchaseReturnModal.supplier_id,
      return_date: purchaseReturnModal.return_date,
      amount: normalizePtBrMoneyInput(purchaseReturnModal.amount),
      invoice_number: purchaseReturnModal.invoice_number.trim() || null,
      status: purchaseReturnModal.status,
      notes: purchaseReturnModal.notes.trim() || null,
    };
    if (purchaseReturnModal.id) {
      await onUpdatePurchaseReturn(purchaseReturnModal.id, payload);
    } else {
      await onCreatePurchaseReturn(payload);
    }
    setPurchaseReturnModalOpen(false);
    setPurchaseReturnModal(emptyPurchaseReturnModal(today));
  }

  async function handleDeleteSupplier(supplierId: string) {
    if (!window.confirm("Excluir este fornecedor?")) return;
    await onDeleteSupplier(supplierId);
  }

  async function handleDeleteBrand(brandId: string) {
    if (!window.confirm("Excluir esta marca?")) return;
    await onDeleteBrand(brandId);
  }

  async function handleDeleteCollection(collectionId: string) {
    if (!window.confirm("Excluir esta coleção?")) return;
    await onDeleteCollection(collectionId);
  }

  async function handleDeletePurchaseReturn(purchaseReturnId: string) {
    if (!window.confirm("Excluir esta devolução de compra?")) return;
    await onDeletePurchaseReturn(purchaseReturnId);
  }

  async function handleInstallmentLink(installmentId: string, value: string) {
    await onLinkInstallment(installmentId, value || null);
  }

  async function handleAssignUnassignedSupplierToBrand(supplierId: string) {
    const targetBrandId = unassignedSupplierTargets[supplierId];
    if (!targetBrandId) return;
    const targetBrand = brands.find((brand) => brand.id === targetBrandId);
    if (!targetBrand) return;
    const nextSupplierIds = Array.from(
      new Set([...targetBrand.supplier_ids, supplierId]),
    );
    await onUpdateBrand(targetBrand.id, {
      name: targetBrand.name,
      supplier_ids: nextSupplierIds,
      default_payment_term: targetBrand.default_payment_term,
      notes: targetBrand.notes,
      is_active: targetBrand.is_active,
    });
    setUnassignedSupplierTargets((current) => {
      const next = { ...current };
      delete next[supplierId];
      return next;
    });
  }

  async function handleBulkAssignUnassignedSuppliers() {
    if (!bulkUnassignedBrandId || !selectedUnassignedSupplierIds.length) return;
    const targetBrand = brands.find(
      (brand) => brand.id === bulkUnassignedBrandId,
    );
    if (!targetBrand) return;
    const nextSupplierIds = Array.from(
      new Set([...targetBrand.supplier_ids, ...selectedUnassignedSupplierIds]),
    );
    await onUpdateBrand(targetBrand.id, {
      name: targetBrand.name,
      supplier_ids: nextSupplierIds,
      default_payment_term: targetBrand.default_payment_term,
      notes: targetBrand.notes,
      is_active: targetBrand.is_active,
    });
    setSelectedUnassignedSupplierIds([]);
    setBulkUnassignedBrandId("");
    setUnassignedSupplierTargets({});
  }

  async function handleBulkIgnoreUnassignedSuppliers() {
    if (!selectedUnassignedSupplierIds.length) return;
    for (const supplierId of selectedUnassignedSupplierIds) {
      const supplier = supplierMap.get(supplierId);
      if (!supplier) continue;
      await onUpdateSupplier(supplier.id, {
        name: supplier.name,
        default_payment_term: supplier.default_payment_term,
        notes: supplier.notes,
        ignore_in_purchase_planning: true,
        is_active: supplier.is_active,
      });
    }
    setSelectedUnassignedSupplierIds([]);
    setBulkUnassignedBrandId("");
    setUnassignedSupplierTargets({});
  }

  function toggleUnassignedSupplierSelection(supplierId: string) {
    setSelectedUnassignedSupplierIds((current) =>
      current.includes(supplierId)
        ? current.filter((value) => value !== supplierId)
        : [...current, supplierId],
    );
  }

  function getInlineEditablePlan(
    collectionSnapshot: PlanningCollectionSnapshot | null | undefined,
  ) {
    if (!collectionSnapshot?.plans.length) {
      return null;
    }
    return (
      collectionSnapshot.plans.find((plan) => plan.status !== "imported") ??
      null
    );
  }

  async function handleInlinePlanSave(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
  ) {
    if (
      !inlinePlanEdit ||
      inlinePlanEdit.brand_key !== snapshot.key ||
      inlinePlanEdit.collection_id !== collection.id
    ) {
      return;
    }
    const normalizedAmount = normalizePtBrMoneyInput(inlinePlanEdit.value);
    const collectionSnapshot = snapshot.collections.get(collection.id);
    const editablePlan = inlinePlanEdit.plan_id
      ? collectionSnapshot?.plans.find(
          (plan) => plan.id === inlinePlanEdit.plan_id,
        )
      : getInlineEditablePlan(collectionSnapshot);
    const supplierIds = editablePlan?.supplier_ids?.length
      ? editablePlan.supplier_ids
      : snapshot.supplierIds;
    const brand = snapshot.brandId ? brandMap.get(snapshot.brandId) : undefined;
    const paymentTerm =
      brand?.default_payment_term ??
      editablePlan?.payment_term ??
      supplierIds
        .map((supplierId) => supplierMap.get(supplierId)?.default_payment_term)
        .find(Boolean) ??
      null;
    const payload = {
      brand_id: snapshot.brandId,
      supplier_id: supplierIds[0] ?? null,
      supplier_ids: supplierIds,
      collection_id: collection.id,
      season_phase: editablePlan?.season_phase ?? "main",
      title: snapshot.brandName,
      order_date: editablePlan?.order_date ?? today,
      expected_delivery_date:
        editablePlan?.expected_delivery_date ?? collection.end_date,
      purchased_amount: normalizedAmount,
      payment_term: paymentTerm,
      status: editablePlan?.status ?? "planned",
      notes: editablePlan?.notes ?? null,
    };
    if (editablePlan) {
      await onUpdatePlan(editablePlan.id, payload);
    } else {
      await onCreatePlan(payload);
    }
    setInlinePlanEdit(null);
  }

  function buildNewCollectionPlanPayload(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
    overrides?: Partial<Record<string, unknown>>,
  ) {
    const supplierIds = snapshot.supplierIds;
    const brand = snapshot.brandId ? brandMap.get(snapshot.brandId) : undefined;
    const paymentTerm =
      brand?.default_payment_term ??
      supplierIds
        .map((supplierId) => supplierMap.get(supplierId)?.default_payment_term)
        .find(Boolean) ??
      null;
    return {
      brand_id: snapshot.brandId,
      supplier_id: supplierIds[0] ?? null,
      supplier_ids: supplierIds,
      collection_id: collection.id,
      season_phase: "main",
      title: snapshot.brandName,
      order_date: today,
      expected_delivery_date: collection.end_date,
      purchased_amount: "0.00",
      payment_term: paymentTerm,
      status: "planned",
      notes: null,
      ...overrides,
    };
  }

  function buildCollectionPlanPayload(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
    plan: PurchasePlan,
    overrides?: Partial<Record<string, unknown>>,
  ) {
    const supplierIds = plan.supplier_ids?.length
      ? plan.supplier_ids
      : snapshot.supplierIds;
    const brand = snapshot.brandId ? brandMap.get(snapshot.brandId) : undefined;
    const paymentTerm =
      brand?.default_payment_term ??
      plan.payment_term ??
      supplierIds
        .map((supplierId) => supplierMap.get(supplierId)?.default_payment_term)
        .find(Boolean) ??
      null;
    return {
      brand_id: snapshot.brandId ?? plan.brand_id ?? null,
      supplier_id: supplierIds[0] ?? plan.supplier_id ?? null,
      supplier_ids: supplierIds,
      collection_id: collection.id,
      season_phase: plan.season_phase ?? "main",
      title: plan.title || snapshot.brandName,
      order_date: plan.order_date ?? today,
      expected_delivery_date:
        plan.expected_delivery_date ?? collection.end_date,
      purchased_amount: plan.purchased_amount,
      payment_term: paymentTerm,
      status: plan.status ?? "planned",
      notes: plan.notes ?? null,
      ...overrides,
    };
  }

  async function handleSaveCollectionObservation() {
    if (!collectionObservationModal) {
      return;
    }
    const snapshot = planningBrands.find(
      (item) => item.key === collectionObservationModal.brandKey,
    );
    const collection = collectionMap.get(
      collectionObservationModal.collectionId,
    );
    if (!snapshot || !collection) {
      closeCollectionObservationModal();
      return;
    }
    const collectionSnapshot = snapshot.collections.get(collection.id);
    const notes =
      normalizeDisplayText(collectionObservationModal.notes).trim() || null;

    if (!collectionSnapshot?.plans.length) {
      if (!notes) {
        closeCollectionObservationModal();
        return;
      }
      await onCreatePlan(
        buildNewCollectionPlanPayload(snapshot, collection, {
          notes,
        }),
      );
      closeCollectionObservationModal();
      return;
    }

    for (const plan of collectionSnapshot.plans) {
      await onUpdatePlan(
        plan.id,
        buildCollectionPlanPayload(snapshot, collection, plan, {
          notes,
        }),
      );
    }
    closeCollectionObservationModal();
  }

  async function handleToggleCollectionConfirmation(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
  ) {
    const collectionSnapshot = snapshot.collections.get(collection.id);
    if (
      !collectionSnapshot ||
      !isCollectionConfirmationEditable(collection) ||
      !hasCollectionConfirmableOrder(collectionSnapshot)
    ) {
      return;
    }
    const nextStatus = getCollectionConfirmedState(
      collection,
      collectionSnapshot,
    )
      ? "planned"
      : "confirmed";
    for (const plan of collectionSnapshot.plans) {
      await onUpdatePlan(
        plan.id,
        buildCollectionPlanPayload(snapshot, collection, plan, {
          status: nextStatus,
        }),
      );
    }
  }

  function updateInvoiceDraftField<Key extends keyof PurchaseInvoiceDraft>(
    field: Key,
    value: PurchaseInvoiceDraft[Key],
  ) {
    setInvoiceDraft((current) => ({ ...current, [field]: value }));
  }

  function handleInvoiceSupplierChange(option: SingleValue<SelectOption>) {
    const supplierId = asSingleValue(option);
    const supplier = supplierId ? supplierMap.get(supplierId) : undefined;
    setInvoiceDraft((current) => ({
      ...current,
      supplier_id: supplierId || null,
      supplier_name: supplier?.name ?? current.supplier_name,
    }));
  }

  function startInlinePlanEdit(
    snapshot: PlanningBrandSnapshot,
    collection: CollectionSeason,
  ) {
    const collectionSnapshot = snapshot.collections.get(collection.id);
    const editablePlan = getInlineEditablePlan(collectionSnapshot);
    setInlinePlanEdit({
      brand_key: snapshot.key,
      collection_id: collection.id,
      plan_id: editablePlan?.id ?? null,
      value: toInputAmount(
        collectionSnapshot?.plannedAmount ??
          editablePlan?.purchased_amount ??
          "0.00",
      ),
      creating: editablePlan === null,
    });
  }

  function cancelInlinePlanEdit() {
    setInlinePlanEdit(null);
  }

  function renderSummaryFilters() {
    return (
      <section className="section-toolbar-panel purchase-toolbar-panel">
        <div className="purchase-filter-bar">
          <label>
            Ano
            <Select
              options={yearOptions}
              value={selectedYearOption}
              onChange={(option) => {
                const nextYear = asSingleValue(option);
                const shouldKeepCollection =
                  !selectedFilterCollection ||
                  !nextYear ||
                  String(selectedFilterCollection.season_year ?? "") ===
                    nextYear;
                onChangeFilters({
                  ...filters,
                  year: nextYear,
                  collection_id: shouldKeepCollection
                    ? filters.collection_id
                    : "",
                  brand_id: "",
                  status: "",
                });
              }}
              isClearable
              placeholder="Todos"
              styles={purchaseSelectStyles}
              menuPortalTarget={portalTarget}
            />
          </label>
          <label>
            Fornecedor
            <Select
              options={purchaseSupplierOptions}
              value={selectedSupplierOption}
              onChange={(option) =>
                onChangeFilters({
                  ...filters,
                  supplier_id: asSingleValue(option),
                  brand_id: "",
                  status: "",
                })
              }
              isClearable
              placeholder="Todos"
              styles={purchaseSelectStyles}
              menuPortalTarget={portalTarget}
            />
          </label>
          <label>
            Coleção
            <Select
              options={collectionOptions}
              value={selectedCollectionOption}
              onChange={(option) => {
                const nextCollectionId = asSingleValue(option);
                const nextCollection = nextCollectionId
                  ? (collectionMap.get(nextCollectionId) ?? null)
                  : null;
                onChangeFilters({
                  ...filters,
                  year: nextCollection?.season_year
                    ? String(nextCollection.season_year)
                    : filters.year,
                  collection_id: nextCollectionId,
                  brand_id: "",
                  status: "",
                });
              }}
              isClearable
              placeholder="Todas"
              styles={purchaseSelectStyles}
              menuPortalTarget={portalTarget}
            />
          </label>
          <div className="action-row"></div>
        </div>
      </section>
    );
  }

  function renderPlanningFilters() {
    return (
      <section className="panel">
        <div className="purchase-filter-bar">
          <label>
            <Select
              options={planningCollectionOptions}
              value={
                planningCollectionOptions.find(
                  (option) => option.value === (planningCollection?.id ?? ""),
                ) ?? null
              }
              onChange={(option) =>
                setPlanningCollectionId(
                  asSingleValue(option) || currentCollection?.id || "",
                )
              }
              placeholder="Foco"
              styles={purchaseSelectStyles}
              menuPortalTarget={portalTarget}
            />
          </label>
          <label>
            <Select<SelectOption, true>
              options={comparisonCollectionOptions}
              value={selectedComparisonCollectionOptions}
              onChange={(options) => {
                const nextIds = asMultiValue(options);
                if (
                  planningCollection?.id &&
                  !nextIds.includes(planningCollection.id)
                ) {
                  setCompareCollectionIds([...nextIds, planningCollection.id]);
                  return;
                }
                setCompareCollectionIds(nextIds);
              }}
              isMulti
              closeMenuOnSelect={false}
              hideSelectedOptions={false}
              controlShouldRenderValue={false}
              placeholder="Coleções"
              styles={purchaseSelectStyles}
              menuPortalTarget={portalTarget}
            />
          </label>
          <div className="status-select-switch">
            <button
              className={!filters.status ? "active" : ""}
              type="button"
              onClick={() => onChangeFilters({ ...filters, status: "" })}
            >
              Todos
            </button>
            <button
              className={filters.status === "planned" ? "active" : ""}
              type="button"
              onClick={() => onChangeFilters({ ...filters, status: "planned" })}
            >
              Planejado
            </button>
            <button
              className={filters.status === "confirmed" ? "active" : ""}
              type="button"
              onClick={() =>
                onChangeFilters({ ...filters, status: "confirmed" })
              }
            >
              Confirmado
            </button>
          </div>
          <div className="purchase-toggle-group">
            <label className="purchase-filter-toggle">
              <span className="purchase-filter-toggle-control">
                <input
                  type="checkbox"
                  checked={showPlanningDetail}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setShowPlanningDetail(checked);
                    setShowPlanningReturns(checked);
                    setShowPlanningSales(checked);
                  }}
                />
                <span>Detalhamento</span>
              </span>
            </label>
          </div>
          <div className="action-row action-row--toolbar">
            <button
              className="icon-action-button"
              type="button"
              onClick={() => openBrandModal()}
              title="Nova marca"
            >
              <TagIcon />
            </button>
            <button
              className="icon-action-button"
              type="button"
              onClick={openInvoiceModal}
              title="Nova nota fiscal"
            >
              <InvoiceIcon />
            </button>
            <button
              className="icon-action-button"
              type="button"
              onClick={() => setPurchaseReturnsPanelOpen(true)}
              title="Gerenciar devoluções"
            >
              <ReturnsIcon />
            </button>
          </div>
        </div>
      </section>
    );
  }
  function renderCadastrosToolbar() {
    return (
      <section className="section-toolbar-panel purchase-toolbar-panel">
        <div className="purchase-filter-bar purchase-filter-bar--compact">
          <label>
            Coleção atual
            <input value={currentCollection?.season_label || "-"} disabled />
          </label>
          <label>
            Coleções cadastradas
            <input value={String(collections.length)} disabled />
          </label>
          <div className="action-row">
            <button
              className="secondary-button"
              type="button"
              onClick={() => openBrandModal()}
            >
              Nova marca
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => openSupplierModal()}
            >
              Novo fornecedor
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => openCollectionModal()}
            >
              Nova coleção
            </button>
          </div>
        </div>
      </section>
    );
  }
  function renderInlinePlannedAmount(
    snapshot: PlanningBrandSnapshot | null,
    collection: CollectionSeason,
    options?: { compact?: boolean; highlight?: boolean; showEditButton?: boolean; extraActions?: React.ReactNode },
  ) {
    if (!snapshot) {
      return <span>{formatPurchaseDisplayAmount("0.00")}</span>;
    }
    const collectionSnapshot = snapshot.collections.get(collection.id);
    if (!collectionSnapshot) {
      return <span>{formatPurchaseDisplayAmount("0.00")}</span>;
    }
    const isEditing =
      inlinePlanEdit?.brand_key === snapshot.key &&
      inlinePlanEdit.collection_id === collection.id;
    const inlineEditClassName = [
      "planning-inline-edit",
      options?.compact ? "" : "planning-inline-edit-table",
      options?.compact ? "planning-inline-edit-compact" : "",
      isEditing ? "is-editing" : "is-readonly",
    ]
      .filter(Boolean)
      .join(" ");
    const netDisplayLine = showPlanningReturns
      ? buildPurchaseNetDisplayLine(
          collectionSnapshot.plannedAmount,
          collectionSnapshot.returnsAmount,
        )
      : null;

    const isConfirmed = getCollectionConfirmedState(
      collection,
      collectionSnapshot,
    );
    const valueClassName = [
      "planning-inline-edit-value",
      options?.highlight ? "is-highlighted" : "",
      isConfirmed ? "is-confirmed" : "is-planned",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className={inlineEditClassName}>
        {isEditing ? (
          <div className="planning-inline-edit-container">
            <MoneyInput
              autoFocus
              className="planning-inline-input"
              value={inlinePlanEdit.value}
              onValueChange={(value) =>
                setInlinePlanEdit({ ...inlinePlanEdit, value })
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  void handleInlinePlanSave(snapshot, collection);
                } else if (e.key === "Escape") {
                  cancelInlinePlanEdit();
                }
              }}
            />
            <div className="planning-inline-actions">
              <button
                className="cockpit-btn is-success"
                type="button"
                onClick={() => void handleInlinePlanSave(snapshot, collection)}
                title="Salvar"
              >
                <CheckIcon />
              </button>
              <button
                className="cockpit-btn"
                type="button"
                onClick={cancelInlinePlanEdit}
                title="Cancelar"
              >
                <CloseIcon />
              </button>
            </div>
          </div>
        ) : (
          <div className="metric-value-container">
            <span className={valueClassName}>
              {formatPurchaseDisplayAmount(collectionSnapshot.plannedAmount)}
            </span>
            {options?.showEditButton && (
              <button
                className="table-button icon-button cockpit-btn ml-1"
                type="button"
                onClick={() => startInlinePlanEdit(snapshot, collection)}
                title="Editar valor planejado"
              >
                <EditIcon />
              </button>
            )}
            {options?.extraActions}
          </div>
        )}
      </div>
    );
  }

  function renderInstallmentRow(installment: PurchaseInstallment) {
    const candidateOptions = installment.candidates.map((candidate) => ({
      value: candidate.entry_id,
      label: `${candidate.title} - ${formatPurchaseDisplayAmount(candidate.total_amount)}`,
    }));
    const selectedCandidate =
      candidateOptions.find(
        (option) => option.value === installment.financial_entry_id,
      ) ?? null;

    return (
      <tr key={installment.id}>
        <td className="purchase-installments-col-supplier">{installment.supplier_name || "-"}</td>
        <td className="purchase-installments-col-invoice">{installment.invoice_number || "-"}</td>
        <td className="purchase-installments-col-label">
          {installment.installment_label || installment.installment_number}
        </td>
        <td className="purchase-installments-col-date">{renderResponsivePurchaseDate(installment.due_date)}</td>
        <td className="numeric-cell purchase-installments-col-amount">
          {formatPurchaseDisplayAmount(installment.amount)}
        </td>
        <td className="purchase-installments-col-status">{renderPurchaseStatusBadge(installment.status)}</td>
        <td className="purchase-installments-link-cell">
          <Select
            options={candidateOptions}
            value={selectedCandidate}
            onChange={(option) =>
              void handleInstallmentLink(installment.id, asSingleValue(option))
            }
            isClearable
            placeholder="Selecionar lancamento"
            styles={purchaseSelectStyles}
            menuPortalTarget={portalTarget}
          />
        </td>
      </tr>
    );
  }

  function renderResumo() {
    return (
      <div className="content-grid">
        {renderSummaryFilters()}

        <section className="kpi-grid compact-kpis-four">
          {renderMetricCard(
            "Compras custo",
            formatPurchaseDisplayAmount(purchaseCostTotal),
          )}
          {renderMetricCard(
            "Devoluções",
            formatPurchaseDisplayAmount(purchaseReturnCostTotal),
          )}
          {renderMetricCard(
            "Custo líquido",
            formatPurchaseDisplayAmount(netPurchaseCostTotal),
          )}
          {renderMetricCard(
            "Pago",
            formatPurchaseDisplayAmount(overview.summary.paid_total),
          )}
          {renderMetricCard(
            "Em aberto",
            formatPurchaseDisplayAmount(
              overview.summary.outstanding_payable_total,
            ),
          )}
        </section>

        <section className="purchase-two-column">
          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Fluxo mensal das compras</h3>
            </div>
            <div className="table-shell purchase-collections-table-shell">
              <table className="erp-table purchase-collections-table compact-table">
                <thead>
                  <tr>
                    <th>Periodo</th>
                    <th className="numeric-cell">Previsto</th>
                    <th className="numeric-cell">Saldo aberto</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.monthly_projection.length ? (
                    overview.monthly_projection.map((item) => (
                      <tr key={item.reference}>
                        <td>{item.reference}</td>
                        <td className="numeric-cell tabular-nums">
                          {formatPurchaseDisplayAmount(item.planned_outflows)}
                        </td>
                        <td className="numeric-cell tabular-nums">
                          {formatPurchaseDisplayAmount(item.open_balance)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={3}>Nenhuma projecao disponivel.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Resumo operacional</h3>
            </div>
            <div className="summary-list">
              <div className="summary-row">
                <span>Notas registradas</span>
                <strong>{overview.invoices.length}</strong>
              </div>
              <div className="summary-row">
                <span>Compras planejadas</span>
                <strong>{overview.plans.length}</strong>
              </div>
              <div className="summary-row">
                <span>Parcelas previstas</span>
                <strong>{overview.open_installments.length}</strong>
              </div>
              <div className="summary-row">
                <span>Fornecedores ativos</span>
                <strong>
                  {suppliers.filter((supplier) => supplier.is_active).length}
                </strong>
              </div>
              <div className="summary-row">
                <span>Coleções ativas</span>
                <strong>
                  {
                    collections.filter((collection) => collection.is_active)
                      .length
                  }
                </strong>
              </div>
            </div>
          </article>
        </section>

        <section className="purchase-full-width-section">
          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Totalizações por coleção / fornecedor / custo</h3>
            </div>
            <div className="table-shell tall">
              <table className="erp-table compact-table">
                <thead>
                  <tr>
                    <th>Coleção</th>
                    <th>Fornecedor</th>
                    <th className="numeric-cell">Compras</th>
                    <th className="numeric-cell">Devoluções</th>
                    <th className="numeric-cell">Custo líquido</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.cost_totals.length ? (
                    overview.cost_totals.map((item) => (
                      <tr key={`${item.collection_name}-${item.supplier_name}`}>
                        <td>{item.collection_name}</td>
                        <td>{item.supplier_name}</td>
                        <td className="numeric-cell tabular-nums">
                          {formatPurchaseDisplayAmount(
                            item.purchase_cost_total,
                          )}
                        </td>
                        <td className="numeric-cell tabular-nums">
                          {formatPurchaseDisplayAmount(
                            item.purchase_return_cost_total,
                          )}
                        </td>
                        <td className="numeric-cell tabular-nums">
                          {formatPurchaseDisplayAmount(item.net_cost_total)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5}>
                        Nenhuma totalização por coleção e fornecedor encontrada.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className="purchase-two-column">
          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Compras registradas</h3>
            </div>
            <div className="table-shell tall">
              <table className="erp-table purchase-summary-invoices-table">
                <thead>
                  <tr>
                    <th>Fornecedor</th>
                    <th>Coleção</th>
                    <th>Nota</th>
                    <th>Emissão</th>
                    <th className="numeric-cell">Valor</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.invoices.length ? (
                    overview.invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td className="purchase-summary-invoices-col-supplier">{invoice.supplier_name || "-"}</td>
                        <td className="purchase-summary-invoices-col-collection">{invoice.collection_name || "-"}</td>
                        <td className="purchase-summary-invoices-col-invoice">{invoice.invoice_number || "-"}</td>
                        <td className="purchase-summary-invoices-col-date">{renderResponsivePurchaseDate(invoice.issue_date)}</td>
                        <td className="numeric-cell purchase-summary-invoices-col-amount">
                          {formatPurchaseDisplayAmount(invoice.total_amount)}
                        </td>
                        <td className="purchase-summary-invoices-col-status">{renderPurchaseStatusBadge(invoice.status)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>Nenhuma nota fiscal registrada.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Parcelas previstas</h3>
            </div>
            <div className="table-shell tall">
              <table className="erp-table purchase-summary-installments-table">
                <thead>
                  <tr>
                    <th>Fornecedor</th>
                    <th>Nota</th>
                    <th>Parcela</th>
                    <th>Vencimento</th>
                    <th className="numeric-cell">Valor</th>
                    <th>Status</th>
                    <th>Vínculo</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.open_installments.length ? (
                    overview.open_installments.map((installment) =>
                      renderInstallmentRow(installment),
                    )
                  ) : (
                    <tr>
                      <td colSpan={7}>Nenhuma parcela prevista em aberto.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </div>
    );
  }

  function renderPlanejamento() {
    const showConfirmationColumn = planningCollection
      ? isCollectionConfirmationEditable(planningCollection)
      : false;
    const visibleBrands = planningTableBrands.filter((snapshot) => {
      if (
        filters.supplier_id &&
        !snapshot.supplierIds.includes(filters.supplier_id)
      ) {
        return false;
      }
      if (filters.status && planningCollection) {
        const currentSnapshot = snapshot.collections.get(planningCollection.id);
        if (
          !currentSnapshot ||
          !currentSnapshot.plans.some((plan) => plan.status === filters.status)
        ) {
          return false;
        }
      }
      return true;
    });
    const visibleCollectionTotals = new Map(
      selectedComparisonCollections.map((collection) => {
        const totals = visibleBrands.reduce(
          (accumulator, snapshot) => {
            const collectionSnapshot = snapshot.collections.get(collection.id);
            accumulator.plannedCents += toCents(
              collectionSnapshot?.plannedAmount ?? "0.00",
            );
            accumulator.receivedCents += toCents(
              collectionSnapshot?.receivedAmount ?? "0.00",
            );
            accumulator.returnsCents += toCents(
              collectionSnapshot?.returnsAmount ?? "0.00",
            );
            accumulator.soldCents += toCents(
              collectionSnapshot?.soldAmount ?? "0.00",
            );
            return accumulator;
          },
          {
            plannedCents: 0,
            receivedCents: 0,
            returnsCents: 0,
            soldCents: 0,
          },
        );
        return [collection.id, totals] as const;
      }),
    );
    const totalRowProfitPercentage = Math.round(
      calculatePurchaseProfitMargin(
        Array.from(visibleCollectionTotals.values()).reduce(
          (sum, totals) => sum + totals.soldCents,
          0,
        ) / 100,
        Array.from(visibleCollectionTotals.values()).reduce(
          (sum, totals) => sum + totals.receivedCents,
          0,
        ) / 100,
        Array.from(visibleCollectionTotals.values()).reduce(
          (sum, totals) => sum + totals.returnsCents,
          0,
        ) / 100,
      ),
    );

    return (
      <div className="content-grid">
        {renderPlanningFilters()}

        <article className="panel-card">
          <div className="table-shell purchase-brand-planning-table-shell">
            <table className="erp-table compact-table">
              <thead>
                <tr>
                  <th className="sticky-col">Nome</th>
                  {selectedComparisonCollections.map((collection) => (
                    <th
                      className={`numeric-cell${planningCollection?.id === collection.id ? " planning-current-column" : ""}`}
                      key={`header-${collection.id}`}
                    >
                      {collection.season_label || collection.name}
                    </th>
                  ))}
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {visibleBrands.length ? (
                  visibleBrands.map((snapshot) => {
                    const currentSnapshot = planningCollection
                      ? snapshot.collections.get(planningCollection.id)
                      : null;
                    const currentConfirmed = planningCollection
                      ? getCollectionConfirmedState(
                          planningCollection,
                          currentSnapshot,
                        )
                      : false;
                    const hasCurrentOrderToConfirm = planningCollection
                      ? hasCollectionConfirmableOrder(currentSnapshot)
                      : false;
                    const canToggleCurrentConfirmation = Boolean(
                      planningCollection &&
                      hasCurrentOrderToConfirm &&
                      !snapshot.isInactiveGroup &&
                      snapshot.brandId &&
                      isCollectionConfirmationEditable(planningCollection),
                    );
                    return (
                      <tr key={snapshot.key}>
                        <td className="sticky-col">
                          {snapshot.isInactiveGroup ? (
                            <div className="planning-brand-cell">
                              <strong>{snapshot.brandName}</strong>
                              <span>
                                {snapshot.groupedBrandIds?.length ?? 0} marcas
                                agrupadas
                              </span>
                              {showPlanningProfit && (
                                <span className="planning-brand-performance">
                                  {(() => {
                                    let totalSales = 0;
                                    let totalReceived = 0;
                                    let totalReturns = 0;
                                    selectedComparisonCollections.forEach(
                                      (coll) => {
                                        const collSnap =
                                          snapshot.collections.get(coll.id);
                                        if (collSnap) {
                                          totalSales += Number(
                                            collSnap.soldAmount,
                                          );
                                          totalReceived += Number(
                                            collSnap.receivedAmount,
                                          );
                                          totalReturns += Number(
                                            collSnap.returnsAmount,
                                          );
                                        }
                                      },
                                    );
                                    const percentage = Math.round(
                                      calculatePurchaseProfitMargin(
                                        totalSales,
                                        totalReceived,
                                        totalReturns,
                                      ),
                                    );
                                    return (
                                      <span
                                        style={{
                                          color:
                                            percentage >= 0
                                              ? "#10b981"
                                              : "#ef4444",
                                        }}
                                      >
                                        {percentage}%
                                      </span>
                                    );
                                  })()}
                                </span>
                              )}
                            </div>
                          ) : (
                            <div className="planning-brand-cell">
                              <strong>{snapshot.brandName}</strong>
                              {showPlanningProfit && (
                                <span className={`planning-brand-performance`}>
                                  {(() => {
                                    let totalSales = 0;
                                    let totalReceived = 0;
                                    let totalReturns = 0;
                                    selectedComparisonCollections.forEach(
                                      (coll) => {
                                        const collSnap =
                                          snapshot.collections.get(coll.id);
                                        if (collSnap) {
                                          totalSales += Number(
                                            collSnap.soldAmount,
                                          );
                                          totalReceived += Number(
                                            collSnap.receivedAmount,
                                          );
                                          totalReturns += Number(
                                            collSnap.returnsAmount,
                                          );
                                        }
                                      },
                                    );
                                    const percentage = Math.round(
                                      calculatePurchaseProfitMargin(
                                        totalSales,
                                        totalReceived,
                                        totalReturns,
                                      ),
                                    );
                                    return (
                                      <span
                                        style={{
                                          color:
                                            percentage >= 0
                                              ? "#10b981"
                                              : "#ef4444",
                                        }}
                                      >
                                        {percentage}%
                                      </span>
                                    );
                                  })()}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        {selectedComparisonCollections.map((collection) => {
                          const collectionSnapshot = snapshot.collections.get(
                            collection.id,
                          );

                          return (
                            <td
                              className={`numeric-cell${planningCollection?.id === collection.id ? " planning-current-column" : ""}`}
                              key={`cell-${snapshot.key}-${collection.id}`}
                            >
                              <div className="planning-metric-stack">
                                {/* Line 1: Pedido (Cor identifica estado) */}
                                <div
                                  className="metric-line metric-line-pedido"
                                  title="Pedido"
                                >
                                  {renderInlinePlannedAmount(snapshot, collection, {
                                    compact: true,
                                    highlight: true,
                                    showEditButton: false,
                                  })}
                                </div>

                                {showPlanningDetail && (
                                  <>
                                    <div
                                      className="metric-line"
                                      title="Recebido"
                                    >
                                      <div className="metric-value-stack">
                                        <div className="metric-value-container color-recebido">
                                          {formatPurchaseDisplayAmount(
                                            collectionSnapshot?.receivedAmount ||
                                              0,
                                          )}
                                        </div>
                                        {renderOutstandingReceiptHint(
                                          collectionSnapshot?.outstandingAmount ||
                                            0,
                                        )}
                                      </div>
                                      <div className="metric-actions-container" />
                                      <div className="metric-actions-container-confirm" />
                                    </div>
                                    <div
                                      className="metric-line"
                                      title="Devolvido"
                                    >
                                      <div className="metric-value-container color-devolucao">
                                        {formatPurchaseDisplayAmount(
                                          collectionSnapshot?.returnsAmount ||
                                            0,
                                        )}
                                      </div>
                                      <div className="metric-actions-container" />
                                      <div className="metric-actions-container-confirm" />
                                    </div>
                                    <div
                                      className="metric-line"
                                      title="Vendido"
                                    >
                                      <div className="metric-value-container color-venda">
                                        {formatPurchaseDisplayAmount(
                                          collectionSnapshot?.soldAmount || 0,
                                        )}
                                      </div>
                                      <div className="metric-actions-container" />
                                      <div className="metric-actions-container-confirm" />
                                    </div>
                                  </>
                                )}

                                {/* Line 5: Lucro */}
                                {(() => {
                                  const percentage = Math.round(
                                    calculatePurchaseProfitMargin(
                                      collectionSnapshot?.soldAmount || 0,
                                      collectionSnapshot?.receivedAmount || 0,
                                      collectionSnapshot?.returnsAmount || 0,
                                    ),
                                  );
                                  return (
                                    <div
                                      className="metric-line"
                                      title="Lucro %"
                                    >
                                      <div
                                        className="metric-value-container"
                                        style={{
                                          color:
                                            percentage >= 0
                                              ? "#10b981"
                                              : "#ef4444",
                                        }}
                                      >
                                        {percentage}%
                                      </div>
                                      <div className="metric-actions-container" />
                                      <div className="metric-actions-container-confirm" />
                                    </div>
                                  );
                                })()}
                              </div>
                            </td>
                          );
                        })}
                        <td>
                          <div className="action-row">
                            {snapshot.isInactiveGroup ? (
                              <button
                                aria-label="Editar marcas desativadas"
                                className="table-button icon-button"
                                title="Editar marcas desativadas"
                                type="button"
                                onClick={openInactiveBrandsModal}
                              >
                                <EditIcon />
                              </button>
                            ) : !snapshot.brandId &&
                              snapshot.brandName === "Sem marca" ? (
                              <button
                                aria-label="Editar fornecedores sem marca"
                                className="table-button icon-button"
                                title="Editar fornecedores sem marca"
                                type="button"
                                onClick={openUnassignedSuppliersModal}
                              >
                                <EditIcon />
                              </button>
                            ) : snapshot.brandId ? (
                              <>
                                <button
                                  aria-label={`Editar marca ${snapshot.brandName}`}
                                  className="table-button icon-button"
                                  title="Editar marca"
                                  type="button"
                                  onClick={() =>
                                    openBrandModal(
                                      brandMap.get(
                                        snapshot.brandId as string,
                                      ) ?? undefined,
                                    )
                                  }
                                >
                                  <EditIcon />
                                </button>
                                <button
                                  aria-label={`Excluir marca ${snapshot.brandName}`}
                                  className="ghost-button icon-button danger-text-action"
                                  title="Excluir marca"
                                  type="button"
                                  onClick={() =>
                                    void handleDeleteBrand(
                                      snapshot.brandId as string,
                                    )
                                  }
                                >
                                  <DeleteIcon />
                                </button>
                              </>
                            ) : (
                              <span>-</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={
                        selectedComparisonCollections.length +
                        (showConfirmationColumn ? 6 : 5)
                      }
                    >
                      Nenhuma marca encontrada para esse recorte.
                    </td>
                  </tr>
                )}
                {visibleBrands.length ? (
                  <tr>
                    <td className="sticky-col">
                      <div className="planning-brand-cell">
                        <strong>Total</strong>
                        {showPlanningProfit && (
                          <span className="planning-brand-performance">
                            <span
                              style={{
                                color:
                                  totalRowProfitPercentage >= 0
                                    ? "#10b981"
                                    : "#ef4444",
                              }}
                            >
                              {totalRowProfitPercentage}%
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    {selectedComparisonCollections.map((collection) => {
                      const totals = visibleCollectionTotals.get(collection.id) ?? {
                        plannedCents: 0,
                        receivedCents: 0,
                        returnsCents: 0,
                        soldCents: 0,
                      };
                      const percentage = Math.round(
                        calculatePurchaseProfitMargin(
                          totals.soldCents / 100,
                          totals.receivedCents / 100,
                          totals.returnsCents / 100,
                        ),
                      );
                      return (
                        <td
                          className={`numeric-cell${planningCollection?.id === collection.id ? " planning-current-column" : ""}`}
                          key={`totals-${collection.id}`}
                        >
                          <div className="planning-metric-stack">
                            <div
                              className="metric-line metric-line-pedido"
                              title="Pedido"
                            >
                              <div className="metric-value-container">
                                <span className="planning-inline-edit-value is-highlighted">
                                  {formatPurchaseDisplayAmount(
                                    centsToAmount(totals.plannedCents),
                                  )}
                                </span>
                              </div>
                            </div>
                            {showPlanningDetail && (
                              <>
                                <div className="metric-line" title="Recebido">
                                  <div className="metric-value-stack">
                                    <div className="metric-value-container color-recebido">
                                      {formatPurchaseDisplayAmount(
                                        centsToAmount(totals.receivedCents),
                                      )}
                                    </div>
                                    {renderOutstandingReceiptHint(
                                      centsToAmount(
                                        Math.max(
                                          totals.plannedCents -
                                            totals.receivedCents,
                                          0,
                                        ),
                                      ),
                                    )}
                                  </div>
                                  <div className="metric-actions-container" />
                                  <div className="metric-actions-container-confirm" />
                                </div>
                                <div className="metric-line" title="Devolvido">
                                  <div className="metric-value-container color-devolucao">
                                    {formatPurchaseDisplayAmount(
                                      centsToAmount(totals.returnsCents),
                                    )}
                                  </div>
                                  <div className="metric-actions-container" />
                                  <div className="metric-actions-container-confirm" />
                                </div>
                                <div className="metric-line" title="Vendido">
                                  <div className="metric-value-container color-venda">
                                    {formatPurchaseDisplayAmount(
                                      centsToAmount(totals.soldCents),
                                    )}
                                  </div>
                                  <div className="metric-actions-container" />
                                  <div className="metric-actions-container-confirm" />
                                </div>
                              </>
                            )}
                            <div className="metric-line" title="Lucro %">
                              <div
                                className="metric-value-container"
                                style={{
                                  color:
                                    percentage >= 0 ? "#10b981" : "#ef4444",
                                }}
                              >
                                {percentage}%
                              </div>
                              <div className="metric-actions-container" />
                              <div className="metric-actions-container-confirm" />
                            </div>
                          </div>
                        </td>
                      );
                    })}
                    <td>
                      <span>-</span>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div
            className="purchase-planning-totals-dashboard"
            role="presentation"
          >
            {selectedComparisonCollections.map((collection) => (
              <div
                className="purchase-planning-total-card"
                key={`planning-total-${collection.id}`}
              >
                <span>{collection.season_label || collection.name}</span>
                <strong>
                  {formatPurchaseDisplayAmount(
                    collectionTotals.get(collection.id) ?? "0.00",
                  )}
                </strong>
              </div>
            ))}
          </div>
        </article>

        <section className="purchase-full-width-section">
          <article className="panel-card">
            <div className="purchase-panel-heading">
              <h3>Coleções</h3>
              <button
                className="secondary-button"
                type="button"
                onClick={() => openCollectionModal()}
              >
                Nova coleção
              </button>
            </div>
            <div className="table-shell purchase-collections-table-shell">
              <table className="erp-table purchase-collections-table purchase-collections-mobile-table">
                <thead>
                  <tr>
                    <th>Coleção</th>
                    <th>Ano</th>
                    <th>Inicio</th>
                    <th>Fim da coleção</th>
                    <th className="numeric-cell">Pedidos totais</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {collections.length ? (
                    collections.map((collection) => (
                      <tr key={collection.id}>
                        <td className="purchase-collections-col-name">{collection.season_label || collection.name}</td>
                        <td className="purchase-collections-col-year">{collection.season_year}</td>
                        <td className="purchase-collections-col-start">{renderResponsivePurchaseDate(collection.start_date)}</td>
                        <td className="purchase-collections-col-end">{renderResponsivePurchaseDate(collection.end_date)}</td>
                        <td className="numeric-cell purchase-collections-col-total">
                          {formatPurchaseDisplayAmount(
                            collectionTotals.get(collection.id) ?? "0.00",
                          )}
                        </td>
                        <td className="purchase-collections-col-status">{renderPurchaseStatusBadge(collection.is_active ? "active" : "inactive", collection.is_active ? "Ativa" : "Inativa")}</td>
                        <td>
                          <div className="action-row">
                            <button
                              className="table-button"
                              type="button"
                              onClick={() => openCollectionModal(collection)}
                            >
                              Editar
                            </button>
                            <button
                              className="ghost-button"
                              type="button"
                              onClick={() =>
                                void handleDeleteCollection(collection.id)
                              }
                            >
                              Excluir
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>Nenhuma coleção encontrada.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <article className="panel-card">
          <div className="purchase-panel-heading">
            <h3>Fluxo de pagamento previsto</h3>
          </div>
          <div className="table-shell purchase-collections-table-shell">
            <table className="erp-table purchase-collections-table">
              <thead>
                <tr>
                  <th>Periodo</th>
                  <th className="numeric-cell">Previsto</th>
                  <th className="numeric-cell">Saldo aberto</th>
                </tr>
              </thead>
              <tbody>
                {overview.monthly_projection.length ? (
                  overview.monthly_projection.map((item) => (
                    <tr key={item.reference}>
                      <td>{item.reference}</td>
                      <td className="numeric-cell">
                        {formatPurchaseDisplayAmount(item.planned_outflows)}
                      </td>
                      <td className="numeric-cell">
                        {formatPurchaseDisplayAmount(item.open_balance)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={3}>Nenhum fluxo previsto.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    );
  }

  function renderFornecedores() {
    return (
      <div className="content-grid">
        <article className="panel-card">
          <div className="purchase-panel-heading">
            <h3>Fornecedores</h3>
            <button
              className="secondary-button"
              type="button"
              onClick={() => openSupplierModal()}
            >
              Novo fornecedor
            </button>
          </div>
          <div className="table-shell tall">
              <table className="erp-table compact-table purchase-suppliers-table">
              <thead>
                <tr>
                  <th>Fornecedor</th>
                  <th>Prazo padrão</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.length ? (
                  suppliers.map((supplier) => (
                    <tr key={supplier.id}>
                      <td className="purchase-suppliers-col-name">{supplier.name}</td>
                      <td className="purchase-suppliers-col-term">{supplier.default_payment_term || "-"}</td>
                      <td className="purchase-suppliers-col-status">{renderPurchaseStatusBadge(supplier.is_active ? "active" : "inactive", supplier.is_active ? "Ativo" : "Inativo")}</td>
                      <td>
                        <div className="action-row">
                          <button
                            className="table-button"
                            type="button"
                            onClick={() => openSupplierModal(supplier)}
                          >
                            Editar
                          </button>
                          <button
                            className="ghost-button"
                            type="button"
                            onClick={() =>
                              void handleDeleteSupplier(supplier.id)
                            }
                          >
                            Excluir
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4}>Nenhum fornecedor encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    );
  }

  function renderDevolucoes() {
    return (
      <div className="content-grid">
        <section className="panel">
          <div className="purchase-filter-bar purchase-return-filter-bar">
            <label className="purchase-return-filter-field">
              Filtro
              <input
                value={purchaseReturnFilter}
                onChange={(event) =>
                  setPurchaseReturnFilter(event.target.value)
                }
                placeholder="Buscar por data, fornecedor, NF, status, observação ou valor"
              />
            </label>
            <label className="purchase-return-filter-field">
              Data inicial
              <input
                type="date"
                value={purchaseReturnDateFrom}
                onChange={(event) =>
                  setPurchaseReturnDateFrom(event.target.value)
                }
              />
            </label>
            <label className="purchase-return-filter-field">
              Data final
              <input
                type="date"
                value={purchaseReturnDateTo}
                onChange={(event) =>
                  setPurchaseReturnDateTo(event.target.value)
                }
              />
            </label>
            <div className="purchase-return-filter-field purchase-return-status-inline">
              <span className="purchase-return-inline-label">Status</span>
              <Select
                options={PURCHASE_RETURN_STATUS_OPTIONS}
                value={selectedPurchaseReturnVisibleStatusOptions}
                onChange={(options) =>
                  setPurchaseReturnVisibleStatuses(
                    normalizePurchaseReturnVisibleStatuses(
                      asMultiValue(options),
                    ),
                  )
                }
                isMulti
                closeMenuOnSelect={false}
                hideSelectedOptions={false}
                controlShouldRenderValue={false}
                placeholder={purchaseReturnStatusPlaceholder}
                styles={purchaseSelectStyles}
                menuPortalTarget={portalTarget}
              />
            </div>
            <div className="action-row">
              <button
                className="secondary-button"
                type="button"
                onClick={() => openPurchaseReturnModal()}
              >
                Nova devolução
              </button>
            </div>
          </div>
        </section>

        <article className="panel-card">
          <div className="purchase-panel-heading">
            <h3>Devolução de compras</h3>
          </div>
          <div className="table-shell tall">
            <table className="erp-table compact-table purchase-returns-table">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Fornecedor</th>
                  <th>Nota fiscal</th>
                  <th className="centered-cell">Status</th>
                  <th className="numeric-cell">Valor</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredPurchaseReturns.length ? (
                  filteredPurchaseReturns.map((purchaseReturn) => (
                    <tr
                      key={purchaseReturn.id}
                      className={
                        isPurchaseReturnActionRequired(purchaseReturn.status)
                          ? "purchase-return-row--action-needed"
                          : undefined
                      }
                    >
                      <td className="purchase-returns-col-date">{renderResponsivePurchaseDate(purchaseReturn.return_date)}</td>
                      <td className="purchase-returns-col-supplier">{purchaseReturn.supplier_name || "-"}</td>
                      <td className="purchase-returns-col-invoice">{purchaseReturn.invoice_number || "-"}</td>
                      <td className="centered-cell purchase-returns-col-status">
                        {renderPurchaseStatusBadge(purchaseReturn.status, labelizePurchaseReturnStatus(purchaseReturn.status))}
                      </td>
                      <td className="numeric-cell tabular-nums purchase-returns-col-amount">
                        {formatPurchaseDisplayAmount(purchaseReturn.amount)}
                      </td>
                      <td>
                        <div className="action-row">
                          <button
                            aria-label={`Editar devolução de ${purchaseReturn.supplier_name || "fornecedor"}`}
                            className="table-button icon-button"
                            title="Editar devolução"
                            type="button"
                            onClick={() =>
                              openPurchaseReturnModal(purchaseReturn)
                            }
                          >
                            <EditIcon />
                          </button>
                          <button
                            aria-label={`Excluir devolução de ${purchaseReturn.supplier_name || "fornecedor"}`}
                            className="ghost-button icon-button danger-text-action"
                            title="Excluir devolução"
                            type="button"
                            onClick={() =>
                              void handleDeletePurchaseReturn(purchaseReturn.id)
                            }
                          >
                            <DeleteIcon />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>Nenhuma devolução de compra encontrada.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    );
  }

  function renderInvoiceModal() {
    if (!invoiceModalOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card">
          <div className="purchase-panel-heading">
            <h3>Nova nota fiscal</h3>
            <ModalCloseButton onClick={closeInvoiceModal} />
          </div>

          <div className="content-grid">
            <section className="panel">
              <div className="purchase-panel-heading">
                <h3>Faturas de compra via API Linx</h3>
              </div>
              <p className="empty-state">
                Busca as faturas de compra na API da Linx, compara com os
                titulos ja vistos e inclui somente os lancamentos novos ou
                alterados em aberto.
              </p>
              {linxSyncFeedback && (
                <div
                  className={`purchase-sync-feedback is-${linxSyncFeedback.tone}`}
                  role="status"
                  aria-live="polite"
                >
                  {linxSyncFeedback.message}
                </div>
              )}
              <div className="action-row">
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void handleSyncLinxPurchaseInvoices()}
                  disabled={syncingLinxInvoices}
                  aria-busy={syncingLinxInvoices}
                >
                  {syncingLinxInvoices
                    ? "Sincronizando faturas de compra..."
                    : "Atualizar faturas de compra"}
                </button>
              </div>
            </section>

            <section className="panel">
              <label className="full-width">
                Texto da nota
                <textarea
                  className="large-textarea"
                  value={invoiceText}
                  onChange={(event) => setInvoiceText(event.target.value)}
                  placeholder="Cole aqui o texto bruto da nota fiscal..."
                />
              </label>
              <div className="action-row">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void handleExtractInvoice()}
                  disabled={!invoiceText.trim()}
                >
                  Extrair texto
                </button>
                <label
                  className="ghost-button"
                  style={{ cursor: uploadingXml ? "wait" : "pointer" }}
                >
                  {uploadingXml ? "Importando XML..." : "Importar XML"}
                  <input
                    hidden
                    type="file"
                    accept=".xml,text/xml,application/xml"
                    onChange={(event) =>
                      void handleXmlImport(event.target.files?.[0] ?? null)
                    }
                    disabled={uploadingXml}
                  />
                </label>
              </div>
            </section>

            <section className="panel">
              <div className="form-grid wide">
                <label>
                  Fornecedor
                  <Select
                    options={supplierOptions}
                    value={selectedInvoiceSupplierOption}
                    onChange={handleInvoiceSupplierChange}
                    isClearable
                    placeholder="Selecione"
                    styles={purchaseSelectStyles}
                    menuPortalTarget={portalTarget}
                  />
                </label>
                <label>
                  Nome do fornecedor
                  <input
                    value={invoiceDraft.supplier_name}
                    onChange={(event) =>
                      updateInvoiceDraftField(
                        "supplier_name",
                        event.target.value,
                      )
                    }
                    placeholder="Fornecedor da nota"
                  />
                </label>
                <label>
                  Coleção
                  <Select
                    options={collectionOptions}
                    value={selectedInvoiceCollectionOption}
                    onChange={(option) =>
                      updateInvoiceDraftField(
                        "collection_id",
                        asSingleValue(option) || null,
                      )
                    }
                    isClearable
                    placeholder="Selecione"
                    styles={purchaseSelectStyles}
                    menuPortalTarget={portalTarget}
                  />
                </label>
                <label>
                  Fase
                  <Select
                    options={SEASON_PHASE_OPTIONS as unknown as SelectOption[]}
                    value={
                      selectedInvoiceSeasonPhaseOption as unknown as SelectOption
                    }
                    onChange={(option) =>
                      updateInvoiceDraftField(
                        "season_phase",
                        (asSingleValue(option) || "main") as "main" | "high",
                      )
                    }
                    styles={purchaseSelectStyles}
                    menuPortalTarget={portalTarget}
                  />
                </label>
                <label>
                  Número da nota
                  <input
                    value={invoiceDraft.invoice_number ?? ""}
                    onChange={(event) =>
                      updateInvoiceDraftField(
                        "invoice_number",
                        event.target.value,
                      )
                    }
                  />
                </label>
                <label>
                  Emissão
                  <input
                    type="date"
                    value={invoiceDraft.issue_date ?? ""}
                    onChange={(event) =>
                      updateInvoiceDraftField("issue_date", event.target.value)
                    }
                  />
                </label>
                <label>
                  Entrada
                  <input
                    type="date"
                    value={invoiceDraft.entry_date ?? ""}
                    onChange={(event) =>
                      updateInvoiceDraftField("entry_date", event.target.value)
                    }
                  />
                </label>
                <label>
                  Valor
                  <MoneyInput
                    value={String(invoiceDraft.total_amount ?? "")}
                    onValueChange={(value) =>
                      updateInvoiceDraftField("total_amount", value)
                    }
                  />
                </label>
                <label>
                  Condicao de pagamento
                  <Select
                    options={paymentTermOptions}
                    value={selectedInvoiceTermOption}
                    onChange={(option) =>
                      updateInvoiceDraftField(
                        "payment_term",
                        asSingleValue(option) || null,
                      )
                    }
                    isClearable
                    placeholder="Selecione"
                    styles={purchaseSelectStyles}
                    menuPortalTarget={portalTarget}
                  />
                </label>
                <label className="full-width">
                  Observações
                  <textarea
                    value={invoiceDraft.notes ?? ""}
                    onChange={(event) =>
                      updateInvoiceDraftField("notes", event.target.value)
                    }
                  />
                </label>
              </div>
            </section>

            <section className="panel">
              <div className="purchase-panel-heading">
                <h3>Parcelas da nota</h3>
              </div>
              <div className="table-shell">
                <table className="erp-table compact-table">
                  <thead>
                    <tr>
                      <th>Parcela</th>
                      <th>Vencimento</th>
                      <th className="numeric-cell">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoiceDraft.installments.length ? (
                      invoiceDraft.installments.map((installment) => (
                        <tr
                          key={`${installment.installment_number}-${installment.installment_label ?? ""}`}
                        >
                          <td>
                            {installment.installment_label ||
                              installment.installment_number}
                          </td>
                          <td>{formatDate(installment.due_date)}</td>
                          <td className="numeric-cell tabular-nums">
                            {formatPurchaseDisplayAmount(installment.amount)}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3}>Nenhuma parcela informada.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="action-row">
              <button
                className="primary-button"
                type="button"
                onClick={() => void handleSaveInvoice()}
              >
                Salvar nota
              </button>
              <button
                className="ghost-button"
                type="button"
                onClick={closeInvoiceModal}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderBrandModal() {
    if (!brandModalOpen) return null;
    const isEditingBrand = Boolean(brandModal.id);
    const currentBrandSnapshot =
      planningBrands.find((snapshot) => snapshot.brandId === brandModal.id) ??
      planningBrands.find(
        (snapshot) => snapshot.brandName === brandModal.name,
      ) ??
      null;

    // Calcular Totais do Dashboard
    let totalPlanned = 0;
    let totalReceived = 0;
    let totalSold = 0;
    let totalReturns = 0;

    if (currentBrandSnapshot) {
      currentBrandSnapshot.collections.forEach((snapshot) => {
        totalPlanned += Number(
          normalizePtBrMoneyInput(snapshot.plannedAmount || 0),
        );
        totalReceived += Number(
          normalizePtBrMoneyInput(snapshot.receivedAmount || 0),
        );
        totalSold += Number(normalizePtBrMoneyInput(snapshot.soldAmount || 0));
        totalReturns += Number(
          normalizePtBrMoneyInput(snapshot.returnsAmount || 0),
        );
      });
    }
    const avgProfit = Math.round(
      calculatePurchaseProfitMargin(totalSold, totalReceived, totalReturns),
    );

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card purchase-brand-modal-card">
          <div className="purchase-panel-heading">
            <h3>{brandModal.id ? "Editar marca" : "Nova marca"}</h3>
            <ModalCloseButton onClick={closeBrandModal} />
          </div>

          <div className="brand-modal-unified-content">
            <div className="brand-modal-inputs-grid">
              <label className="brand-modal-field brand-modal-field--name">
                <input
                  placeholder="Nome da marca"
                  value={brandModal.name}
                  onChange={(event) =>
                    setBrandModal((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="brand-modal-field brand-modal-field--suppliers">
                <Select<SelectOption, true>
                  options={brandSupplierOptions}
                  value={selectedBrandSupplierOptions}
                  onChange={(options) =>
                    setBrandModal((current) => ({
                      ...current,
                      supplier_ids: asMultiValue(options),
                    }))
                  }
                  isMulti
                  isClearable
                  placeholder="Fornecedores"
                  styles={purchaseSelectStyles}
                  menuPortalTarget={portalTarget}
                />
              </label>
              <label className="brand-modal-field brand-modal-field--notes">
                <input
                  placeholder="Observações"
                  style={{ fontSize: "0.82rem" }}
                  value={brandModal.notes}
                  onChange={(event) =>
                    setBrandModal((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>
              <div className="brand-modal-field brand-modal-field--term">
                <Select
                  options={paymentTermOptions}
                  value={selectedBrandTermOption}
                  onChange={(option) =>
                    setBrandModal((current) => ({
                      ...current,
                      default_payment_term: asSingleValue(option) || "1x",
                    }))
                  }
                  isClearable
                  placeholder="Parcelamento"
                  styles={purchaseSelectStyles}
                  menuPortalTarget={portalTarget}
                />
              </div>
              <div className="brand-modal-field brand-modal-field--status">
                <button
                  className={`brand-modal-status-toggle${brandModal.is_active ? " is-active" : " is-inactive"}`}
                  type="button"
                  aria-pressed={brandModal.is_active}
                  onClick={() =>
                    setBrandModal((current) => ({
                      ...current,
                      is_active: !current.is_active,
                    }))
                  }
                  title={
                    brandModal.is_active
                      ? "Clique para desativar a marca"
                      : "Clique para ativar a marca"
                  }
                >
                  <CheckIcon />
                  <span>{brandModal.is_active ? "Ativa" : "Inativa"}</span>
                </button>
              </div>
              <label className="brand-modal-field brand-modal-field--notes brand-modal-field--duplicate">
                <input
                  placeholder="Observações"
                  style={{ fontSize: "0.82rem" }}
                  value={brandModal.notes}
                  onChange={(event) =>
                    setBrandModal((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>
            </div>

            {isEditingBrand && (
              <>
                <div className="brand-summary-dashboard">
                  <div className="summary-metric-card">
                    <span>Pedido</span>
                    <strong>{formatPurchaseDisplayAmount(totalPlanned)}</strong>
                  </div>
                  <div className="summary-metric-card">
                    <span>Recebido</span>
                    <strong>
                      {formatPurchaseDisplayAmount(totalReceived)}
                    </strong>
                  </div>
                  <div className="summary-metric-card">
                    <span>Vendido</span>
                    <strong>{formatPurchaseDisplayAmount(totalSold)}</strong>
                  </div>
                  <div className="summary-metric-card">
                    <span>Devolvido</span>
                    <strong
                      style={{
                        color: totalReturns > 0 ? "#ef4444" : "inherit",
                      }}
                    >
                      {formatPurchaseDisplayAmount(totalReturns)}
                    </strong>
                  </div>
                  <div
                    className={`summary-metric-card ${avgProfit >= 0 ? "positive" : "negative"}`}
                  >
                    <span>Margem</span>
                    <strong>{avgProfit}%</strong>
                  </div>
                </div>

                <div className="brand-modal-table-title-row">
                  <span>Coleções & Performance</span>
                  <button
                    className={`table-button icon-button cockpit-btn detail-toggle-btn${brandModalDetailed ? " active" : ""}`}
                    type="button"
                    onClick={() => setBrandModalDetailed(!brandModalDetailed)}
                    title="Alternar Detalhamento Analítico"
                  >
                    <EyeIcon />
                  </button>
                </div>

                <div className="table-shell brand-collection-table-shell">
                  <table className="erp-table brand-collection-table compact-table">
                    <colgroup>
                      <col className="brand-collection-col-name" />
                      <col className="brand-collection-col-pedido" />
                      {brandModalDetailed && (
                        <>
                          <col className="brand-collection-col-detail" />
                          <col className="brand-collection-col-detail" />
                          <col className="brand-collection-col-detail" />
                          <col className="brand-collection-col-detail" />
                          <col className="brand-collection-col-profit" />
                        </>
                      )}
                      <col className="brand-collection-col-note" />
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="brand-collection-col-name">Coleção</th>
                        <th className="numeric-cell brand-collection-col-pedido">
                          Pedido
                        </th>
                        {brandModalDetailed && (
                          <>
                            <th className="numeric-cell brand-collection-col-detail">
                              Recebido
                            </th>
                            <th className="numeric-cell brand-collection-col-detail">
                              Falta receber
                            </th>
                            <th className="numeric-cell brand-collection-col-detail">
                              Devolvido
                            </th>
                            <th className="numeric-cell brand-collection-col-detail">
                              Vendido
                            </th>
                            <th className="numeric-cell brand-collection-col-profit">
                              % Lucro
                            </th>
                          </>
                        )}
                        <th className="centered-cell brand-collection-col-note">
                          <span className="brand-collection-note-header">
                            <span>Obs</span>
                            <button
                              className={`table-button icon-button cockpit-btn detail-toggle-btn${brandModalDetailed ? " active" : ""}`}
                              type="button"
                              onClick={() => setBrandModalDetailed(!brandModalDetailed)}
                              title="Alternar detalhamento analítico"
                            >
                              <EyeIcon />
                            </button>
                          </span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {collectionsChronological.length ? (
                        collectionsChronological
                          .slice()
                          .reverse()
                          .map((collection) => {
                            const collectionSnapshot =
                              currentBrandSnapshot?.collections.get(
                                collection.id,
                              ) ?? null;
                            const isEditable =
                              isCollectionConfirmationEditable(collection);
                            const isConfirmed = getCollectionConfirmedState(
                              collection,
                              collectionSnapshot,
                            );
                            const hasConfirmableOrder =
                              hasCollectionConfirmableOrder(collectionSnapshot);
                            const observationText =
                              getCollectionObservationText(collectionSnapshot);
                            const hasObservation = Boolean(observationText);

                            const profitPercentage = Math.round(
                              calculatePurchaseProfitMargin(
                                collectionSnapshot?.soldAmount || 0,
                                collectionSnapshot?.receivedAmount || 0,
                                collectionSnapshot?.returnsAmount || 0,
                              ),
                            );

                            return (
                              <tr
                                key={`${brandModal.id ?? brandModal.name}-${collection.id}`}
                              >
                                <td>
                                  {collection.season_label || collection.name}
                                </td>
                                 <td className="numeric-cell">
                                  {renderInlinePlannedAmount(currentBrandSnapshot, collection, {
                                    compact: true,
                                    showEditButton: true,
                                    extraActions: isEditable ? (
                                      <button
                                        className={`table-button icon-button cockpit-btn cockpit-btn-confirm${isConfirmed ? " is-confirmed" : ""}`}
                                        type="button"
                                        onClick={() =>
                                          currentBrandSnapshot
                                            ? void handleToggleCollectionConfirmation(
                                                currentBrandSnapshot,
                                                collection,
                                              )
                                            : undefined
                                        }
                                        disabled={
                                          !currentBrandSnapshot ||
                                          !hasConfirmableOrder
                                        }
                                        title={
                                          !hasConfirmableOrder
                                            ? "Cadastre o pedido para confirmar"
                                            : isConfirmed
                                              ? "Confirmado (clique para desfazer)"
                                              : "Planejado (clique para confirmar)"
                                        }
                                        style={{ marginLeft: "2px" }}
                                      >
                                        <ConfirmIcon confirmed={isConfirmed} />
                                      </button>
                                    ) : null
                                  })}
                                </td>
                                {brandModalDetailed && (
                                  <>
                                    <td className="numeric-cell color-recebido">
                                      {formatPurchaseDisplayAmount(
                                        collectionSnapshot?.receivedAmount || 0,
                                      )}
                                    </td>
                                    <td className="numeric-cell color-a-receber">
                                      {formatPurchaseDisplayAmount(
                                        collectionSnapshot?.outstandingAmount ||
                                          0,
                                      )}
                                    </td>
                                    <td className="numeric-cell color-devolucao">
                                      {formatPurchaseDisplayAmount(
                                        collectionSnapshot?.returnsAmount || 0,
                                      )}
                                    </td>
                                    <td className="numeric-cell color-venda">
                                      {formatPurchaseDisplayAmount(
                                        collectionSnapshot?.soldAmount || 0,
                                      )}
                                    </td>
                                    <td
                                      className="numeric-cell"
                                      style={{
                                        color:
                                          profitPercentage >= 0
                                            ? "#10b981"
                                            : "#ef4444",
                                        fontWeight: 600,
                                      }}
                                    >
                                      {profitPercentage}%
                                    </td>
                                  </>
                                )}
                                <td className="centered-cell">
                                  <button
                                    aria-label={`${hasObservation ? "Editar" : "Adicionar"} observação`}
                                    className={`table-button icon-button cockpit-btn collection-observation-button${hasObservation ? " has-observation" : ""}`}
                                    type="button"
                                    onClick={() =>
                                      currentBrandSnapshot
                                        ? openCollectionObservationModal(
                                            currentBrandSnapshot,
                                            collection,
                                          )
                                        : undefined
                                    }
                                    disabled={!currentBrandSnapshot}
                                    title={
                                      observationText || "Adicionar observação"
                                    }
                                  >
                                    <ObservationIcon />
                                  </button>
                                </td>
                              </tr>
                            );
                          })
                      ) : (
                        <tr>
                          <td colSpan={brandModalDetailed ? 8 : 4}>
                            Nenhuma coleção cadastrada.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleSaveBrand()}
            >
              Salvar marca
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={closeBrandModal}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }
  function renderCollectionObservationModal() {
    if (!collectionObservationModal) return null;
    const collection = collectionMap.get(
      collectionObservationModal.collectionId,
    );

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card purchase-collection-note-modal">
          <div className="purchase-panel-heading">
            <h3>Observação da coleção</h3>
            <ModalCloseButton onClick={closeCollectionObservationModal} />
          </div>
          <div className="summary-list purchase-collection-note-summary">
            <div className="summary-row">
              <span>Coleção</span>
              <strong>
                {collection?.season_label || collection?.name || "-"}
              </strong>
            </div>
          </div>
          <div className="full-width">
            <textarea
              className="purchase-collection-note-input"
              value={collectionObservationModal.notes}
              onChange={(event) =>
                setCollectionObservationModal((current) =>
                  current
                    ? {
                        ...current,
                        notes: event.target.value,
                      }
                    : current,
                )
              }
              placeholder="Digite uma observação para esta coleção"
              rows={5}
            />
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleSaveCollectionObservation()}
            >
              Salvar observação
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={closeCollectionObservationModal}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderInactiveBrandsModal() {
    if (!inactiveBrandsModalOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card purchase-inactive-brands-modal-card">
          <div className="purchase-panel-heading">
            <h3>Marcas desativadas</h3>
            <ModalCloseButton
              onClick={() => setInactiveBrandsModalOpen(false)}
            />
          </div>
          <div className="summary-list inactive-brands-summary">
            <div className="summary-row">
              <span>Marcas agrupadas</span>
              <strong>{inactiveBrands.length}</strong>
            </div>
          </div>
          <div className="table-shell">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>Marca</th>
                  <th>Fornecedores</th>
                  <th>Forma de pagamento</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {inactiveBrands.length ? (
                  inactiveBrands.map((brand) => (
                    <tr key={brand.id}>
                      <td>{brand.name}</td>
                      <td>
                        {brand.suppliers
                          .map((supplier) => supplier.name)
                          .join(", ") || "-"}
                      </td>
                      <td>{brand.default_payment_term || "-"}</td>
                      <td>
                        <div className="action-row">
                          <button
                            aria-label={`Editar marca ${brand.name}`}
                            className="table-button icon-button"
                            title="Editar marca"
                            type="button"
                            onClick={() => {
                              setInactiveBrandsModalOpen(false);
                              openBrandModal(brand);
                            }}
                          >
                            <EditIcon />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4}>Nenhuma marca desativada encontrada.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  function renderUnassignedSuppliersModal() {
    if (!unassignedSuppliersModalOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card purchase-inactive-brands-modal-card">
          <div className="purchase-panel-heading">
            <h3>Fornecedores sem marca</h3>
            <ModalCloseButton
              onClick={() => setUnassignedSuppliersModalOpen(false)}
            />
          </div>
          <div className="summary-list inactive-brands-summary">
            <div className="summary-row">
              <span>Fornecedores sem marca</span>
              <strong>{unassignedSuppliers.length}</strong>
            </div>
          </div>
          <div className="purchase-unassigned-toolbar">
            <label>
              Agregar selecionados a marca
              <Select
                options={activeBrandOptions}
                value={
                  activeBrandOptions.find(
                    (option) => option.value === bulkUnassignedBrandId,
                  ) ?? null
                }
                onChange={(option) =>
                  setBulkUnassignedBrandId(asSingleValue(option))
                }
                isClearable
                placeholder="Selecione a marca"
                styles={purchaseSelectStyles}
                menuPortalTarget={portalTarget}
              />
            </label>
            <div className="action-row">
              <button
                className="secondary-button"
                type="button"
                onClick={() => void handleBulkAssignUnassignedSuppliers()}
                disabled={
                  !bulkUnassignedBrandId ||
                  !selectedUnassignedSupplierIds.length
                }
              >
                Vincular selecionados
              </button>
              <button
                className="ghost-button danger-text-action"
                type="button"
                onClick={() => void handleBulkIgnoreUnassignedSuppliers()}
                disabled={!selectedUnassignedSupplierIds.length}
              >
                Desconsiderar selecionados
              </button>
            </div>
          </div>
          <div className="table-shell">
            <table className="erp-table">
              <thead>
                <tr>
                  <th className="centered-cell">Selecionar</th>
                  <th>Fornecedor</th>
                  <th>Agregar a marca</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {unassignedSuppliers.length ? (
                  unassignedSuppliers.map((supplier) => {
                    const selectedBrand =
                      activeBrandOptions.find(
                        (option) =>
                          option.value ===
                          (unassignedSupplierTargets[supplier.id] ?? ""),
                      ) ?? null;
                    return (
                      <tr key={supplier.id}>
                        <td className="centered-cell">
                          <input
                            type="checkbox"
                            checked={selectedUnassignedSupplierIds.includes(
                              supplier.id,
                            )}
                            onChange={() =>
                              toggleUnassignedSupplierSelection(supplier.id)
                            }
                          />
                        </td>
                        <td>{supplier.name}</td>
                        <td style={{ minWidth: 260 }}>
                          <Select
                            options={activeBrandOptions}
                            value={selectedBrand}
                            onChange={(option) =>
                              setUnassignedSupplierTargets((current) => ({
                                ...current,
                                [supplier.id]: asSingleValue(option),
                              }))
                            }
                            isClearable
                            placeholder="Selecione a marca"
                            styles={purchaseSelectStyles}
                            menuPortalTarget={portalTarget}
                          />
                        </td>
                        <td>
                          <div className="action-row">
                            <button
                              className="table-button"
                              type="button"
                              onClick={() =>
                                void handleAssignUnassignedSupplierToBrand(
                                  supplier.id,
                                )
                              }
                              disabled={!unassignedSupplierTargets[supplier.id]}
                            >
                              Vincular
                            </button>
                            <button
                              className="ghost-button danger-text-action"
                              type="button"
                              onClick={() =>
                                void onUpdateSupplier(supplier.id, {
                                  name: supplier.name,
                                  default_payment_term:
                                    supplier.default_payment_term,
                                  notes: supplier.notes,
                                  ignore_in_purchase_planning: true,
                                  is_active: supplier.is_active,
                                })
                              }
                            >
                              Desconsiderar
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={4}>Nenhum fornecedor sem marca encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  function renderSupplierModal() {
    if (!supplierModalOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card">
          <div className="purchase-panel-heading">
            <h3>
              {supplierModal.id ? "Editar fornecedor" : "Novo fornecedor"}
            </h3>
            <ModalCloseButton onClick={() => setSupplierModalOpen(false)} />
          </div>
          <div className="form-grid">
            <label>
              Fornecedor
              <input
                value={supplierModal.name}
                onChange={(event) =>
                  setSupplierModal((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Prazo padrão
              <Select
                options={paymentTermOptions}
                value={selectedSupplierTermOption}
                onChange={(option) =>
                  setSupplierModal((current) => ({
                    ...current,
                    default_payment_term: asSingleValue(option) || "1x",
                  }))
                }
                isClearable
                placeholder="Selecione"
                styles={purchaseSelectStyles}
                menuPortalTarget={portalTarget}
              />
            </label>
            <label className="full-width">
              Observações
              <textarea
                value={supplierModal.notes}
                onChange={(event) =>
                  setSupplierModal((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
            <label className="checkbox-line full-width">
              <input
                type="checkbox"
                checked={supplierModal.is_active}
                onChange={(event) =>
                  setSupplierModal((current) => ({
                    ...current,
                    is_active: event.target.checked,
                  }))
                }
              />
              <span>Fornecedor ativo</span>
            </label>
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleSaveSupplier()}
            >
              Salvar fornecedor
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => setSupplierModalOpen(false)}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderPurchaseReturnModal() {
    if (!purchaseReturnModalOpen) return null;

    return (
      <div
        className="modal-backdrop"
        role="presentation"
        style={{ zIndex: 1200 }}
      >
        <div className="modal-card purchase-modal-card">
          <div className="purchase-panel-heading">
            <h3>
              {purchaseReturnModal.id
                ? "Editar devolução de compra"
                : "Nova devolução de compra"}
            </h3>
            <ModalCloseButton
              onClick={() => {
                setPurchaseReturnModalOpen(false);
                setPurchaseReturnModal(emptyPurchaseReturnModal(today));
              }}
            />
          </div>
          <div className="form-grid">
            <label>
              Data
              <input
                type="date"
                value={purchaseReturnModal.return_date}
                onChange={(event) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    return_date: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Fornecedor
              <Select
                options={supplierOptions}
                value={selectedPurchaseReturnSupplierOption}
                onChange={(option) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    supplier_id: asSingleValue(option),
                  }))
                }
                isClearable
                placeholder="Selecione o fornecedor"
                styles={purchaseSelectStyles}
                menuPortalTarget={portalTarget}
              />
            </label>
            <label>
              Nota fiscal
              <input
                value={purchaseReturnModal.invoice_number}
                onChange={(event) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    invoice_number: event.target.value,
                  }))
                }
                placeholder="Número da nota fiscal"
              />
            </label>
            <label>
              Status
              <select
                value={purchaseReturnModal.status}
                onChange={(event) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    status: event.target.value,
                  }))
                }
              >
                {purchaseReturnStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="full-width">
              Valor
              <MoneyInput
                value={purchaseReturnModal.amount}
                onValueChange={(value) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    amount: value,
                  }))
                }
              />
            </label>
            <label className="full-width">
              Observação
              <textarea
                rows={3}
                value={purchaseReturnModal.notes}
                onChange={(event) =>
                  setPurchaseReturnModal((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleSavePurchaseReturn()}
            >
              Salvar devolução
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => {
                setPurchaseReturnModalOpen(false);
                setPurchaseReturnModal(emptyPurchaseReturnModal(today));
              }}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderPurchaseReturnsPanelModal() {
    if (!purchaseReturnsPanelOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card purchase-returns-panel-modal">
          <div className="purchase-panel-heading">
            <h3>Devoluções de compras</h3>
            <ModalCloseButton
              onClick={() => setPurchaseReturnsPanelOpen(false)}
            />
          </div>
          {renderDevolucoes()}
        </div>
      </div>
    );
  }

  function renderCollectionModal() {
    if (!collectionModalOpen) return null;

    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card purchase-modal-card">
          <div className="purchase-panel-heading">
            <h3>{collectionModal.id ? "Editar coleção" : "Nova coleção"}</h3>
            <ModalCloseButton onClick={() => setCollectionModalOpen(false)} />
          </div>
          <div className="form-grid">
            <label>
              Ano
              <input
                type="number"
                min="2000"
                max="2100"
                value={collectionModal.season_year}
                onChange={(event) =>
                  setCollectionModal((current) => ({
                    ...current,
                    season_year: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Estação
              <Select
                options={SEASON_TYPE_OPTIONS as unknown as SelectOption[]}
                value={
                  selectedCollectionSeasonTypeOption as unknown as SelectOption
                }
                onChange={(option) =>
                  setCollectionModal((current) => ({
                    ...current,
                    season_type: (asSingleValue(option) || "summer") as
                      | "summer"
                      | "winter",
                  }))
                }
                styles={purchaseSelectStyles}
                menuPortalTarget={portalTarget}
              />
            </label>
            <label>
              Inicio
              <input
                type="date"
                value={collectionModal.start_date}
                onChange={(event) =>
                  setCollectionModal((current) => ({
                    ...current,
                    start_date: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              Fim da coleção
              <input
                type="date"
                value={collectionModal.end_date}
                onChange={(event) =>
                  setCollectionModal((current) => ({
                    ...current,
                    end_date: event.target.value,
                  }))
                }
              />
            </label>
            <label className="full-width">
              Observações
              <textarea
                value={collectionModal.notes}
                onChange={(event) =>
                  setCollectionModal((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
            <label className="checkbox-line full-width">
              <input
                type="checkbox"
                checked={collectionModal.is_active}
                onChange={(event) =>
                  setCollectionModal((current) => ({
                    ...current,
                    is_active: event.target.checked,
                  }))
                }
              />
              <span>{`${buildSeasonLabel(collectionModal.season_type, collectionModal.season_year) || "Coleção"} ativa`}</span>
            </label>
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleSaveCollection()}
            >
              Salvar coleção
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => setCollectionModalOpen(false)}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    );
  }

  const content =
    view === "planejamento"
      ? renderPlanejamento()
      : view === "fornecedores"
        ? renderFornecedores()
        : renderResumo();

  return (
    <>
      {content}
      {renderInvoiceModal()}
      {renderBrandModal()}
      {renderCollectionObservationModal()}
      {renderInactiveBrandsModal()}
      {renderUnassignedSuppliersModal()}
      {renderSupplierModal()}
      {renderPurchaseReturnsPanelModal()}
      {renderPurchaseReturnModal()}
      {renderCollectionModal()}
    </>
  );
}

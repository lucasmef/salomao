import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { formatDate, formatEntryStatus, formatMoney } from "../lib/format";
import type { Account, BoletoAlertItem, BoletoClient, BoletoDashboard } from "../types";

type Props = {
  accounts: Account[];
  onCancelInterBoleto: (boletoId: string) => Promise<void>;
  dashboard: BoletoDashboard;
  showAllMonthlyMissingBoletos: boolean;
  submitting: boolean;
  onDownloadInterBoletoPdf: (boletoId: string) => Promise<void>;
  onDownloadInterBoletoPdfBatch: (boletoIds: string[]) => Promise<void>;
  onExportMissingBoletos: (selectionKeys: string[]) => Promise<void>;
  onIssueInterCharges: (selectionKeys: string[]) => Promise<void>;
  onReceiveInterBoleto: (boletoId: string, payWith?: "BOLETO" | "PIX") => Promise<void>;
  onSyncInterCharges: () => Promise<void>;
  onToggleAllMonthlyMissingBoletos: (showAll: boolean) => Promise<void>;
  onUploadReceivables: (file: File) => Promise<void>;
  onUploadBoletoInter: (file: File) => Promise<void>;
  onUploadBoletoC6: (file: File) => Promise<void>;
  onUploadClientData: (file: File) => Promise<void>;
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
type TabId = "resumo" | "clientes" | "faturas";
type InvoiceFilter = "open" | "open-boletos" | "overdue" | "paid-pending" | "missing" | "excess";
type OpenReceivableSort = "due_date" | "client_name" | "document" | "status" | "amount";
type OpenBoletoSort = "due_date" | "issue_date" | "client_name" | "bank" | "amount" | "document_id";
type SortDirection = "asc" | "desc";

const tabItems: Array<{ id: TabId; label: string }> = [
  { id: "resumo", label: "Resumo" },
  { id: "clientes", label: "Clientes" },
  { id: "faturas", label: "Faturas" },
];

const invoiceFilters: Array<{ id: InvoiceFilter; label: string }> = [
  { id: "open", label: "Faturas em aberto" },
  { id: "open-boletos", label: "Boletos em aberto" },
  { id: "overdue", label: "Atrasados" },
  { id: "paid-pending", label: "Pagas sem baixa" },
  { id: "missing", label: "Boletos faltando" },
  { id: "excess", label: "Boletos em excesso" },
];

function renderReceivableDetails(item: BoletoAlertItem) {
  if (!item.receivables.length) {
    return "-";
  }
  return item.receivables
    .slice(0, 3)
    .map((receivable) => `${receivable.invoice_number || "Sem numero"}/${receivable.installment || "-"}`)
    .join(", ");
}

function UploadIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M10 13V4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.75 7.75 10 4.5l3.25 3.25" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 14.5v.75A1.75 1.75 0 0 0 5.75 17h8.5A1.75 1.75 0 0 0 16 15.25v-.75" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
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

function RefreshIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 20 20" fill="none">
      <path d="M14.75 6.25V3.75m0 0h-2.5m2.5 0L12.5 6A5.75 5.75 0 1 0 14 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
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

type UploadCardProps = {
  id: string;
  title: string;
  accept: string;
  selectedFile: File | null;
  submitting: boolean;
  onChange: (file: File | null) => void;
  onSubmit: () => void;
  meta: ReactNode;
};

function UploadCard({ id, title, accept, selectedFile, submitting, onChange, onSubmit, meta }: UploadCardProps) {
  return (
    <div className="compact-import-card billing-import-card">
      <div className="billing-import-header">
        <strong>{title}</strong>
        <button
          className="primary-button icon-button"
          disabled={submitting || !selectedFile}
          onClick={onSubmit}
          title={`Importar ${title}`}
          type="button"
        >
          <UploadIcon />
        </button>
      </div>
      <input
        id={id}
        className="hidden-file-input"
        type="file"
        accept={accept}
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
      <div className="billing-file-picker-row">
        <label className="secondary-button compact-file-trigger" htmlFor={id}>
          Selecionar
        </label>
        {selectedFile ? (
          <span className="compact-file-name" title={selectedFile.name}>
            {selectedFile.name}
          </span>
        ) : null}
      </div>
      <div className="billing-import-meta">
        {meta}
        {selectedFile ? (
          <small className="compact-muted" title={selectedFile.name}>
            Novo arquivo: {selectedFile.name}
          </small>
        ) : null}
      </div>
    </div>
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
  onCancelInterBoleto,
  dashboard,
  showAllMonthlyMissingBoletos,
  submitting,
  onDownloadInterBoletoPdf,
  onDownloadInterBoletoPdfBatch,
  onExportMissingBoletos,
  onIssueInterCharges,
  onReceiveInterBoleto,
  onSyncInterCharges,
  onToggleAllMonthlyMissingBoletos,
  onUploadReceivables,
  onUploadBoletoInter,
  onUploadBoletoC6,
  onUploadClientData,
  onSaveClients,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("resumo");
  const [invoiceFilter, setInvoiceFilter] = useState<InvoiceFilter>("open");
  const [receivablesFile, setReceivablesFile] = useState<File | null>(null);
  const [interFile, setInterFile] = useState<File | null>(null);
  const [c6File, setC6File] = useState<File | null>(null);
  const [customerDataFile, setCustomerDataFile] = useState<File | null>(null);
  const [customerDataModalOpen, setCustomerDataModalOpen] = useState(false);
  const [clients, setClients] = useState<EditableClient[]>([]);
  const [selectedMissingKeys, setSelectedMissingKeys] = useState<string[]>([]);
  const [selectedOpenBoletoIds, setSelectedOpenBoletoIds] = useState<string[]>([]);
  const [openBoletoSearch, setOpenBoletoSearch] = useState("");
  const [openBoletoBankFilter, setOpenBoletoBankFilter] = useState("all");
  const [openReceivableSort, setOpenReceivableSort] = useState<OpenReceivableSort>("due_date");
  const [openReceivableSortDirection, setOpenReceivableSortDirection] = useState<SortDirection>("asc");
  const [openBoletoSort, setOpenBoletoSort] = useState<OpenBoletoSort>("due_date");
  const [openBoletoSortDirection, setOpenBoletoSortDirection] = useState<SortDirection>("asc");

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

  const topClients = useMemo(
    () => [...dashboard.clients].sort((left, right) => Number(right.total_amount) - Number(left.total_amount)).slice(0, 8),
    [dashboard.clients],
  );
  const filesBySource = useMemo(
    () => Object.fromEntries(dashboard.files.map((item) => [item.source_type, item] as const)) as Record<string, BoletoDashboard["files"][number]>,
    [dashboard.files],
  );
  const openReceivables = useMemo(
    () =>
      [...dashboard.receivables]
        .filter((item) => Number(item.corrected_amount || item.amount) > 0)
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
    [dashboard.receivables, openReceivableSort, openReceivableSortDirection],
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

  function renderSortButton(
    label: string,
    sortKey: string,
    currentSort: string,
    direction: SortDirection,
    onClick: () => void,
    numeric = false,
  ) {
    const indicator = currentSort === sortKey ? (direction === "asc" ? "^" : "v") : "";
    return (
      <button className={`table-sort-button ${numeric ? "numeric" : ""}`.trim()} onClick={onClick} type="button">
        <strong>{label}</strong>
        <span>{indicator}</span>
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

  function renderBoletoActions(boletos: BoletoAlertItem["boletos"]) {
    if (!boletos.length) {
      return "-";
    }
    return (
      <div className="billing-boleto-list">
        {boletos.map((boleto) => (
          <div key={boleto.id} className="billing-boleto-chip">
            <span title={boleto.linha_digitavel || boleto.barcode || boleto.document_id}>
              {`${boleto.bank} ${boleto.document_id || boleto.barcode || ""}`.trim()}
            </span>
            {boleto.pdf_available && (
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
            <button className="ghost-button" type="button" onClick={closeCustomerDataModal}>
              Fechar
            </button>
          </div>

          <div className="billing-modal-copy">
            <p>
              Envie o arquivo <strong>etiquetas.txt</strong> para atualizar endereco, numero, complemento, bairro,
              cidade, estado, CEP, CPF/CNPJ, IE e telefones dos clientes.
            </p>
            <p>
              Os campos <strong>usa boleto</strong>, <strong>modo</strong>, <strong>dia</strong> e <strong>cobrar multa/juros</strong> nao sao alterados.
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
            <small className="compact-muted">Esse arquivo sera a base fixa para a proxima etapa de emissao.</small>
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

  function renderInvoicePanel() {
    if (invoiceFilter === "open") {
      return (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Faturas em aberto</h3>
            <span>{openReceivables.length}</span>
          </div>
          <div className="table-shell tall">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>{renderSortButton("Vencimento", "due_date", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("due_date"))}</th>
                  <th>{renderSortButton("Cliente", "client_name", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("client_name"))}</th>
                  <th>{renderSortButton("Titulo", "document", openReceivableSort, openReceivableSortDirection, () => toggleOpenReceivableSort("document"))}</th>
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
                    <td>{item.client_name ?? "-"}</td>
                    <td>{`${item.invoice_number || "Sem numero"}/${item.installment || "-"}`}</td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td className="numeric-cell">{formatMoney(item.corrected_amount || item.amount)}</td>
                  </tr>
                ))}
                {!openReceivables.length && (
                  <tr>
                    <td colSpan={5}>Nenhuma fatura em aberto encontrada.</td>
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
          <div className="table-shell tall">
            <table className="erp-table">
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
          <div className="table-shell tall">
            <table className="erp-table">
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
                    <td>{renderBoletoActions(item.boletos)}</td>
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
          <div className="table-shell tall">
            <table className="erp-table">
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
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
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
                  placeholder="Cliente, documento, linha digitavel..."
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
              <span>{filteredOpenBoletos.length}</span>
            </div>
          </div>
          <div className="table-shell tall">
            <table className="erp-table">
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
                  <th>{renderSortButton("Emissao", "issue_date", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("issue_date"))}</th>
                  <th>{renderSortButton("Vencimento", "due_date", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("due_date"))}</th>
                  <th className="numeric-cell">
                    {renderSortButton("Valor", "amount", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("amount"), true)}
                  </th>
                  <th>Status</th>
                  <th>{renderSortButton("Banco", "bank", openBoletoSort, openBoletoSortDirection, () => toggleOpenBoletoSort("bank"))}</th>
                  <th>Acoes</th>
                </tr>
              </thead>
              <tbody>
                {filteredOpenBoletos.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <input
                        checked={selectedOpenBoletoIds.includes(item.id)}
                        disabled={submitting || !item.pdf_available}
                        onChange={() => toggleOpenBoletoSelection(item.id)}
                        type="checkbox"
                      />
                    </td>
                    <td>{item.client_name}</td>
                    <td>
                      <div className="billing-boleto-main-cell">
                        <strong>{item.document_id}</strong>
                        <small className="compact-muted">{item.linha_digitavel || item.barcode || "-"}</small>
                      </div>
                    </td>
                    <td>{formatDate(item.issue_date)}</td>
                    <td>{formatDate(item.due_date)}</td>
                    <td className="numeric-cell">{formatMoney(item.amount)}</td>
                    <td>{formatEntryStatus(item.status)}</td>
                    <td>{item.bank}</td>
                    <td>
                      <div className="billing-boleto-row-actions">
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
                          <small className="compact-muted">Nao disponivel</small>
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
            <label className="checkbox-line compact-inline">
              <input
                checked={showAllMonthlyMissingBoletos}
                disabled={submitting}
                onChange={(event) => void onToggleAllMonthlyMissingBoletos(event.target.checked)}
                type="checkbox"
              />
              <span>Exibe todos boletos de clientes mensal</span>
            </label>
            <button
              className="primary-button"
              disabled={submitting || !selectedMissingKeys.length}
              onClick={() => void onExportMissingBoletos(selectedMissingKeys)}
              type="button"
            >
              Gerar XLSX
            </button>
            <button
              className="secondary-button"
              disabled={submitting || !selectedMissingKeys.length || !hasInterApiAccount}
              onClick={() => void onIssueInterCharges(selectedMissingKeys)}
              type="button"
            >
              Emitir no Inter
            </button>
            <span>{dashboard.missing_boletos.length}</span>
          </div>
        </div>
        <div className="table-shell tall">
          <table className="erp-table">
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
      <section className="panel compact-tabs-panel">
        <div className="tab-row">
          {tabItems.map((tab) => (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "resumo" && (
        <>
          <section className="content-grid billing-summary-grid">
            <article className="panel-card compact-panel-card billing-summary-panel">
              <div className="panel-title compact-title-row">
                <h3>Importacao rapida</h3>
              </div>
              <div className="compact-import-grid billing-import-grid">
                <UploadCard
                  id="boletos-receivables-file"
                  title="Faturas a receber"
                  accept=".xls,.xlsx,.zip"
                  selectedFile={receivablesFile}
                  submitting={submitting}
                  onChange={setReceivablesFile}
                  onSubmit={() => receivablesFile && void onUploadReceivables(receivablesFile)}
                  meta={renderFileMeta("linx_receivables")}
                />
                <UploadCard
                  id="boletos-inter-file"
                  title="Relatorio Inter"
                  accept=".zip"
                  selectedFile={interFile}
                  submitting={submitting}
                  onChange={setInterFile}
                  onSubmit={() => interFile && void onUploadBoletoInter(interFile)}
                  meta={renderFileMeta("boletos:inter")}
                />
                <UploadCard
                  id="boletos-c6-file"
                  title="Relatorio C6"
                  accept=".csv"
                  selectedFile={c6File}
                  submitting={submitting}
                  onChange={setC6File}
                  onSubmit={() => c6File && void onUploadBoletoC6(c6File)}
                  meta={renderFileMeta("boletos:c6")}
                />
                <div className="compact-import-card billing-import-card">
                  <div className="billing-import-header">
                    <strong>Inter</strong>
                    <button
                      className="primary-button icon-button"
                      disabled={submitting || !hasInterApiAccount}
                      onClick={() => void onSyncInterCharges()}
                      title="Atualizar cobrancas do Inter"
                      type="button"
                    >
                      <RefreshIcon />
                    </button>
                  </div>
                  <div className="billing-import-meta">
                    {renderFileMeta("inter_charge_sync")}
                    {!hasInterApiAccount && (
                      <small className="compact-muted">Cadastre a chave da API do Inter na conta para habilitar.</small>
                    )}
                  </div>
                </div>
              </div>
            </article>
          </section>

          <section className="kpi-grid compact-kpis billing-summary-kpis">
            <article className="kpi-card"><span>Faturas abertas</span><strong>{dashboard.summary.receivable_count}</strong></article>
            <article className="kpi-card"><span>Valor em aberto</span><strong>{formatMoney(dashboard.summary.receivable_total)}</strong></article>
            <article className="kpi-card"><span>Boletos vencidos</span><strong>{dashboard.summary.overdue_boleto_count}</strong></article>
            <article className="kpi-card"><span>Clientes em atraso</span><strong>{dashboard.summary.overdue_invoice_client_count}</strong></article>
            <article className="kpi-card"><span>Pagas sem baixa</span><strong>{dashboard.summary.paid_pending_count}</strong></article>
            <article className="kpi-card"><span>Boletos faltando</span><strong>{dashboard.summary.missing_boleto_count}</strong></article>
            <article className="kpi-card"><span>Boletos em excesso</span><strong>{dashboard.summary.excess_boleto_count}</strong></article>
          </section>

          <section className="content-grid two-columns">
            <article className="panel">
              <div className="panel-title">
                <h3>Maiores clientes por valor em aberto</h3>
              </div>
              <div className="table-shell">
                <table className="erp-table">
                  <thead>
                    <tr>
                      <th>Cliente</th>
                      <th>Faturas</th>
                      <th className="numeric-cell">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topClients.map((client) => (
                      <tr key={client.client_key}>
                        <td><span className="single-line-cell">{client.client_name}</span></td>
                        <td>{client.receivable_count}</td>
                        <td className="numeric-cell">{formatMoney(client.total_amount)}</td>
                      </tr>
                    ))}
                    {!topClients.length && (
                      <tr>
                        <td colSpan={3}>Nenhum cliente encontrado.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel">
              <div className="panel-title">
                <h3>Pendencias principais</h3>
              </div>
              <div className="table-shell">
                <table className="erp-table">
                  <thead>
                    <tr>
                      <th>Indicador</th>
                      <th className="numeric-cell">Quantidade</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr><td>Clientes com boleto</td><td className="numeric-cell">{dashboard.summary.boleto_clients_count}</td></tr>
                    <tr><td>Boletos vencidos</td><td className="numeric-cell">{dashboard.summary.overdue_boleto_count}</td></tr>
                    <tr><td>Pagas sem baixa</td><td className="numeric-cell">{dashboard.summary.paid_pending_count}</td></tr>
                    <tr><td>Boletos faltando</td><td className="numeric-cell">{dashboard.summary.missing_boleto_count}</td></tr>
                    <tr><td>Boletos em excesso</td><td className="numeric-cell">{dashboard.summary.excess_boleto_count}</td></tr>
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        </>
      )}

      {activeTab === "clientes" && (
        <section className="panel compact-panel-card">
          <div className="panel-title compact-title-row">
            <h3>Cadastro de clientes</h3>
            <div className="action-row">
              <button className="secondary-button" disabled={submitting} onClick={() => setCustomerDataModalOpen(true)} type="button">
                Atualizar dados dos clientes
              </button>
              <button className="primary-button" disabled={submitting} onClick={() => void handleSaveClients()} type="button">
                Salvar configuracoes
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
                  <th>Observacoes</th>
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

      {activeTab === "faturas" && (
        <>
          <section className="panel compact-tabs-panel">
            <div className="tab-row">
              {invoiceFilters.map((filter) => (
                <button
                  key={filter.id}
                  className={`tab-button ${invoiceFilter === filter.id ? "active" : ""}`}
                  onClick={() => setInvoiceFilter(filter.id)}
                  type="button"
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </section>

          {renderInvoicePanel()}
        </>
      )}

      {renderCustomerDataModal()}
    </div>
  );
}

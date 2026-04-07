import { useEffect, useMemo, useState } from "react";

import { TablePagination } from "../components/TablePagination";
import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { ImportSummary, LinxOpenReceivableDirectory } from "../types";

type Props = {
  tabs: MainNavChild[];
  directory: LinxOpenReceivableDirectory;
  importSummary: ImportSummary;
  loading: boolean;
  filters: {
    search: string;
  };
  onApplyFilters: (filters: { search: string }) => Promise<void>;
  onChangePage: (page: number) => Promise<void>;
  onChangePageSize: (pageSize: number) => Promise<void>;
  onSyncLinxOpenReceivables: () => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

function installmentLabel(item: LinxOpenReceivableDirectory["items"][number]) {
  if (item.installment_number == null || item.installment_count == null) {
    return "-";
  }
  return `${item.installment_number}/${item.installment_count}`;
}

export function CadastrosOpenReceivablesPage({
  tabs,
  directory,
  importSummary,
  loading,
  filters,
  onApplyFilters,
  onChangePage,
  onChangePageSize,
  onSyncLinxOpenReceivables,
}: Props) {
  const currentTab = tabs.find((item) => item.key === "faturas-receber") ?? tabs[0];
  const latestBatch = useMemo(
    () => latestBatchFor(importSummary, "linx_open_receivables"),
    [importSummary],
  );
  const [searchInput, setSearchInput] = useState(filters.search);
  const totalPages = Math.max(1, Math.ceil(directory.total / directory.page_size));

  useEffect(() => {
    setSearchInput(filters.search);
  }, [filters.search]);

  return (
    <SectionChrome
      sectionLabel="Sistema"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Busca
            <input
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Cliente, documento, identificador..."
              value={searchInput}
            />
          </label>
          <button
            className="ghost-button"
            disabled={loading}
            onClick={() => void onApplyFilters({ search: searchInput })}
            type="button"
          >
            Buscar
          </button>
          <button
            className="primary-button"
            disabled={loading}
            onClick={() => void onSyncLinxOpenReceivables()}
            type="button"
          >
            {loading ? "Atualizando..." : "Atualizar Linx"}
          </button>
        </div>
        <div className="section-toolbar-content">
          <div className="import-last-meta">
            {latestBatch
              ? `Ultima atualizacao Linx: ${formatDate(latestBatch.created_at)}`
              : "Primeira atualizacao Linx vai trazer a base aberta atual; depois, so incrementais."}
          </div>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Total em aberto</span><strong>{directory.summary.total_count}</strong></article>
        <article className="kpi-card"><span>Vencidas</span><strong>{directory.summary.overdue_count}</strong></article>
        <article className="kpi-card"><span>Vencem hoje</span><strong>{directory.summary.due_today_count}</strong></article>
        <article className="kpi-card"><span>Valor total</span><strong>{formatMoney(directory.summary.total_amount)}</strong></article>
      </section>

      <section className="panel">
        <div className="table-shell tall">
          <TablePagination
            loading={loading}
            onPageChange={onChangePage}
            onPageSizeChange={onChangePageSize}
            page={directory.page}
            pageSize={directory.page_size}
            pageSizeOptions={[25, 50, 100, 200]}
            totalItems={directory.total}
            totalPages={totalPages}
          />
          <table className="erp-table">
            <thead>
              <tr>
                <th>Fatura</th>
                <th>Cliente</th>
                <th>Emissao</th>
                <th>Vencimento</th>
                <th>Parcela</th>
                <th>Valor</th>
                <th>Documento</th>
                <th>Identificador</th>
              </tr>
            </thead>
            <tbody>
              {directory.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.linx_code}</td>
                  <td>{item.customer_name}</td>
                  <td>{item.issue_date ? formatDate(item.issue_date) : "-"}</td>
                  <td>{item.due_date ? formatDate(item.due_date) : "-"}</td>
                  <td>{installmentLabel(item)}</td>
                  <td>{item.amount != null ? formatMoney(item.amount) : "-"}</td>
                  <td>
                    {item.document_number
                      ? `${item.document_number}${item.document_series ? ` / ${item.document_series}` : ""}`
                      : "-"}
                  </td>
                  <td>{item.identifier ?? "-"}</td>
                </tr>
              ))}
              {!directory.items.length && (
                <tr>
                  <td className="empty-cell" colSpan={8}>
                    Nenhuma fatura a receber encontrada com os filtros atuais.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </SectionChrome>
  );
}

import { useEffect, useMemo, useState } from "react";

import { TablePagination } from "../components/TablePagination";
import { SectionChrome } from "../components/SectionChrome";
import { findNavChildByKey, type MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { ImportSummary, LinxProductDirectory } from "../types";

type Props = {
  tabs: MainNavChild[];
  directory: LinxProductDirectory;
  importSummary: ImportSummary;
  loading: boolean;
  filters: {
    search: string;
    status: string;
  };
  onApplyFilters: (filters: { search: string; status: string }) => Promise<void>;
  onChangePage: (page: number) => Promise<void>;
  onChangePageSize: (pageSize: number) => Promise<void>;
  onSyncLinxProducts: () => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

export function CadastrosProductsPage({
  tabs,
  directory,
  importSummary,
  loading,
  filters,
  onApplyFilters,
  onChangePage,
  onChangePageSize,
  onSyncLinxProducts,
}: Props) {
  const currentTab = findNavChildByKey(tabs, "produtos") ?? tabs[0];
  const latestBatch = useMemo(() => latestBatchFor(importSummary, "linx_products"), [importSummary]);
  const [searchInput, setSearchInput] = useState(filters.search);
  const [statusInput, setStatusInput] = useState(filters.status);
  const totalPages = Math.max(1, Math.ceil(directory.total / directory.page_size));

  useEffect(() => {
    setSearchInput(filters.search);
    setStatusInput(filters.status);
  }, [filters.search, filters.status]);

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
              placeholder="Descricao, codigo, referencia, fornecedor..."
              value={searchInput}
            />
          </label>
          <label>
            Status
            <select onChange={(event) => setStatusInput(event.target.value)} value={statusInput}>
              <option value="all">Todos</option>
              <option value="active">Ativos</option>
              <option value="inactive">Inativos</option>
            </select>
          </label>
          <button
            className="ghost-button"
            disabled={loading}
            onClick={() => void onApplyFilters({ search: searchInput, status: statusInput })}
            type="button"
          >
            Buscar
          </button>
          <button
            className="primary-button"
            disabled={loading}
            onClick={() => void onSyncLinxProducts()}
            type="button"
          >
            {loading ? "Atualizando..." : "Atualizar Linx"}
          </button>
        </div>
        <div className="section-toolbar-content">
          <div className="import-last-meta">
            {latestBatch
              ? `Ultima atualizacao Linx: ${formatDate(latestBatch.created_at)}`
              : "Primeira atualizacao Linx vai trazer toda a base; depois, so incrementais."}
          </div>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Total na base</span><strong>{directory.summary.total_count}</strong></article>
        <article className="kpi-card"><span>Ativos</span><strong>{directory.summary.active_count}</strong></article>
        <article className="kpi-card"><span>Com fornecedor</span><strong>{directory.summary.with_supplier_count}</strong></article>
        <article className="kpi-card"><span>Com colecao</span><strong>{directory.summary.with_collection_count}</strong></article>
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
                <th>Codigo</th>
                <th>Descricao</th>
                <th>Referencia</th>
                <th>Custo</th>
                <th>Venda</th>
                <th>Saldo</th>
                <th>Fornecedor</th>
                <th>Colecao</th>
                <th>Status</th>
                <th>Atualizado no Linx</th>
              </tr>
            </thead>
            <tbody>
              {directory.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.linx_code}</td>
                  <td>{item.description}</td>
                  <td>{item.reference ?? "-"}</td>
                  <td>{item.price_cost != null ? formatMoney(item.price_cost) : "-"}</td>
                  <td>{item.price_sale != null ? formatMoney(item.price_sale) : "-"}</td>
                  <td>{item.stock_quantity ?? "-"}</td>
                  <td>{item.supplier_name ?? (item.supplier_code != null ? `Fornecedor ${item.supplier_code}` : "-")}</td>
                  <td>{item.collection_name ?? "-"}</td>
                  <td>{item.is_active ? "Ativo" : "Inativo"}</td>
                  <td>{item.linx_updated_at ? formatDate(item.linx_updated_at) : "-"}</td>
                </tr>
              ))}
              {!directory.items.length && (
                <tr>
                  <td className="empty-cell" colSpan={10}>
                    Nenhum produto encontrado com os filtros atuais.
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

import { useEffect, useMemo, useState } from "react";

import { TablePagination } from "../components/TablePagination";
import { SectionChrome } from "../components/SectionChrome";
import { Button } from "../components/ui";
import { findNavChildByKey, type MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { ImportSummary, LinxMovementDirectory } from "../types";

type Props = {
  tabs: MainNavChild[];
  directory: LinxMovementDirectory;
  importSummary: ImportSummary;
  loading: boolean;
  filters: {
    search: string;
    group: string;
    movement_type: string;
  };
  onApplyFilters: (filters: { search: string; group: string; movement_type: string }) => Promise<void>;
  onChangePage: (page: number) => Promise<void>;
  onChangePageSize: (pageSize: number) => Promise<void>;
  onSyncLinxMovements: () => Promise<void>;
  onFullRefreshLinxMovements: () => Promise<void>;
};

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

function movementTypeLabel(value: string) {
  switch (value) {
    case "sale":
      return "Venda";
    case "sale_return":
      return "Devolução venda";
    case "purchase":
      return "Compra";
    case "purchase_return":
      return "Devolução compra";
    case "purchase_return_reversal":
      return "Estorno devolução compra";
    default:
      return value;
  }
}

export function CadastrosMovementsPage({
  tabs,
  directory,
  importSummary,
  loading,
  filters,
  onApplyFilters,
  onChangePage,
  onChangePageSize,
  onSyncLinxMovements,
  onFullRefreshLinxMovements,
}: Props) {
  const currentTab = findNavChildByKey(tabs, "movimentos") ?? tabs[0];
  const latestBatch = useMemo(() => latestBatchFor(importSummary, "linx_movements"), [importSummary]);
  const [searchInput, setSearchInput] = useState(filters.search);
  const [groupInput, setGroupInput] = useState(filters.group);
  const [typeInput, setTypeInput] = useState(filters.movement_type);
  const totalPages = Math.max(1, Math.ceil(directory.total / directory.page_size));

  useEffect(() => {
    setSearchInput(filters.search);
    setGroupInput(filters.group);
    setTypeInput(filters.movement_type);
  }, [filters.group, filters.movement_type, filters.search]);

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
              placeholder="Produto, documento, identificador, coleção..."
              value={searchInput}
            />
          </label>
          <label>
            Grupo
            <select onChange={(event) => setGroupInput(event.target.value)} value={groupInput}>
              <option value="all">Todos</option>
              <option value="sale">Vendas</option>
              <option value="purchase">Compras</option>
            </select>
          </label>
          <label>
            Tipo
            <select onChange={(event) => setTypeInput(event.target.value)} value={typeInput}>
              <option value="all">Todos</option>
              <option value="sale">Venda</option>
              <option value="sale_return">Devolução de venda</option>
              <option value="purchase">Compra</option>
              <option value="purchase_return">Devolução de compra</option>
              <option value="purchase_return_reversal">Estorno de devolução de compra</option>
            </select>
          </label>
          <Button
            type="button"
            variant="ghost"
            disabled={loading}
            onClick={() => void onApplyFilters({ search: searchInput, group: groupInput, movement_type: typeInput })}
          >
            Buscar
          </Button>
          <Button
            type="button"
            variant="primary"
            loading={loading}
            disabled={loading}
            onClick={() => void onSyncLinxMovements()}
          >
            {loading ? "Atualizando..." : "Atualizar Linx"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={loading}
            title="Recria a base local de movimentos Linx desde 2020"
            onClick={() => void onFullRefreshLinxMovements()}
          >
            Recriar base Linx
          </Button>
        </div>
        <div className="section-toolbar-content">
          <div className="import-last-meta">
            {latestBatch
              ? `Ultima atualizacao Linx: ${formatDate(latestBatch.created_at)}`
              : "Primeira atualizacao Linx vai trazer a base configurada; depois, so incrementais."}
          </div>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card">
          <span>Vendas</span>
          <strong>{formatMoney(directory.summary.sales_total_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Devoluções venda</span>
          <strong>{formatMoney(directory.summary.sales_return_total_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Compras</span>
          <strong>{formatMoney(directory.summary.purchases_total_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Devoluções compra brutas</span>
          <strong>{formatMoney(directory.summary.purchase_returns_total_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Estornos devolução</span>
          <strong>{formatMoney(directory.summary.purchase_return_reversals_total_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Devoluções compra líquidas</span>
          <strong>{formatMoney(directory.summary.purchase_returns_net_amount)}</strong>
        </article>
      </section>

      <section className="panel">
        <div className="table-shell tall table-shell--mobile-compact">
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
          <table className="erp-table mobile-compact-table">
            <thead>
              <tr>
                <th>Lançamento</th>
                <th>Tipo</th>
                <th>Documento</th>
                <th>Produto</th>
                <th>Coleção</th>
                <th>Quantidade</th>
                <th>Vlr. unit.</th>
                <th>Vlr. total</th>
                <th>Custo</th>
                <th>Natureza</th>
                <th>Data lançamento</th>
              </tr>
            </thead>
            <tbody>
              {directory.items.map((item) => (
                <tr key={item.id}>
                  <td className="mobile-compact-hidden" data-label="Lancamento">{item.linx_transaction}</td>
                  <td className="mobile-compact-hidden" data-label="Tipo">{movementTypeLabel(item.movement_type)}</td>
                  <td data-label="Documento">{item.document_number ?? "-"}</td>
                  <td className="mobile-compact-primary" data-label="Produto">
                    {item.product_description ?? (item.product_code != null ? `Produto ${item.product_code}` : "-")}
                  </td>
                  <td className="mobile-compact-hidden" data-label="Colecao">{item.collection_name ?? "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Quantidade">{item.quantity ?? "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Vlr. unit.">{item.unit_price != null ? formatMoney(item.unit_price) : "-"}</td>
                  <td className="mobile-compact-amount" data-label="Vlr. total">{item.total_amount != null ? formatMoney(item.total_amount) : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Custo">{item.cost_price != null ? formatMoney(item.cost_price) : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Natureza">{item.nature_description ?? item.nature_code ?? "-"}</td>
                  <td data-label="Data">{item.launch_date ? formatDate(item.launch_date) : "-"}</td>
                </tr>
              ))}
              {!directory.items.length && (
                <tr>
                  <td className="empty-cell" colSpan={11}>
                    Nenhum movimento encontrado com os filtros atuais.
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

import { useEffect, useState } from "react";

import { TablePagination } from "../components/TablePagination";
import { Button } from "../components/ui";
import { formatDate, formatMoney } from "../lib/format";
import type { LinxSalesReport } from "../types";

type Props = {
  report: LinxSalesReport;
  filters: {
    search: string;
    start: string;
    end: string;
    page: number;
    page_size: number;
  };
  loading: boolean;
  onApplyFilters: (filters: { search: string; start: string; end: string }) => Promise<void>;
  onChangePage: (page: number) => Promise<void>;
  onChangePageSize: (pageSize: number) => Promise<void>;
};

export function SalesReportPage({
  report,
  filters,
  loading,
  onApplyFilters,
  onChangePage,
  onChangePageSize,
}: Props) {
  const [search, setSearch] = useState(filters.search);
  const [start, setStart] = useState(filters.start);
  const [end, setEnd] = useState(filters.end);
  const totalPages = Math.max(1, Math.ceil(report.total / report.page_size));

  useEffect(() => {
    setSearch(filters.search);
    setStart(filters.start);
    setEnd(filters.end);
  }, [filters.end, filters.search, filters.start]);

  return (
    <>
      <section className="section-toolbar-panel">
        <div className="section-toolbar-content compact-filter-layout">
          <label>
            Início
            <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
          </label>
          <label>
            Fim
            <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
          </label>
          <label>
            Cliente ou nota
            <input
              placeholder="Cliente, código ou documento"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <Button
            type="button"
            variant="primary"
            loading={loading}
            onClick={() => void onApplyFilters({ search, start, end })}
          >
            Buscar
          </Button>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card">
          <span>Notas</span>
          <strong>{report.summary.total_invoices}</strong>
        </article>
        <article className="kpi-card">
          <span>Venda bruta</span>
          <strong>{formatMoney(report.summary.gross_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Devoluções</span>
          <strong>{formatMoney(report.summary.returns_amount)}</strong>
        </article>
        <article className="kpi-card">
          <span>Venda líquida</span>
          <strong>{formatMoney(report.summary.net_amount)}</strong>
        </article>
      </section>

      <section className="panel">
        <div className="table-shell tall">
          <TablePagination
            loading={loading}
            onPageChange={onChangePage}
            onPageSizeChange={onChangePageSize}
            page={report.page}
            pageSize={report.page_size}
            pageSizeOptions={[25, 50, 100, 200]}
            totalItems={report.total}
            totalPages={totalPages}
          />
          <table className="erp-table">
            <thead>
              <tr>
                <th>Nota</th>
                <th>Cliente</th>
                <th>Emissão</th>
                <th>Lançamento</th>
                <th>Itens</th>
                <th>Qtd.</th>
                <th>Venda bruta</th>
                <th>Devoluções</th>
                <th>Venda líquida</th>
              </tr>
            </thead>
            <tbody>
              {report.items.map((item) => (
                <tr key={item.key}>
                  <td>{[item.document_number, item.document_series].filter(Boolean).join(" / ") || "-"}</td>
                  <td>{item.customer_name ?? (item.customer_code ? `Cliente ${item.customer_code}` : "-")}</td>
                  <td>{item.issue_date ? formatDate(item.issue_date) : "-"}</td>
                  <td>{item.launch_date ? formatDate(item.launch_date) : "-"}</td>
                  <td>{item.item_count}</td>
                  <td>{item.quantity}</td>
                  <td>{formatMoney(item.gross_amount)}</td>
                  <td>{formatMoney(item.returns_amount)}</td>
                  <td>{formatMoney(item.net_amount)}</td>
                </tr>
              ))}
              {!report.items.length && (
                <tr>
                  <td className="empty-cell" colSpan={9}>
                    Nenhuma venda encontrada com os filtros atuais.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

type PageSizeOption = number | { value: number; label: string };

type Props = {
  page: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions?: PageSizeOption[];
  totalItems?: number;
  loading?: boolean;
  onPageChange: (page: number) => void | Promise<void>;
  onPageSizeChange?: (pageSize: number) => void | Promise<void>;
};

export function TablePagination({
  page,
  totalPages,
  pageSize,
  pageSizeOptions = [25, 50, 100],
  totalItems,
  loading = false,
  onPageChange,
  onPageSizeChange,
}: Props) {
  const hasPrevious = page > 1 && !loading;
  const hasNext = page < totalPages && !loading;
  const firstItem = typeof totalItems === "number" && totalItems > 0 ? (page - 1) * pageSize + 1 : 0;
  const lastItem = typeof totalItems === "number" ? Math.min(page * pageSize, totalItems) : 0;

  return (
    <div className="table-pagination">
      <div className="table-pagination-meta">
        {typeof totalItems === "number" ? (
          <span>
            {firstItem}-{lastItem} de {totalItems} registros
          </span>
        ) : null}
      </div>
      <div className="table-pagination-actions">
        {onPageSizeChange ? (
          <label className="pagination-size">
            <span>Linhas</span>
            <select
              value={String(pageSize)}
              onChange={(event) => void onPageSizeChange(Number(event.target.value))}
            >
              {pageSizeOptions.map((option) => (
                <option
                  key={typeof option === "number" ? option : `${option.value}-${option.label}`}
                  value={typeof option === "number" ? option : option.value}
                >
                  {typeof option === "number" ? option : option.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button
          aria-label="Primeira pagina"
          className="table-button table-pagination-nav-button"
          disabled={!hasPrevious}
          onClick={() => void onPageChange(1)}
          type="button"
        >
          «
        </button>
        <button
          aria-label="Pagina anterior"
          className="table-button table-pagination-nav-button"
          disabled={!hasPrevious}
          onClick={() => void onPageChange(page - 1)}
          type="button"
        >
          ‹
        </button>
        <span className="table-pagination-page">
          <strong>{page}</strong>
          <span>de {totalPages}</span>
        </span>
        <button
          aria-label="Proxima pagina"
          className="table-button table-pagination-nav-button"
          disabled={!hasNext}
          onClick={() => void onPageChange(page + 1)}
          type="button"
        >
          ›
        </button>
        <button
          aria-label="Ultima pagina"
          className="table-button table-pagination-nav-button"
          disabled={!hasNext}
          onClick={() => void onPageChange(totalPages)}
          type="button"
        >
          »
        </button>
      </div>
    </div>
  );
}

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
  return (
    <div className="table-pagination">
      <div className="table-pagination-meta">
        {typeof totalItems === "number" ? <span>{totalItems} registro(s)</span> : null}
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
          className="table-button"
          disabled={page <= 1 || loading}
          onClick={() => void onPageChange(page - 1)}
          type="button"
        >
          Anterior
        </button>
        <span>
          Pagina {page} de {totalPages}
        </span>
        <button
          className="table-button"
          disabled={page >= totalPages || loading}
          onClick={() => void onPageChange(page + 1)}
          type="button"
        >
          Proxima
        </button>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";

import { formatMoney } from "../lib/format";
import type { LinxProductListItem, LinxProductSearchResult } from "../types";
import { ModalCloseButton } from "./ModalCloseButton";
import { Button } from "./ui";

type Props = {
  open: boolean;
  loading: boolean;
  searchInput: string;
  result: LinxProductSearchResult;
  onChangeSearchInput: (value: string) => void;
  onClose: () => void;
  onSearch: (query: string) => Promise<void>;
};

type ProductTableColumnKey =
  | "linx_code"
  | "description"
  | "reference"
  | "brand_name"
  | "collection_name"
  | "stock_quantity"
  | "price_sale";
type ProductTableSortState = {
  key: ProductTableColumnKey;
  direction: "asc" | "desc";
} | null;
type ProductFilterOption = {
  key: string;
  label: string;
};

const STOCK_FILTER_OPTIONS: ProductFilterOption[] = [
  { key: "positive", label: "Com saldo" },
  { key: "zero", label: "Saldo zero" },
];

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
      <path
        d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z"
        fill="currentColor"
      />
    </svg>
  );
}

function SortDirectionIcon({ direction }: { direction: "asc" | "desc" | null }) {
  if (direction === "asc") {
    return (
      <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
        <path d="M8 12V4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        <path d="m4.75 7.25 3.25-3.25 3.25 3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  if (direction === "desc") {
    return (
      <svg aria-hidden="true" className="button-icon" viewBox="0 0 16 16">
        <path d="M8 4v8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        <path d="m4.75 8.75 3.25 3.25 3.25-3.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return null;
}

function parseProductNumber(value: string | null) {
  const parsed = Number(value ?? "0");
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatStockQuantity(value: string | null) {
  if (value == null || value === "") {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 0,
  }).format(Math.trunc(parseProductNumber(value)));
}

function getBrandFilterKey(item: LinxProductListItem) {
  return item.brand_name?.trim() || "Sem marca";
}

function getProductSortValue(item: LinxProductListItem, key: ProductTableColumnKey) {
  switch (key) {
    case "linx_code":
      return item.linx_code;
    case "reference":
      return item.reference ?? "";
    case "brand_name":
      return item.brand_name ?? "";
    case "collection_name":
      return item.collection_name ?? "";
    case "stock_quantity":
      return parseProductNumber(item.stock_quantity);
    case "price_sale":
      return parseProductNumber(item.price_sale);
    case "description":
    default:
      return item.description ?? "";
  }
}

function getProductStockFilterKey(item: LinxProductListItem) {
  return parseProductNumber(item.stock_quantity) > 0 ? "positive" : "zero";
}

function compareValues(left: string | number, right: string | number) {
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left).localeCompare(String(right), "pt-BR", {
    numeric: true,
    sensitivity: "base",
  });
}

export function GlobalProductSearchModal({
  open,
  loading,
  searchInput,
  result,
  onChangeSearchInput,
  onClose,
  onSearch,
}: Props) {
  const brandFilterPopoverRef = useRef<HTMLDivElement | null>(null);
  const stockFilterPopoverRef = useRef<HTMLDivElement | null>(null);
  const selectAllBrandsRef = useRef<HTMLInputElement | null>(null);
  const selectAllStockRef = useRef<HTMLInputElement | null>(null);
  const [tableSort, setTableSort] = useState<ProductTableSortState>(null);
  const [showBrandFilter, setShowBrandFilter] = useState(false);
  const [showStockFilter, setShowStockFilter] = useState(false);
  const [excludedBrandKeys, setExcludedBrandKeys] = useState<string[]>([]);
  const [selectedStockKeys, setSelectedStockKeys] = useState<string[]>(["positive"]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const trimmedInput = searchInput.trim();
    if (trimmedInput.length < 2 || trimmedInput === result.query.trim()) {
      return;
    }
    const timer = window.setTimeout(() => {
      void onSearch(trimmedInput);
    }, 420);
    return () => window.clearTimeout(timer);
  }, [onSearch, open, result.query, searchInput]);

  useEffect(() => {
    setTableSort(null);
    setExcludedBrandKeys([]);
    setSelectedStockKeys(["positive"]);
    setShowBrandFilter(false);
    setShowStockFilter(false);
  }, [result.query]);

  useEffect(() => {
    if (!showBrandFilter && !showStockFilter) {
      return undefined;
    }

    function handleClickOutside(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (showBrandFilter && brandFilterPopoverRef.current && !brandFilterPopoverRef.current.contains(target)) {
        setShowBrandFilter(false);
      }
      if (showStockFilter && stockFilterPopoverRef.current && !stockFilterPopoverRef.current.contains(target)) {
        setShowStockFilter(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showBrandFilter, showStockFilter]);

  const canSearch = searchInput.trim().length >= 2;
  const brandFilterOptions = useMemo(() => {
    const options = new Map<string, ProductFilterOption>();
    result.items.forEach((item) => {
      const key = getBrandFilterKey(item);
      if (!options.has(key)) {
        options.set(key, { key, label: key });
      }
    });
    return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label, "pt-BR"));
  }, [result.items]);
  const allBrandKeys = useMemo(() => brandFilterOptions.map((option) => option.key), [brandFilterOptions]);
  const allStockKeys = useMemo(() => STOCK_FILTER_OPTIONS.map((option) => option.key), []);
  const allBrandsSelected = excludedBrandKeys.length === 0;
  const someBrandsSelected = excludedBrandKeys.length > 0 && excludedBrandKeys.length < allBrandKeys.length;
  const allStockSelected = selectedStockKeys.length === allStockKeys.length;
  const someStockSelected = selectedStockKeys.length > 0 && selectedStockKeys.length < allStockKeys.length;

  useEffect(() => {
    setExcludedBrandKeys((current) => current.filter((key) => allBrandKeys.includes(key)));
  }, [allBrandKeys]);

  useEffect(() => {
    setSelectedStockKeys((current) => {
      const nextKeys = current.filter((key) => allStockKeys.includes(key));
      return nextKeys.length ? nextKeys : ["positive"];
    });
  }, [allStockKeys]);

  useEffect(() => {
    if (selectAllBrandsRef.current) {
      selectAllBrandsRef.current.indeterminate = someBrandsSelected;
    }
  }, [someBrandsSelected]);

  useEffect(() => {
    if (selectAllStockRef.current) {
      selectAllStockRef.current.indeterminate = someStockSelected;
    }
  }, [someStockSelected]);

  const visibleItems = useMemo(() => {
    const nextItems = result.items
      .filter((item) => !excludedBrandKeys.includes(getBrandFilterKey(item)))
      .filter((item) => selectedStockKeys.includes(getProductStockFilterKey(item)));

    if (!tableSort) {
      return nextItems;
    }

    nextItems.sort((left, right) => {
      const comparison = compareValues(
        getProductSortValue(left, tableSort.key),
        getProductSortValue(right, tableSort.key),
      );
      return tableSort.direction === "asc" ? comparison : -comparison;
    });

    return nextItems;
  }, [excludedBrandKeys, result.items, selectedStockKeys, tableSort]);

  if (!open) {
    return null;
  }

  function handleImmediateSearch() {
    if (!canSearch) {
      return;
    }
    void onSearch(searchInput.trim());
  }

  function toggleTableSort(column: ProductTableColumnKey) {
    setTableSort((current) => {
      if (!current || current.key !== column) {
        return { key: column, direction: "asc" };
      }
      if (current.direction === "asc") {
        return { key: column, direction: "desc" };
      }
      return null;
    });
  }

  function toggleAllBrandFilters(checked: boolean) {
    setExcludedBrandKeys(checked ? [] : allBrandKeys);
  }

  function toggleBrandFilterOption(brandKey: string) {
    setExcludedBrandKeys((current) =>
      current.includes(brandKey) ? current.filter((item) => item !== brandKey) : [...current, brandKey],
    );
  }

  function toggleAllStockFilters(checked: boolean) {
    setSelectedStockKeys(checked ? allStockKeys : []);
  }

  function toggleStockFilterOption(stockKey: string) {
    setSelectedStockKeys((current) =>
      current.includes(stockKey) ? current.filter((item) => item !== stockKey) : [...current, stockKey],
    );
  }

  function renderTableHeader(
    label: string,
    column: ProductTableColumnKey,
    options?: {
      numeric?: boolean;
      filter?: "brand" | "stock";
    },
  ) {
    const numeric = options?.numeric ?? false;
    const sortDirection = tableSort?.key === column ? tableSort.direction : null;
    const isBrandFilter = options?.filter === "brand";
    const isStockFilter = options?.filter === "stock";
    const isFilterActive = isBrandFilter ? excludedBrandKeys.length > 0 : isStockFilter ? selectedStockKeys.length < allStockKeys.length : false;

    return (
      <div
        className={`entries-table-header global-product-search-table-header ${numeric ? "is-numeric" : ""}`.trim()}
        ref={isBrandFilter && showBrandFilter ? brandFilterPopoverRef : isStockFilter && showStockFilter ? stockFilterPopoverRef : null}
      >
        <button
          className={`table-sort-button ${numeric ? "numeric" : ""}`.trim()}
          onClick={() => toggleTableSort(column)}
          type="button"
        >
          <strong>{label}</strong>
          {sortDirection ? (
            <span className="table-sort-indicator is-active">
              <SortDirectionIcon direction={sortDirection} />
            </span>
          ) : null}
        </button>

        {isBrandFilter ? (
          <>
            <button
              aria-expanded={showBrandFilter}
              aria-label="Filtrar marca"
              className={`entries-column-filter-trigger ${isFilterActive ? "is-active" : ""}`.trim()}
              onClick={() => {
                setShowBrandFilter((current) => !current);
                setShowStockFilter(false);
              }}
              title={isFilterActive ? "Marca filtrada" : "Filtrar marca"}
              type="button"
            >
              <FilterFunnelIcon />
            </button>
            {showBrandFilter ? (
              <div className="entries-floating-panel entries-column-filter-popover global-product-search-filter-popover">
                <div className="entries-category-filter-head">
                  <label className="entries-category-filter-option is-all">
                    <input
                      checked={allBrandsSelected}
                      onChange={(event) => toggleAllBrandFilters(event.target.checked)}
                      ref={selectAllBrandsRef}
                      type="checkbox"
                    />
                    <span>Selecionar tudo</span>
                  </label>
                </div>
                <div className="entries-category-filter-list">
                  {brandFilterOptions.length ? (
                    brandFilterOptions.map((option) => (
                      <label className="entries-category-filter-option" key={option.key}>
                        <input
                          checked={!excludedBrandKeys.includes(option.key)}
                          onChange={() => toggleBrandFilterOption(option.key)}
                          type="checkbox"
                        />
                        <span title={option.label}>{option.label}</span>
                      </label>
                    ))
                  ) : (
                    <p className="entries-category-filter-empty">Nenhuma marca encontrada nesta busca.</p>
                  )}
                </div>
                <div className="entries-column-filter-popover-actions">
                  <Button variant="secondary" className="compact-button" onClick={() => toggleAllBrandFilters(true)} type="button">
                    Restaurar
                  </Button>
                  <Button variant="ghost" className="compact" onClick={() => setShowBrandFilter(false)} type="button">
                    Fechar
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}

        {isStockFilter ? (
          <>
            <button
              aria-expanded={showStockFilter}
              aria-label="Filtrar saldo"
              className={`entries-column-filter-trigger ${isFilterActive ? "is-active" : ""}`.trim()}
              onClick={() => {
                setShowStockFilter((current) => !current);
                setShowBrandFilter(false);
              }}
              title={isFilterActive ? "Saldo filtrado" : "Filtrar saldo"}
              type="button"
            >
              <FilterFunnelIcon />
            </button>
            {showStockFilter ? (
              <div className="entries-floating-panel entries-column-filter-popover global-product-search-filter-popover">
                <div className="entries-category-filter-head">
                  <label className="entries-category-filter-option is-all">
                    <input
                      checked={allStockSelected}
                      onChange={(event) => toggleAllStockFilters(event.target.checked)}
                      ref={selectAllStockRef}
                      type="checkbox"
                    />
                    <span>Selecionar tudo</span>
                  </label>
                </div>
                <div className="entries-category-filter-list">
                  {STOCK_FILTER_OPTIONS.map((option) => (
                    <label className="entries-category-filter-option" key={option.key}>
                      <input
                        checked={selectedStockKeys.includes(option.key)}
                        onChange={() => toggleStockFilterOption(option.key)}
                        type="checkbox"
                      />
                      <span title={option.label}>{option.label}</span>
                    </label>
                  ))}
                </div>
                <div className="entries-column-filter-popover-actions">
                  <Button variant="secondary" className="compact-button" onClick={() => setSelectedStockKeys(["positive"])} type="button">
                    So com saldo
                  </Button>
                  <Button variant="ghost" className="compact" onClick={() => setShowStockFilter(false)} type="button">
                    Fechar
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card global-product-search-modal">
        <div className="global-product-search-toolbar">
          <input
            autoFocus
            onChange={(event) => onChangeSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleImmediateSearch();
              }
            }}
            placeholder="Buscar produto"
            value={searchInput}
          />
          <span className="global-product-search-count">
            {loading ? "Buscando..." : `${visibleItems.length} item(ns)`}
          </span>
          <ModalCloseButton onClick={onClose} />
        </div>

        <div className="table-shell global-product-search-table-shell">
          <table className="erp-table entries-list-table global-product-search-table">
            <colgroup>
              <col className="global-product-col-code" />
              <col className="global-product-col-description" />
              <col className="global-product-col-reference" />
              <col className="global-product-col-brand" />
              <col className="global-product-col-collection" />
              <col className="global-product-col-stock" />
              <col className="global-product-col-price" />
            </colgroup>
            <thead>
              <tr>
                <th>{renderTableHeader("Codigo", "linx_code")}</th>
                <th>{renderTableHeader("Descricao", "description")}</th>
                <th>{renderTableHeader("Referencia", "reference")}</th>
                <th>{renderTableHeader("Marca", "brand_name", { filter: "brand" })}</th>
                <th>{renderTableHeader("Colecao", "collection_name")}</th>
                <th className="numeric-cell">{renderTableHeader("Saldo", "stock_quantity", { filter: "stock", numeric: true })}</th>
                <th className="numeric-cell">{renderTableHeader("Venda", "price_sale", { numeric: true })}</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => (
                <tr key={item.id}>
                  <td>{item.linx_code}</td>
                  <td className="global-product-cell-description" title={item.description}>
                    {item.description}
                  </td>
                  <td className="global-product-cell-reference" title={item.reference ?? "-"}>
                    {item.reference ?? "-"}
                  </td>
                  <td className="global-product-cell-brand" title={item.brand_name ?? "Sem marca"}>
                    {item.brand_name ?? "Sem marca"}
                  </td>
                  <td className="global-product-cell-collection" title={item.collection_name ?? "-"}>
                    {item.collection_name ?? "-"}
                  </td>
                  <td className="numeric-cell">{formatStockQuantity(item.stock_quantity)}</td>
                  <td className="numeric-cell">{item.price_sale != null ? formatMoney(item.price_sale) : "-"}</td>
                </tr>
              ))}
              {!visibleItems.length && (
                <tr>
                  <td className="empty-cell" colSpan={7}>
                    {loading
                      ? "Buscando produtos..."
                      : canSearch
                        ? "Nenhum produto encontrado para esta busca."
                        : "Digite ao menos 2 caracteres para buscar."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

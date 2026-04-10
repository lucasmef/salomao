import { useEffect } from "react";

import { formatMoney } from "../lib/format";
import type { LinxProductSearchResult } from "../types";

type Props = {
  open: boolean;
  loading: boolean;
  searchInput: string;
  result: LinxProductSearchResult;
  onChangeSearchInput: (value: string) => void;
  onClose: () => void;
  onSearch: (query: string) => Promise<void>;
};

export function GlobalProductSearchModal({
  open,
  loading,
  searchInput,
  result,
  onChangeSearchInput,
  onClose,
  onSearch,
}: Props) {
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
    }, 220);
    return () => window.clearTimeout(timer);
  }, [onSearch, open, result.query, searchInput]);

  if (!open) {
    return null;
  }

  const canSearch = searchInput.trim().length >= 2;

  function handleImmediateSearch() {
    if (!canSearch) {
      return;
    }
    void onSearch(searchInput.trim());
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card global-product-search-modal">
        <div className="global-product-search-header">
          <div>
            <h3>Busca de produtos</h3>
            <p>Pesquise por descrição, marca, referência, coleção, código ou combinações como "Mari Lafort 38".</p>
          </div>
          <button className="ghost-button" onClick={onClose} type="button">
            Fechar
          </button>
        </div>

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
            placeholder='Ex.: calça 38, Mari preta 38 ou Mari Lafort 38'
            value={searchInput}
          />
          <button className="primary-button" disabled={!canSearch || loading} onClick={handleImmediateSearch} type="button">
            {loading ? "Buscando..." : "Buscar"}
          </button>
        </div>

        <div className="modal-summary global-product-search-summary">
          <strong>{result.total} resultado(s)</strong>
          <span>{result.query ? `Busca atual: ${result.query}` : "Digite pelo menos 2 caracteres."}</span>
        </div>

        <div className="table-shell">
          <table className="erp-table global-product-search-table">
            <thead>
              <tr>
                <th>Codigo</th>
                <th>Descricao</th>
                <th>Referencia</th>
                <th>Marca</th>
                <th>Colecao</th>
                <th className="numeric-cell">Saldo em estoque</th>
                <th className="numeric-cell">Preco de venda</th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.linx_code}</td>
                  <td>{item.description}</td>
                  <td>{item.reference ?? "-"}</td>
                  <td>{item.brand_name ?? "-"}</td>
                  <td>{item.collection_name ?? "-"}</td>
                  <td className="numeric-cell">{item.stock_quantity ?? "-"}</td>
                  <td className="numeric-cell">{item.price_sale != null ? formatMoney(item.price_sale) : "-"}</td>
                </tr>
              ))}
              {!result.items.length && (
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

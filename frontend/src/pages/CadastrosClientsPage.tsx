import { useMemo, useState } from "react";

import { SectionChrome } from "../components/SectionChrome";
import { Button } from "../components/ui";
import { findNavChildByKey, type MainNavChild } from "../data/navigation";
import { formatDate, normalizeDisplayText } from "../lib/format";
import type { ImportSummary, LinxCustomerDirectory } from "../types";

type Props = {
  tabs: MainNavChild[];
  directory: LinxCustomerDirectory;
  importSummary: ImportSummary;
  loading: boolean;
  onSyncLinxCustomers: () => Promise<void>;
};

type TypeFilter = "all" | "client" | "supplier";
type BoletoFilter = "all" | "yes" | "no";

function latestBatchFor(importSummary: ImportSummary, sourceType: string) {
  return importSummary.import_batches.find((batch) => batch.source_type === sourceType) ?? null;
}

function normalizeSearchValue(value: string) {
  return normalizeDisplayText(value).trim().toLowerCase();
}

function displayMode(value: string) {
  const normalized = normalizeDisplayText(value).trim().toLowerCase();
  if (normalized === "mensal") {
    return "Mensal";
  }
  if (normalized === "individual") {
    return "Individual";
  }
  return value || "-";
}

export function CadastrosClientsPage({
  tabs,
  directory,
  importSummary,
  loading,
  onSyncLinxCustomers,
}: Props) {
  const currentTab = findNavChildByKey(tabs, "clientes") ?? tabs[0];
  const latestBatch = useMemo(() => latestBatchFor(importSummary, "linx_customers"), [importSummary]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [boletoFilter, setBoletoFilter] = useState<BoletoFilter>("all");

  const filteredItems = useMemo(() => {
    const searchValue = normalizeSearchValue(search);
    return directory.items.filter((item) => {
      const matchesSearch =
        !searchValue ||
        [
          item.legal_name,
          item.display_name ?? "",
          String(item.linx_code),
          item.document_number ?? "",
          item.city ?? "",
          item.state ?? "",
        ].some((value) => normalizeSearchValue(value).includes(searchValue));

      const matchesType =
        typeFilter === "all" ||
        (typeFilter === "client" && ["C", "A"].includes(item.registration_type ?? "")) ||
        (typeFilter === "supplier" && ["F", "A"].includes(item.registration_type ?? ""));

      const matchesBoleto =
        boletoFilter === "all" ||
        (boletoFilter === "yes" && item.supports_boleto_config && item.uses_boleto) ||
        (boletoFilter === "no" &&
          (!item.supports_boleto_config || !item.uses_boleto));

      return matchesSearch && matchesType && matchesBoleto;
    });
  }, [boletoFilter, directory.items, search, typeFilter]);

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
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Nome, código Linx, documento..."
              value={search}
            />
          </label>
          <label>
            Tipo
            <select onChange={(event) => setTypeFilter(event.target.value as TypeFilter)} value={typeFilter}>
              <option value="all">Todos</option>
              <option value="client">Clientes</option>
              <option value="supplier">Fornecedores</option>
            </select>
          </label>
          <label>
            Usa boleto
            <select onChange={(event) => setBoletoFilter(event.target.value as BoletoFilter)} value={boletoFilter}>
              <option value="all">Todos</option>
              <option value="yes">Sim</option>
              <option value="no">Não</option>
            </select>
          </label>
          <Button
            type="button"
            variant="primary"
            loading={loading}
            disabled={loading}
            onClick={() => void onSyncLinxCustomers()}
          >
            {loading ? "Atualizando..." : "Atualizar Linx"}
          </Button>
        </div>
        <div className="section-toolbar-content">
          <div className="import-last-meta">
            {latestBatch
              ? `Última atualização Linx: ${formatDate(latestBatch.created_at)}`
              : "Primeira atualização Linx vai trazer toda a base; depois, só incrementais."}
          </div>
        </div>
      </section>

      <section className="kpi-grid compact-kpis-four">
        <article className="kpi-card"><span>Total na base</span><strong>{directory.summary.total_count}</strong></article>
        <article className="kpi-card"><span>Clientes</span><strong>{directory.summary.client_count}</strong></article>
        <article className="kpi-card"><span>Fornecedores</span><strong>{directory.summary.supplier_count}</strong></article>
        <article className="kpi-card"><span>Usam boleto</span><strong>{directory.summary.boleto_enabled_count}</strong></article>
      </section>

      <section className="panel">
        <div className="table-shell tall table-shell--mobile-compact">
          <table className="erp-table mobile-compact-table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Código</th>
                <th>Razão social</th>
                <th>Nome fantasia</th>
                <th>Documento</th>
                <th>Cidade/UF</th>
                <th>Usa boleto</th>
                <th>Modo</th>
                <th>Dia</th>
                <th>Cobrar multa/juros</th>
                <th>Atualizado no Linx</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => (
                <tr key={item.id}>
                  <td className="mobile-compact-hidden" data-label="Tipo">{item.registration_type_label}</td>
                  <td className="mobile-compact-hidden" data-label="Codigo">{item.linx_code}</td>
                  <td className="mobile-compact-primary" data-label="Nome">{item.legal_name}</td>
                  <td className="mobile-compact-hidden" data-label="Fantasia">{item.display_name ?? "-"}</td>
                  <td data-label="Documento">{item.document_number ?? "-"}</td>
                  <td data-label="Cidade/UF">{item.city || item.state ? `${item.city ?? "-"} / ${item.state ?? "-"}` : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Boleto">
                    {item.supports_boleto_config ? (item.uses_boleto ? "Sim" : "Não") : "-"}
                  </td>
                  <td className="mobile-compact-hidden" data-label="Modo">{item.supports_boleto_config ? displayMode(item.mode) : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Dia">{item.supports_boleto_config ? item.boleto_due_day ?? "-" : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Multa/juros">{item.supports_boleto_config ? (item.include_interest ? "Sim" : "Não") : "-"}</td>
                  <td className="mobile-compact-hidden" data-label="Atualizado">{item.linx_updated_at ? formatDate(item.linx_updated_at) : "-"}</td>
                </tr>
              ))}
              {!filteredItems.length && (
                <tr>
                  <td className="empty-cell" colSpan={11}>
                    Nenhum cliente ou fornecedor encontrado com os filtros atuais.
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

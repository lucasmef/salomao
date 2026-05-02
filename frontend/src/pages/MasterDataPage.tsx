import { FormEvent, useMemo, useState } from "react";

import {
  CategoryGroupIcon,
  categoryGroupIconOptions,
  makeCategoryGroupIconKey,
  readCategoryGroupIconMap,
  writeCategoryGroupIconConfig,
  type CategoryGroupIconName,
} from "../components/CategoryGroupIcon";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui";
import { formatMoney } from "../lib/format";
import type { Account, Category, CategoryLookups } from "../types";

type CategorySortKey = "code" | "name" | "entry_kind" | "report_group" | "report_subgroup" | "entry_count";
type CategorySortDirection = "asc" | "desc";

type Props = {
  accounts: Account[];
  categories: Category[];
  lookups: CategoryLookups | null;
  submitting: boolean;
  onCreateAccount: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateAccount: (accountId: string, payload: Record<string, unknown>) => Promise<void>;
  onCreateCategory: (payload: Record<string, unknown>) => Promise<unknown>;
  onUpdateCategory: (categoryId: string, payload: Record<string, unknown>) => Promise<void>;
  onDeleteCategory: (categoryId: string) => Promise<void>;
  embedded?: boolean;
  view?: "all" | "accounts" | "categories";
};

const emptyAccount = {
  name: "",
  account_type: "checking",
  bank_code: "",
  branch_number: "",
  account_number: "",
  opening_balance: "0.00",
  is_active: true,
  import_ofx_enabled: true,
  exclude_from_balance: false,
  inter_api_enabled: false,
  inter_environment: "production",
  inter_api_base_url: "",
  inter_api_key: "",
  inter_account_number: "",
  inter_client_secret: "",
  inter_certificate_pem: "",
  inter_private_key_pem: "",
};

const emptyCategory = {
  code: "",
  name: "",
  entry_kind: "expense",
  report_group: "",
  report_subgroup: "",
  is_financial_expense: false,
  is_active: true,
};

function getCategoryKindLabel(entryKind: string) {
  if (entryKind === "income") return "Receita";
  if (entryKind === "expense") return "Despesa";
  if (entryKind === "transfer") return "Transferencia";
  return entryKind;
}

export function MasterDataPage({
  accounts,
  categories,
  lookups,
  submitting,
  onCreateAccount,
  onUpdateAccount,
  onCreateCategory,
  onUpdateCategory,
  onDeleteCategory,
  embedded = false,
  view = "all",
}: Props) {
  const [accountForm, setAccountForm] = useState(emptyAccount);
  const [categoryForm, setCategoryForm] = useState(emptyCategory);
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
  const [categoryKindFilter, setCategoryKindFilter] = useState("");
  const [categoryGroupFilter, setCategoryGroupFilter] = useState("");
  const [categorySubgroupFilter, setCategorySubgroupFilter] = useState("");
  const [categorySortKey, setCategorySortKey] = useState<CategorySortKey | null>(null);
  const [categorySortDirection, setCategorySortDirection] = useState<CategorySortDirection>("asc");
  const [categoryIconVersion, setCategoryIconVersion] = useState(0);
  const masterDataSectionClass = view === "all" ? "content-grid two-columns" : "content-grid single-column";
  const categoryGroupIcons = useMemo(() => readCategoryGroupIconMap(), [categoryIconVersion]);
  const activeCategoryGroupIconKey = makeCategoryGroupIconKey(categoryForm.entry_kind, categoryForm.report_group);
  const activeCategoryGroupIcon = categoryGroupIcons[activeCategoryGroupIconKey];

  const availableGroups = useMemo(
    () => (lookups?.group_options ?? []).filter((item) => item.entry_kind === categoryForm.entry_kind),
    [lookups, categoryForm.entry_kind],
  );

  const availableSubgroups = useMemo(
    () =>
      (lookups?.subgroup_options ?? []).filter(
        (item) =>
          item.entry_kind === categoryForm.entry_kind &&
          (!categoryForm.report_group || item.report_group === categoryForm.report_group),
      ),
    [lookups, categoryForm.entry_kind, categoryForm.report_group],
  );

  const categoryGroupOptions = useMemo(
    () =>
      [...new Set(categories.map((item) => item.report_group).filter(Boolean))]
        .map((item) => item ?? "")
        .sort((left, right) => left.localeCompare(right)),
    [categories],
  );

  const categorySubgroupOptions = useMemo(
    () =>
      [
        ...new Set(
          categories
            .filter((item) => !categoryGroupFilter || (item.report_group ?? "") === categoryGroupFilter)
            .map((item) => item.report_subgroup)
            .filter(Boolean),
        ),
      ]
        .map((item) => item ?? "")
        .sort((left, right) => left.localeCompare(right)),
    [categories, categoryGroupFilter],
  );

  const filteredCategories = useMemo(
    () =>
      categories.filter((category) => {
        if (categoryKindFilter && category.entry_kind !== categoryKindFilter) {
          return false;
        }
        if (categoryGroupFilter && (category.report_group ?? "") !== categoryGroupFilter) {
          return false;
        }
        if (categorySubgroupFilter && (category.report_subgroup ?? "") !== categorySubgroupFilter) {
          return false;
        }
        return true;
      }),
    [categories, categoryGroupFilter, categoryKindFilter, categorySubgroupFilter],
  );
  const sortedCategories = useMemo(() => {
    if (!categorySortKey) {
      return filteredCategories;
    }

    const sorted = [...filteredCategories].sort((left, right) => {
      if (categorySortKey === "entry_count") {
        return left.entry_count - right.entry_count;
      }

      const leftValue =
        categorySortKey === "entry_kind"
          ? getCategoryKindLabel(left.entry_kind)
          : String(left[categorySortKey] ?? "");
      const rightValue =
        categorySortKey === "entry_kind"
          ? getCategoryKindLabel(right.entry_kind)
          : String(right[categorySortKey] ?? "");
      return leftValue.localeCompare(rightValue, "pt-BR", { sensitivity: "base" });
    });

    if (categorySortDirection === "desc") {
      sorted.reverse();
    }

    return sorted;
  }, [categorySortDirection, categorySortKey, filteredCategories]);

  function toggleCategorySort(sortKey: CategorySortKey) {
    if (categorySortKey === sortKey) {
      setCategorySortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setCategorySortKey(sortKey);
    setCategorySortDirection("asc");
  }

  function categorySortIndicator(sortKey: CategorySortKey) {
    if (categorySortKey !== sortKey) {
      return "↕";
    }
    return categorySortDirection === "asc" ? "↑" : "↓";
  }

  function updateCategoryGroupIcon(icon: CategoryGroupIconName) {
    if (!categoryForm.report_group.trim()) {
      return;
    }
    writeCategoryGroupIconConfig(activeCategoryGroupIconKey, { icon });
    setCategoryIconVersion((current) => current + 1);
  }

  function uploadCategoryGroupIcon(file: File | null) {
    if (!file || !categoryForm.report_group.trim()) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      writeCategoryGroupIconConfig(activeCategoryGroupIconKey, { image: String(reader.result ?? "") });
      setCategoryIconVersion((current) => current + 1);
    };
    reader.readAsDataURL(file);
  }

  async function handleAccountSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      ...accountForm,
      bank_code: accountForm.bank_code || null,
      branch_number: accountForm.branch_number || null,
      account_number: accountForm.account_number || null,
      inter_api_base_url: accountForm.inter_api_base_url || null,
      inter_api_key: accountForm.inter_api_key || null,
      inter_account_number: accountForm.inter_account_number || null,
      inter_client_secret: accountForm.inter_client_secret || null,
      inter_certificate_pem: accountForm.inter_certificate_pem || null,
      inter_private_key_pem: accountForm.inter_private_key_pem || null,
    };
    if (editingAccountId) {
      await onUpdateAccount(editingAccountId, payload);
    } else {
      await onCreateAccount(payload);
    }
    setAccountForm(emptyAccount);
    setEditingAccountId(null);
  }

  async function handleCategorySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      ...categoryForm,
      code: categoryForm.code || null,
      report_group: categoryForm.report_group || null,
      report_subgroup: categoryForm.report_subgroup || null,
    };
    if (editingCategoryId) {
      await onUpdateCategory(editingCategoryId, payload);
    } else {
      await onCreateCategory(payload);
    }
    setCategoryForm(emptyCategory);
    setEditingCategoryId(null);
  }

  async function handleDeleteCategory(categoryId: string) {
    if (!window.confirm("Excluir esta categoria?")) {
      return;
    }
    await onDeleteCategory(categoryId);
    if (editingCategoryId === categoryId) {
      setEditingCategoryId(null);
      setCategoryForm(emptyCategory);
    }
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Cadastros"
          title="Contas e categorias"
          description="Estrutura basica do ERP com tipo, grupo, subgrupo e categoria final para classificacao financeira."
        />
      )}

      <section className={masterDataSectionClass}>
        {(view === "all" || view === "accounts") && (
          <article className="panel">
            <div className="panel-title">
              <h3>{editingAccountId ? "Editar conta" : "Nova conta"}</h3>
            </div>
            <form className="form-grid dense" onSubmit={handleAccountSubmit}>
              <label>
                Nome
                <input
                  value={accountForm.name}
                  onChange={(event) => setAccountForm({ ...accountForm, name: event.target.value })}
                  required
                />
              </label>
              <label>
                Tipo
                <select
                  value={accountForm.account_type}
                  onChange={(event) => setAccountForm({ ...accountForm, account_type: event.target.value })}
                >
                  <option value="checking">Banco</option>
                  <option value="cash">Caixa</option>
                  <option value="wallet">Dinheiro</option>
                  <option value="savings">Poupanca</option>
                  <option value="historical">Historica</option>
                </select>
              </label>
              <label>
                Banco
                <input
                  value={accountForm.bank_code}
                  onChange={(event) => setAccountForm({ ...accountForm, bank_code: event.target.value })}
                />
              </label>
              <label>
                Agencia
                <input
                  value={accountForm.branch_number}
                  onChange={(event) => setAccountForm({ ...accountForm, branch_number: event.target.value })}
                />
              </label>
              <label>
                Conta
                <input
                  value={accountForm.account_number}
                  onChange={(event) => setAccountForm({ ...accountForm, account_number: event.target.value })}
                />
              </label>
              <label>
                Saldo inicial
                <input
                  type="number"
                  step="0.01"
                  value={accountForm.opening_balance}
                  onChange={(event) => setAccountForm({ ...accountForm, opening_balance: event.target.value })}
                />
              </label>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={accountForm.is_active}
                  onChange={(event) => setAccountForm({ ...accountForm, is_active: event.target.checked })}
                />
                Conta ativa
              </label>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={accountForm.import_ofx_enabled}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, import_ofx_enabled: event.target.checked })
                  }
                />
                Importa OFX
              </label>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={accountForm.exclude_from_balance}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, exclude_from_balance: event.target.checked })
                  }
                />
                Ignorar no saldo e no fluxo de caixa
              </label>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={accountForm.inter_api_enabled}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, inter_api_enabled: event.target.checked })
                  }
                />
                API Banco Inter
              </label>
              <small className="compact-muted full-width">
                Apenas uma conta pode ficar com a API do Inter habilitada. Ao salvar esta conta como ativa para o Inter,
                o sistema desabilita essa opcao nas demais.
              </small>
              <label>
                Ambiente Inter
                <select
                  value={accountForm.inter_environment}
                  onChange={(event) => setAccountForm({ ...accountForm, inter_environment: event.target.value })}
                >
                  <option value="production">Producao</option>
                  <option value="sandbox">Sandbox</option>
                </select>
              </label>
              <label>
                Chave API / Client ID
                <input
                  value={accountForm.inter_api_key}
                  onChange={(event) => setAccountForm({ ...accountForm, inter_api_key: event.target.value })}
                  placeholder="Client ID da integracao Inter"
                />
              </label>
              <label>
                Conta corrente Inter
                <input
                  value={accountForm.inter_account_number}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, inter_account_number: event.target.value })
                  }
                  placeholder="Numero da conta para API"
                />
              </label>
              <label>
                URL base Inter
                <input
                  value={accountForm.inter_api_base_url}
                  onChange={(event) => setAccountForm({ ...accountForm, inter_api_base_url: event.target.value })}
                  placeholder="Opcional. Preencha so se precisar sobrescrever"
                />
              </label>
              <label className="full-width">
                Client secret Inter
                <textarea
                  rows={3}
                  value={accountForm.inter_client_secret}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, inter_client_secret: event.target.value })
                  }
                  placeholder="Deixe em branco para manter o secret ja salvo"
                />
              </label>
              <label className="full-width">
                Certificado PEM
                <textarea
                  rows={4}
                  value={accountForm.inter_certificate_pem}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, inter_certificate_pem: event.target.value })
                  }
                  placeholder="Cole o certificado da integracao Inter"
                />
              </label>
              <label className="full-width">
                Chave privada PEM
                <textarea
                  rows={4}
                  value={accountForm.inter_private_key_pem}
                  onChange={(event) =>
                    setAccountForm({ ...accountForm, inter_private_key_pem: event.target.value })
                  }
                  placeholder="Cole a chave privada da integracao Inter"
                />
              </label>
              <div className="action-row">
                <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                  {editingAccountId ? "Salvar alteracoes" : "Criar conta"}
                </Button>
                {editingAccountId && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setEditingAccountId(null);
                      setAccountForm(emptyAccount);
                    }}
                  >
                    Cancelar edicao
                  </Button>
                )}
              </div>
            </form>
          </article>
        )}

        {(view === "all" || view === "categories") && (
          <article className="panel">
            <div className="panel-title">
              <h3>{editingCategoryId ? "Editar categoria" : "Nova categoria"}</h3>
            </div>
            <form className="form-grid dense" onSubmit={handleCategorySubmit}>
            <label>
              Codigo
              <input
                value={categoryForm.code}
                onChange={(event) => setCategoryForm({ ...categoryForm, code: event.target.value })}
              />
            </label>
            <label>
              Nome
              <input
                value={categoryForm.name}
                onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })}
                required
              />
            </label>
            <label>
              Tipo
              <select
                value={categoryForm.entry_kind}
                onChange={(event) =>
                  setCategoryForm({
                    ...categoryForm,
                    entry_kind: event.target.value,
                    report_group: "",
                    report_subgroup: "",
                    is_financial_expense: event.target.value === "expense" ? categoryForm.is_financial_expense : false,
                  })
                }
              >
                <option value="expense">Despesa</option>
                <option value="income">Receita</option>
                <option value="transfer">Transferencia</option>
              </select>
            </label>
            <label>
              Grupo
              <input
                list="category-group-options"
                value={categoryForm.report_group}
                onChange={(event) =>
                  setCategoryForm({ ...categoryForm, report_group: event.target.value, report_subgroup: "" })
                }
                placeholder="Escolha ou digite um novo grupo"
                required
              />
            </label>
            <datalist id="category-group-options">
              {availableGroups.map((group) => (
                <option key={`${group.entry_kind}-${group.name}`} value={group.name} />
              ))}
            </datalist>
            <div className="category-group-icon-editor">
              <div className="category-group-icon-preview">
                <span className="entries-cell-icon entries-category-group-icon">
                  <CategoryGroupIcon config={activeCategoryGroupIcon} group={categoryForm.report_group} />
                </span>
                <span>{categoryForm.report_group.trim() || "Informe um grupo"}</span>
              </div>
              <div className="category-group-icon-picker" aria-label="Icone do grupo de categoria">
                {categoryGroupIconOptions.map((option) => (
                  <button
                    className={activeCategoryGroupIcon?.icon === option.value ? "is-active" : ""}
                    disabled={!categoryForm.report_group.trim()}
                    key={option.value}
                    onClick={() => updateCategoryGroupIcon(option.value)}
                    title={option.label}
                    type="button"
                  >
                    <CategoryGroupIcon config={{ icon: option.value }} />
                  </button>
                ))}
              </div>
              <label className="category-group-icon-upload">
                Upload do icone
                <input
                  accept="image/*"
                  disabled={!categoryForm.report_group.trim()}
                  onChange={(event) => uploadCategoryGroupIcon(event.target.files?.[0] ?? null)}
                  type="file"
                />
              </label>
            </div>
            <label>
              Subgrupo
              <input
                list="category-subgroup-options"
                value={categoryForm.report_subgroup}
                onChange={(event) => setCategoryForm({ ...categoryForm, report_subgroup: event.target.value })}
                placeholder="Opcional. Escolha ou digite um subgrupo"
              />
            </label>
            <datalist id="category-subgroup-options">
              {availableSubgroups.map((subgroup) => (
                <option
                  key={`${subgroup.entry_kind}-${subgroup.report_group}-${subgroup.name}`}
                  value={subgroup.name}
                />
              ))}
            </datalist>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={categoryForm.is_financial_expense}
                disabled={categoryForm.entry_kind !== "expense"}
                onChange={(event) =>
                  setCategoryForm({ ...categoryForm, is_financial_expense: event.target.checked })
                }
              />
              Despesa financeira
            </label>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={categoryForm.is_active}
                onChange={(event) => setCategoryForm({ ...categoryForm, is_active: event.target.checked })}
              />
              Categoria ativa
            </label>
            <div className="action-row">
              <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                {editingCategoryId ? "Salvar alteracoes" : "Criar categoria"}
              </Button>
              {editingCategoryId && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setEditingCategoryId(null);
                    setCategoryForm(emptyCategory);
                  }}
                >
                  Cancelar edicao
                </Button>
              )}
            </div>
            </form>
          </article>
        )}
      </section>

      <section className={masterDataSectionClass}>
        {(view === "all" || view === "accounts") && (
          <article className="panel">
          <div className="panel-title">
            <h3>Contas cadastradas</h3>
            <span>{accounts.length}</span>
          </div>
          <div className="table-shell tall">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>Conta</th>
                  <th>Tipo</th>
                  <th>Saldo inicial</th>
                  <th>OFX</th>
                  <th>Saldo</th>
                  <th>Inter</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => (
                  <tr key={account.id}>
                    <td>{account.name}</td>
                    <td>{account.account_type}</td>
                    <td>{formatMoney(account.opening_balance)}</td>
                    <td>{account.import_ofx_enabled ? "Habilitado" : "Bloqueado"}</td>
                    <td>{account.exclude_from_balance ? "Ignorado" : "Considerado"}</td>
                    <td>
                      {account.inter_api_enabled
                        ? account.has_inter_client_secret && account.has_inter_certificate && account.has_inter_private_key
                          ? "Configurado"
                          : "Pendente"
                        : "Desligado"}
                    </td>
                    <td>{account.is_active ? "Ativa" : "Inativa"}</td>
                    <td className="row-actions">
                      <button
                        className="table-button"
                        type="button"
                        onClick={() => {
                          setEditingAccountId(account.id);
                          setAccountForm({
                            name: account.name,
                            account_type: account.account_type,
                            bank_code: account.bank_code ?? "",
                            branch_number: account.branch_number ?? "",
                            account_number: account.account_number ?? "",
                            opening_balance: account.opening_balance,
                            is_active: account.is_active ?? true,
                            import_ofx_enabled: account.import_ofx_enabled ?? false,
                            exclude_from_balance: account.exclude_from_balance ?? false,
                            inter_api_enabled: account.inter_api_enabled ?? false,
                            inter_environment: account.inter_environment ?? "production",
                            inter_api_base_url: account.inter_api_base_url ?? "",
                            inter_api_key: account.inter_api_key ?? "",
                            inter_account_number: account.inter_account_number ?? "",
                            inter_client_secret: "",
                            inter_certificate_pem: "",
                            inter_private_key_pem: "",
                          });
                        }}
                      >
                        Editar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </article>
        )}

        {(view === "all" || view === "categories") && (
          <article className="panel">
          <div className="panel-title">
            <h3>Categorias cadastradas</h3>
            <span>
              {filteredCategories.length} de {categories.length}
            </span>
          </div>
          <div className="toolbar-row compact">
            <label>
              Tipo
              <select value={categoryKindFilter} onChange={(event) => setCategoryKindFilter(event.target.value)}>
                <option value="">Todos</option>
                <option value="income">Receitas</option>
                <option value="expense">Despesas</option>
                <option value="transfer">Transferencias</option>
              </select>
            </label>
            <label>
              Grupo
              <select
                value={categoryGroupFilter}
                onChange={(event) => {
                  setCategoryGroupFilter(event.target.value);
                  setCategorySubgroupFilter("");
                }}
              >
                <option value="">Todos</option>
                {categoryGroupOptions.map((group) => (
                  <option key={group} value={group}>
                    {group}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Subgrupo
              <select value={categorySubgroupFilter} onChange={(event) => setCategorySubgroupFilter(event.target.value)}>
                <option value="">Todos</option>
                {categorySubgroupOptions.map((subgroup) => (
                  <option key={subgroup} value={subgroup}>
                    {subgroup}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="table-shell tall">
            <table className="erp-table">
              <thead>
                <tr>
                  <th>
                    <button className="table-sort-button" type="button" onClick={() => toggleCategorySort("code")}>
                      Codigo
                      <span>{categorySortIndicator("code")}</span>
                    </button>
                  </th>
                  <th>
                    <button className="table-sort-button" type="button" onClick={() => toggleCategorySort("name")}>
                      Categoria
                      <span>{categorySortIndicator("name")}</span>
                    </button>
                  </th>
                  <th>
                    <button className="table-sort-button" type="button" onClick={() => toggleCategorySort("entry_kind")}>
                      Tipo
                      <span>{categorySortIndicator("entry_kind")}</span>
                    </button>
                  </th>
                  <th>
                    <button className="table-sort-button" type="button" onClick={() => toggleCategorySort("report_group")}>
                      Grupo
                      <span>{categorySortIndicator("report_group")}</span>
                    </button>
                  </th>
                  <th>
                    <button
                      className="table-sort-button"
                      type="button"
                      onClick={() => toggleCategorySort("report_subgroup")}
                    >
                      Subgrupo
                      <span>{categorySortIndicator("report_subgroup")}</span>
                    </button>
                  </th>
                  <th className="numeric-cell">
                    <button className="table-sort-button numeric" type="button" onClick={() => toggleCategorySort("entry_count")}>
                      Lancamentos
                      <span>{categorySortIndicator("entry_count")}</span>
                    </button>
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sortedCategories.map((category) => (
                  <tr key={category.id}>
                    <td>{category.code ?? "-"}</td>
                    <td>{category.name}</td>
                    <td>{getCategoryKindLabel(category.entry_kind)}</td>
                    <td>
                      <span className="category-group-cell">
                        <span className="entries-cell-icon entries-category-group-icon">
                          <CategoryGroupIcon
                            config={categoryGroupIcons[makeCategoryGroupIconKey(category.entry_kind, category.report_group)]}
                            group={category.report_group}
                          />
                        </span>
                        <span>{category.report_group ?? "-"}</span>
                      </span>
                    </td>
                    <td>{category.report_subgroup ?? "-"}</td>
                    <td className="numeric-cell">{category.entry_count}</td>
                    <td className="row-actions">
                      <button
                        className="table-button"
                        type="button"
                        onClick={() => {
                          setEditingCategoryId(category.id);
                          setCategoryForm({
                            code: category.code ?? "",
                            name: category.name,
                            entry_kind: category.entry_kind,
                            report_group: category.report_group ?? "",
                            report_subgroup: category.report_subgroup ?? "",
                            is_financial_expense: category.is_financial_expense,
                            is_active: category.is_active ?? true,
                          });
                        }}
                      >
                        Editar
                      </button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => void handleDeleteCategory(category.id)}>
                        Excluir
                      </Button>
                    </td>
                  </tr>
                ))}
                {!sortedCategories.length && (
                  <tr>
                    <td colSpan={7}>Nenhuma categoria encontrada com esse filtro.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </article>
        )}
      </section>
    </div>
  );
}

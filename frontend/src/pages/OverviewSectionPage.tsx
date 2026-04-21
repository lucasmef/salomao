import { useEffect, useRef, useState } from "react";

import { BarChart } from "../components/BarChart";
import { RefreshIcon } from "../components/RefreshIcon";
import { RevenueComparisonChart } from "../components/RevenueComparisonChart";
import { SectionChrome } from "../components/SectionChrome";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
  onRefreshData: () => Promise<void>;
};

function toInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

function formatRangeLabel(start: string, end: string) {
  if (!start && !end) {
    return "Selecionar periodo";
  }
  if (start && end) {
    return `${formatDate(start)} - ${formatDate(end)}`;
  }
  return start ? `${formatDate(start)} - ...` : `... - ${formatDate(end)}`;
}

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function formatBirthdayDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  }).format(parseIsoDate(value));
}

function CalendarRangeIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M4 1.75a.75.75 0 0 1 1.5 0V3h5V1.75a.75.75 0 0 1 1.5 0V3h.75A2.25 2.25 0 0 1 15 5.25v7.5A2.25 2.25 0 0 1 12.75 15h-9.5A2.25 2.25 0 0 1 1 12.75v-7.5A2.25 2.25 0 0 1 3.25 3H4V1.75ZM2.5 6.5v6.25c0 .414.336.75.75.75h9.5a.75.75 0 0 0 .75-.75V6.5h-11Zm11-1.5v-.75a.75.75 0 0 0-.75-.75h-.75v.5a.75.75 0 0 1-1.5 0v-.5h-5v.5a.75.75 0 0 1-1.5 0v-.5h-.75a.75.75 0 0 0-.75.75V5h11Z" />
    </svg>
  );
}

function FilterFunnelIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" height="14" viewBox="0 0 16 16" width="14">
      <path d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5a1.25 1.25 0 0 1 .965 2.045L10 8.56v3.19a1.25 1.25 0 0 1-.553 1.036l-1.75 1.167A.75.75 0 0 1 6.5 13.33V8.56L2.285 4.045A1.24 1.24 0 0 1 2 3.25Zm1.545.25L7.882 8.15a.75.75 0 0 1 .203.512v3.266L8.5 11.65V8.662a.75.75 0 0 1 .203-.512L12.455 3.5h-8.91Z" />
    </svg>
  );
}

function ChevronDownIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="14"
      viewBox="0 0 16 16"
      width="14"
      style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.16s ease" }}
    >
      <path d="m4 6 4 4 4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  );
}

export function OverviewSectionPage({
  tabs,
  dashboard,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
  onRefreshData,
}: Props) {
  const currentTab = tabs[0];
  const hasMountedAutoApplyRef = useRef(false);
  const applyFiltersRef = useRef(onApplyFilters);
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const presetMenuRef = useRef<HTMLDivElement | null>(null);
  const balancePopoverRef = useRef<HTMLDivElement | null>(null);
  const accountBalances = dashboard?.account_balances ?? [];
  const totalAccountBalance = accountBalances.reduce(
    (total, account) => (account.exclude_from_balance ? total : total + Number(account.current_balance ?? 0)),
    0,
  );
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showPresetMenu, setShowPresetMenu] = useState(false);
  const [showBalancePopover, setShowBalancePopover] = useState(false);

  useEffect(() => {
    applyFiltersRef.current = onApplyFilters;
  }, [onApplyFilters]);

  useEffect(() => {
    if (!hasMountedAutoApplyRef.current) {
      hasMountedAutoApplyRef.current = true;
      return;
    }
    void applyFiltersRef.current();
  }, [filters.end, filters.start]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
      if (showPresetMenu && presetMenuRef.current && !presetMenuRef.current.contains(target)) {
        setShowPresetMenu(false);
      }
      if (showBalancePopover && balancePopoverRef.current && !balancePopoverRef.current.contains(target)) {
        setShowBalancePopover(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showBalancePopover, showPeriodPopover, showPresetMenu]);

  function setDateRange(start: string, end: string) {
    onChangeFilters({ start, end });
  }

  async function applyQuickRange(kind: "month" | "previous" | "year") {
    const now = new Date();
    let nextFilters = filters;

    if (kind === "month") {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), now.getMonth(), 1)),
        end: toInput(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
      };
    } else if (kind === "previous") {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
        end: toInput(new Date(now.getFullYear(), now.getMonth(), 0)),
      };
    } else {
      nextFilters = {
        start: toInput(new Date(now.getFullYear(), 0, 1)),
        end: toInput(new Date(now.getFullYear(), 11, 31)),
      };
    }

    onChangeFilters(nextFilters);
  }

  return (
    <SectionChrome
      sectionLabel="Visão Geral"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className="section-toolbar-panel entries-top-panel overview-top-panel">
        <div className="entries-toolbar-bar overview-toolbar-bar">
          <div className="entries-period-group" ref={periodPopoverRef}>
            <button
              aria-expanded={showPeriodPopover}
              aria-label="Selecionar período"
              className={`entries-period-trigger ${showPeriodPopover ? "is-active" : ""}`}
              disabled={loading}
              onClick={() => {
                setShowPresetMenu(false);
                setShowPeriodPopover((current) => !current);
              }}
              type="button"
            >
              <CalendarRangeIcon />
              <span>{formatRangeLabel(filters.start, filters.end)}</span>
            </button>
            {showPeriodPopover && (
              <div className="entries-floating-panel entries-period-popover">
                <div className="entries-period-fields">
                  <label>
                    Início
                    <input
                      disabled={loading}
                      type="date"
                      value={filters.start}
                      onChange={(event) => setDateRange(event.target.value, filters.end)}
                    />
                  </label>
                  <label>
                    Fim
                    <input
                      disabled={loading}
                      type="date"
                      value={filters.end}
                      onChange={(event) => setDateRange(filters.start, event.target.value)}
                    />
                  </label>
                </div>
                <div className="entries-period-footer">
                  <button
                    className="secondary-button compact-button"
                    onClick={() => {
                      setDateRange("", "");
                      setShowPeriodPopover(false);
                    }}
                    type="button"
                  >
                    Limpar
                  </button>
                  <button
                    className="primary-button compact-button"
                    onClick={() => setShowPeriodPopover(false)}
                    type="button"
                  >
                    Concluir
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="entries-toolbar-icon-wrap" ref={presetMenuRef}>
            <button
              aria-expanded={showPresetMenu}
              aria-label="Filtros pré-definidos de data"
              className={`entries-toolbar-icon ${showPresetMenu ? "is-active" : ""}`}
              disabled={loading}
              onClick={() => {
                setShowPeriodPopover(false);
                setShowPresetMenu((current) => !current);
              }}
              title="Períodos pré-definidos"
              type="button"
            >
              <FilterFunnelIcon />
              <span className="entries-toolbar-icon-label">Atalhos</span>
            </button>
            {showPresetMenu && (
              <div className="entries-floating-panel entries-icon-menu">
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("month");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês atual
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("previous");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Mês anterior
                </button>
                <button
                  className="entries-icon-menu-item"
                  onClick={() => {
                    void applyQuickRange("year");
                    setShowPresetMenu(false);
                  }}
                  type="button"
                >
                  Ano atual
                </button>
              </div>
            )}
          </div>

          <div className="entries-toolbar-icon-wrap">
            <button
              aria-label="Atualizar dados analiticos"
              className={`entries-toolbar-icon ${loading ? "is-loading" : ""}`}
              disabled={loading}
              onClick={() => void onRefreshData()}
              title="Atualizar dados analiticos"
              type="button"
            >
              <RefreshIcon />
              <span className="entries-toolbar-icon-label">Atualizar</span>
            </button>
          </div>

          <div className="reconciliation-balance-wrap overview-balance-wrap" ref={balancePopoverRef}>
            <button
              aria-expanded={showBalancePopover}
              className={`reconciliation-balance-trigger ${showBalancePopover ? "is-active" : ""}`}
              onClick={() => setShowBalancePopover((current) => !current)}
              type="button"
            >
              <span>Saldo total</span>
              <strong>{formatMoney(totalAccountBalance)}</strong>
              <ChevronDownIcon expanded={showBalancePopover} />
            </button>
            {showBalancePopover && (
              <div className="reconciliation-balance-popover">
                {accountBalances.map((account) => (
                  <div className={`reconciliation-balance-row ${account.exclude_from_balance ? "is-ignored-account" : ""}`} key={account.account_id}>
                    <span title={account.account_name}>
                      {account.account_name}
                      {account.exclude_from_balance && <span className="ignored-badge"> (Ignorado)</span>}
                    </span>
                    <strong>{formatMoney(account.current_balance)}</strong>
                  </div>
                ))}
                {!accountBalances.length && (
                  <div className="reconciliation-balance-empty">Nenhum saldo disponivel.</div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="content-grid two-columns overview-grid">
        <div className="overview-dre-column">
          <BarChart title="DRE resumido" data={dashboard?.dre_chart ?? []} tone="success" />
        </div>
        <div className="overview-side-column">
          <RevenueComparisonChart
            title="Comparacao de Ano x Ano em Vendas"
            comparison={
              dashboard?.revenue_comparison ?? {
                current_year: new Date().getFullYear(),
                previous_year: new Date().getFullYear() - 1,
                points: [],
              }
            }
          />
        </div>
      </section>

      <section className="panel-card birthday-week-panel">
        <div className="panel-title">
          <div>
            <h3>Aniversariantes da semana</h3>
            <p className="birthday-week-subtitle">
              {dashboard?.week_birthdays.week_label ?? "Semana atual"} • clientes com compra nos 2 ultimos anos
            </p>
          </div>
        </div>

        {dashboard?.week_birthdays.items.length ? (
          <div className="birthday-week-list">
            {dashboard.week_birthdays.items.map((item) => (
              <article className="birthday-week-item" key={`${item.linx_code}-${item.birthday_date}`}>
                <div className="birthday-week-copy">
                  <strong>{item.customer_name}</strong>
                  <span>
                    Nascimento {formatDate(item.birth_date)} • ultima compra {formatDate(item.last_purchase_date)}
                  </span>
                </div>
                <div className="birthday-week-date">{formatBirthdayDate(item.birthday_date)}</div>
              </article>
            ))}
          </div>
        ) : (
          <p className="birthday-week-empty">Nenhum aniversariante elegivel nesta semana.</p>
        )}
      </section>
    </SectionChrome>
  );
}

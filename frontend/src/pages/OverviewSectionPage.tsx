import { useEffect, useRef, useState } from "react";

import { RevenueComparisonChart } from "../components/RevenueComparisonChart";
import { SectionChrome } from "../components/SectionChrome";
import { Button, Card, EmptyState, Input, KpiCard, PeriodChips } from "../components/ui";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";
import type { DashboardOverview } from "../types";
import styles from "./OverviewSectionPage.module.css";

const DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS = 5;

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
  onOpenEntriesKind: (kind: "income" | "expense") => Promise<void>;
  onOpenDelinquency: () => Promise<void>;
  onOpenSalesReport: () => Promise<void>;
};

type PeriodKey = "today" | "7d" | "30d" | "mtd" | "ytd" | "";

const PERIOD_OPTIONS = [
  { key: "today", label: "Hoje" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "mtd", label: "MTD" },
  { key: "ytd", label: "YTD" },
] as const;

function toInput(value: Date) {
  return value.toISOString().slice(0, 10);
}

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  }).format(parseIsoDate(value));
}

function formatBirthdayDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  }).format(parseIsoDate(value));
}

function formatRangeLabel(start: string, end: string) {
  if (!start && !end) return "Período personalizado";
  if (start && end) return `${formatDate(start)} - ${formatDate(end)}`;
  return start ? `${formatDate(start)} - ...` : `... - ${formatDate(end)}`;
}

function formatOverviewPeriod(start: string, end: string) {
  const reference = start || end;
  if (!reference) return "VISÃO GERAL";
  const date = parseIsoDate(reference);
  const month = new Intl.DateTimeFormat("pt-BR", { month: "long" }).format(date).toUpperCase();
  return `VISÃO GERAL · ${month} ${date.getFullYear()}`;
}

function formatCompactMonth(value: string) {
  if (!value) return "";
  const date = parseIsoDate(value);
  const month = new Intl.DateTimeFormat("pt-BR", { month: "short" })
    .format(date)
    .replace(".", "");
  return `${month.charAt(0).toUpperCase()}${month.slice(1)}/${String(date.getFullYear()).slice(-2)}`;
}

function numeric(value: string | number | null | undefined) {
  return Number(value ?? 0);
}

function formatPercent(value: string | number | null | undefined) {
  const parsed = numeric(value);
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(parsed) ? parsed : 0)}%`;
}

function formatSignedPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const parsed = numeric(value);
  const formatted = formatPercent(Math.abs(parsed));
  return `${parsed >= 0 ? "+" : "-"}${formatted}`;
}

function toSparkline(values: Array<string | number> | undefined) {
  return values?.map((value) => numeric(value)).filter((value) => Number.isFinite(value)) ?? [];
}

function formatSignedMoney(value: string | number | null | undefined) {
  const parsed = numeric(value);
  const formatted = formatMoney(Math.abs(parsed));
  return parsed > 0 ? `+${formatted}` : parsed < 0 ? `-${formatted}` : formatted;
}

function initials(value: string) {
  return value
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function buildQuickRange(kind: Exclude<PeriodKey, "">) {
  const now = new Date();
  if (kind === "today") {
    return {
      start: toInput(now),
      end: toInput(now),
    };
  }
  if (kind === "7d") {
    return {
      start: toInput(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6)),
      end: toInput(now),
    };
  }
  if (kind === "30d") {
    return {
      start: toInput(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29)),
      end: toInput(now),
    };
  }
  if (kind === "mtd") {
    return {
      start: toInput(new Date(now.getFullYear(), now.getMonth(), 1)),
      end: toInput(now),
    };
  }
  return {
    start: toInput(new Date(now.getFullYear(), 0, 1)),
    end: toInput(now),
  };
}

function detectPeriod(filters: { start: string; end: string }): PeriodKey {
  for (const option of PERIOD_OPTIONS) {
    const range = buildQuickRange(option.key);
    if (range.start === filters.start && range.end === filters.end) {
      return option.key;
    }
  }
  return "";
}

export function OverviewSectionPage({
  tabs,
  dashboard,
  filters,
  loading,
  onChangeFilters,
  onApplyFilters,
  onOpenEntriesKind,
  onOpenDelinquency,
  onOpenSalesReport,
}: Props) {
  const currentTab = tabs[0];
  const hasMountedAutoApplyRef = useRef(false);
  const applyFiltersRef = useRef(onApplyFilters);
  const periodPopoverRef = useRef<HTMLDivElement | null>(null);
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
  const [showAccountBalances, setShowAccountBalances] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodKey>(() => detectPeriod(filters));

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
    setSelectedPeriod(detectPeriod(filters));
  }, [filters.end, filters.start]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (showPeriodPopover && periodPopoverRef.current && !periodPopoverRef.current.contains(target)) {
        setShowPeriodPopover(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showPeriodPopover]);

  function setDateRange(start: string, end: string) {
    setSelectedPeriod("");
    onChangeFilters({ start, end });
  }

  function handleQuickRange(key: string) {
    const next = buildQuickRange(key as Exclude<PeriodKey, "">);
    setSelectedPeriod(key as PeriodKey);
    setShowPeriodPopover(false);
    onChangeFilters(next);
  }

  const accountBalances = dashboard?.account_balances ?? [];
  const totalAccountBalance = accountBalances.reduce(
    (total, account) => (account.exclude_from_balance ? total : total + numeric(account.current_balance)),
    0,
  );
  const overduePayables = dashboard?.overdue_payables ?? [];
  const pendingReconciliationItems = dashboard?.pending_reconciliation_items ?? [];
  const consolidatedBalance = totalAccountBalance || numeric(dashboard?.kpis.current_balance);
  const receivablesPeriod = numeric(dashboard?.kpis.receivables_period ?? dashboard?.kpis.receivables_30d);
  const payablesPeriod = numeric(dashboard?.kpis.payables_period ?? dashboard?.kpis.payables_30d);
  const delinquencyRate = numeric(dashboard?.kpis.delinquency_rate);
  const overdueReceivablesAmount = numeric(dashboard?.kpis.overdue_receivables_amount);
  const kpiSparklines = dashboard?.kpi_sparklines;
  const birthdayPurchaseLookbackYears =
    dashboard?.week_birthdays.purchase_lookback_years ?? DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS;
  const operationalAlerts = [
    {
      key: "reconciliation",
      tone: "urgent",
      label: `${dashboard?.pending_reconciliations ?? 0} conciliações pendentes`,
      detail: pendingReconciliationItems[0]?.description ?? "Extratos aguardando vínculo com lançamentos.",
      action: "Revisar",
      show: Boolean(dashboard?.pending_reconciliations),
    },
    {
      key: "receivables",
      tone: "urgent",
      label: `${dashboard?.kpis.overdue_receivables ?? 0} recebíveis vencidos`,
      detail: overdueReceivablesAmount ? formatMoney(overdueReceivablesAmount) : "Sem valor vencido.",
      action: "Cobrar",
      show: Boolean(dashboard?.kpis.overdue_receivables),
    },
    {
      key: "payables",
      tone: "info",
      label: `${dashboard?.kpis.overdue_payables ?? 0} pagamentos vencidos`,
      detail: overduePayables[0]?.title ?? "Sem pagamentos vencidos.",
      action: "Pagar",
      show: Boolean(dashboard?.kpis.overdue_payables),
    },
  ].filter((item) => item.show);
  const hasDashboard = Boolean(dashboard);
  const overviewPeriod = formatOverviewPeriod(filters.start, filters.end);

  return (
    <SectionChrome
      sectionLabel="Visão Geral"
      tabLabel={currentTab.label}
      title={currentTab.title}
      description={currentTab.description}
      tabs={tabs}
    >
      <section className={styles.toolbar}>
        <div className={styles.toolbarCopy}>
          <span className={styles.heroEyebrow}>{overviewPeriod}</span>
          <h2 className={styles.headline}>Bom dia, <span>Lucas</span>.</h2>
          <p className={styles.heroSubline}>
            Você tem <strong>{dashboard?.pending_reconciliations ?? 0} conciliações</strong> e{" "}
            <strong>{dashboard?.kpis.overdue_receivables ?? 0} recebíveis vencidos</strong> esperando atenção.
          </p>
        </div>

        <div className={styles.toolbarControls}>
          <PeriodChips
            options={PERIOD_OPTIONS.map((option) => ({ key: option.key, label: option.label }))}
            value={selectedPeriod}
            onChange={handleQuickRange}
            customLabel="Personalizado"
            onCustomClick={() => setShowPeriodPopover((current) => !current)}
          />
        </div>

        {showPeriodPopover && (
          <div className={styles.periodPopoverWrap} ref={periodPopoverRef}>
            <Card className={styles.periodPopover}>
              <div className={styles.periodFields}>
                <label>
                  Início
                  <Input disabled={loading} type="date" value={filters.start} onChange={(event) => setDateRange(event.target.value, filters.end)} />
                </label>
                <label>
                  Fim
                  <Input disabled={loading} type="date" value={filters.end} onChange={(event) => setDateRange(filters.start, event.target.value)} />
                </label>
              </div>
              <div className={styles.periodActions}>
                <Button
                  size="md"
                  variant="ghost"
                  onClick={() => {
                    setDateRange("", "");
                    setShowPeriodPopover(false);
                  }}
                >
                  Limpar
                </Button>
                <Button size="md" onClick={() => setShowPeriodPopover(false)}>
                  Concluir
                </Button>
              </div>
              <p className={styles.periodHint}>{formatRangeLabel(filters.start, filters.end)}</p>
            </Card>
          </div>
        )}
      </section>

      {!dashboard && !loading ? (
        <EmptyState
          title="Dashboard vazio"
          message="Configure as categorias do DRE para começar a acompanhar os indicadores principais aqui."
        />
      ) : null}

      {hasDashboard ? (
        <>
          <section className={styles.kpiStrip}>
            <button
              className={styles.kpiButton}
              type="button"
              aria-expanded={showAccountBalances}
              onClick={() => setShowAccountBalances((current) => !current)}
            >
              <KpiCard
                delta={showAccountBalances ? "Ocultar contas" : "Ver contas"}
                goodTrend={consolidatedBalance >= 0}
                label="Saldo consolidado"
                sparkline={toSparkline(kpiSparklines?.balance)}
                trend={consolidatedBalance >= 0 ? "up" : "down"}
                value={formatMoney(consolidatedBalance)}
              />
            </button>
            <button className={styles.kpiButton} type="button" onClick={() => void onOpenEntriesKind("income")}>
              <KpiCard
                delta="Período"
                label="A receber"
                sparkline={toSparkline(kpiSparklines?.receivables)}
                trend="up"
                value={formatMoney(receivablesPeriod)}
              />
            </button>
            <button className={styles.kpiButton} type="button" onClick={() => void onOpenEntriesKind("expense")}>
              <KpiCard
                delta="Período"
                goodTrend={payablesPeriod <= receivablesPeriod}
                label="A pagar"
                sparkline={toSparkline(kpiSparklines?.payables)}
                trend={payablesPeriod > receivablesPeriod ? "up" : "down"}
                value={formatMoney(payablesPeriod)}
              />
            </button>
            <button className={styles.kpiButton} type="button" onClick={() => void onOpenDelinquency()}>
              <KpiCard
                delta={overdueReceivablesAmount ? formatMoney(overdueReceivablesAmount) : "Sem vencidos"}
                goodTrend={delinquencyRate === 0}
                label="Inadimplência"
                sparkline={toSparkline(kpiSparklines?.delinquency)}
                trend={delinquencyRate > 0 ? "up" : "flat"}
                value={formatPercent(dashboard?.kpis.delinquency_rate)}
              />
            </button>
            <button className={styles.kpiButton} type="button" onClick={() => void onOpenSalesReport()}>
              <KpiCard
                hero
                delta={dashboard?.today_sales?.updated_at ? `Atualizado ${formatDateTime(dashboard.today_sales.updated_at)}` : "Hoje"}
                label="Vendas do dia"
                sparkline={toSparkline(kpiSparklines?.sales)}
                trend="up"
                value={formatMoney(dashboard?.today_sales?.gross_revenue ?? 0)}
              />
            </button>
          </section>
          {showAccountBalances ? (
            <Card className={styles.accountBreakdown}>
              <div className={styles.accountBreakdownHeader}>
                <strong>Saldo por conta</strong>
                <span>{accountBalances.length} contas</span>
              </div>
              <div className={styles.accountBreakdownList}>
                {accountBalances.map((account) => (
                  <div key={account.account_id} className={styles.accountBreakdownRow}>
                    <span>
                      {account.account_name}
                      {account.exclude_from_balance ? <em>Fora do saldo</em> : null}
                    </span>
                    <strong className={numeric(account.current_balance) >= 0 ? styles.positiveAmount : ""}>
                      {formatMoney(account.current_balance)}
                    </strong>
                  </div>
                ))}
                {!accountBalances.length ? (
                  <EmptyState title="Sem contas" message="Nenhuma conta retornou saldo para o período." />
                ) : null}
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {dashboard ? (
        <>
          <section className={styles.approvedMainGrid}>
            <Card className={styles.panelCard}>
              <div className={styles.panelHeader}>
                <div>
                  <h3>Aniversariantes da semana</h3>
                  <p>
                    {dashboard.week_birthdays.week_label ?? "Semana atual"} com compra nos últimos{" "}
                    {birthdayPurchaseLookbackYears} anos.
                  </p>
                </div>
                <span className={styles.countBadge}>{dashboard.week_birthdays.items.length}</span>
              </div>
              {dashboard.week_birthdays.items.length ? (
                <div className={styles.list}>
                  {dashboard.week_birthdays.items.slice(0, 5).map((item) => {
                    const todayBirthday = item.birthday_date === new Date().toISOString().slice(0, 10);
                    return (
                      <article key={`${item.linx_code}-${item.birthday_date}`} className={styles.birthdayItem}>
                        <div className={`${styles.avatar} ${todayBirthday ? styles.avatarActive : ""}`}>
                          {initials(item.customer_name)}
                        </div>
                        <div className={styles.listCopy}>
                          <strong>{item.customer_name}</strong>
                          <span>Última compra em {formatShortDate(item.last_purchase_date)}</span>
                        </div>
                        <div className={styles.listMeta}>
                          <em>{formatBirthdayDate(item.birthday_date)}</em>
                          {todayBirthday ? <span className={styles.todayBadge}>Hoje</span> : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <EmptyState title="Sem aniversariantes" message="Nenhum cliente elegível aparece nesta semana." />
              )}
            </Card>

            <div className={styles.comparisonPanel}>
              <RevenueComparisonChart title="Comparativo · Ano × Ano" comparison={dashboard.revenue_comparison} />
            </div>
          </section>

          <section className={styles.approvedBottomGrid}>
            <Card className={styles.panelCard}>
              <div className={styles.panelHeader}>
                <div>
                  <h3>Pendências operacionais</h3>
                  <p>Itens que precisam de ação no financeiro.</p>
                </div>
              </div>
              {operationalAlerts.length ? (
                <div className={styles.alertList}>
                  {operationalAlerts.map((item) => (
                    <article key={item.key} className={styles.alertItem}>
                      <span className={`${styles.alertDot} ${item.tone === "urgent" ? styles.alertDotUrgent : ""}`} />
                      <div className={styles.listCopy}>
                        <strong>{item.label}</strong>
                        <span>{item.detail}</span>
                      </div>
                      <Button type="button" variant="ghost">
                        {item.action}
                      </Button>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="Sem pendências" message="Nenhuma ação crítica para o período selecionado." />
              )}
            </Card>

            <div className={styles.sideStack}>
              <Card className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h3>Conciliação</h3>
                    <p>{dashboard.pending_reconciliations} transações aguardando revisão.</p>
                  </div>
                  <span className={styles.countBadge}>{dashboard.pending_reconciliations}</span>
                </div>
                {pendingReconciliationItems.length ? (
                  <div className={styles.list}>
                    {pendingReconciliationItems.map((item) => (
                      <article key={item.id} className={styles.reconciliationItem}>
                        <div className={styles.bankMark}>{(item.bank_name ?? "Banco").slice(0, 3).toUpperCase()}</div>
                        <div className={styles.listCopy}>
                          <strong title={item.description}>{item.description}</strong>
                          <span>{item.account_name ?? "Conta não informada"} · {formatShortDate(item.posted_at)}</span>
                        </div>
                        <strong className={numeric(item.amount) >= 0 ? styles.positiveAmount : ""}>
                          {formatSignedMoney(item.amount)}
                        </strong>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="Sem conciliações pendentes" message="Todas as transações recentes estão conciliadas." />
                )}
              </Card>

              <Card className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h3>DRE — {formatCompactMonth(filters.end || filters.start)}</h3>
                  </div>
                  <span className={styles.dreVsLabel}>vs. {formatCompactMonth(filters.start ? toInput(new Date(parseIsoDate(filters.start).getFullYear(), parseIsoDate(filters.start).getMonth() - 1, 1)) : "")}</span>
                </div>
                <div className={styles.dreList}>
                  {(dashboard.dre_lines.length ? dashboard.dre_lines : dashboard.dre_chart.map((item) => ({
                    ...item,
                    percent: "0.00",
                    comparison_percent: null,
                  }))).slice(0, 5).map((item) => {
                    const amount = numeric(item.value);
                    const comparison = item.comparison_percent;
                    return (
                      <div key={item.label} className={styles.dreRow}>
                        <span>{item.label}</span>
                        <div className={styles.dreMetric}>
                          <strong className={amount >= 0 ? styles.positiveAmount : ""}>{formatMoney(item.value)}</strong>
                          <em className={numeric(comparison) < 0 ? styles.negativePercent : styles.positivePercent}>
                            {formatSignedPercent(comparison)}
                          </em>
                        </div>
                      </div>
                    );
                  })}
                  {!dashboard.dre_lines.length && !dashboard.dre_chart.length ? (
                    <EmptyState title="DRE indisponível" message="Configure as linhas do relatório para preencher este quadro." />
                  ) : null}
                </div>
              </Card>
            </div>
          </section>
        </>
      ) : null}
    </SectionChrome>
  );
}

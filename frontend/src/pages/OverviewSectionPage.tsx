import { useEffect, useRef, useState } from "react";

import { BarChart } from "../components/BarChart";
import { RefreshIcon } from "../components/RefreshIcon";
import { RevenueComparisonChart } from "../components/RevenueComparisonChart";
import { SectionChrome } from "../components/SectionChrome";
import { Button, Card, EmptyState, Input, KpiCard, PeriodChips, StatusPill } from "../components/ui";
import type { MainNavChild } from "../data/navigation";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";
import type { DashboardOverview, DashboardPendingItem } from "../types";
import styles from "./OverviewSectionPage.module.css";

const DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS = 5;

type Props = {
  tabs: MainNavChild[];
  dashboard: DashboardOverview | null;
  filters: { start: string; end: string };
  loading: boolean;
  onChangeFilters: (filters: { start: string; end: string }) => void;
  onApplyFilters: (filters?: { start: string; end: string }) => Promise<void>;
  onRefreshData: () => Promise<void>;
};

type PeriodKey = "month" | "previous" | "year" | "";

const PERIOD_OPTIONS = [
  { key: "month", label: "Mês atual" },
  { key: "previous", label: "Mês anterior" },
  { key: "year", label: "Ano atual" },
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

function numeric(value: string | number | null | undefined) {
  return Number(value ?? 0);
}

function buildQuickRange(kind: Exclude<PeriodKey, "">) {
  const now = new Date();
  if (kind === "month") {
    return {
      start: toInput(new Date(now.getFullYear(), now.getMonth(), 1)),
      end: toInput(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
    };
  }
  if (kind === "previous") {
    return {
      start: toInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      end: toInput(new Date(now.getFullYear(), now.getMonth(), 0)),
    };
  }
  return {
    start: toInput(new Date(now.getFullYear(), 0, 1)),
    end: toInput(new Date(now.getFullYear(), 11, 31)),
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

function buildPendingSpark(items: DashboardPendingItem[]) {
  return items
    .slice(0, 6)
    .map((item) => numeric(item.amount))
    .reverse();
}

function SummaryList({
  title,
  items,
  empty,
}: {
  title: string;
  items: DashboardPendingItem[];
  empty: string;
}) {
  return (
    <Card className={styles.panelCard}>
      <div className={styles.panelHeader}>
        <div>
          <h3>{title}</h3>
          <p>{items.length ? `${items.length} itens críticos no período.` : empty}</p>
        </div>
      </div>
      {items.length ? (
        <div className={styles.list}>
          {items.slice(0, 5).map((item) => (
            <article key={item.id} className={styles.listItem}>
              <div className={styles.listCopy}>
                <strong title={item.title}>{item.title}</strong>
                <span>{item.counterparty_name ?? item.account_name ?? "Sem contraparte"}</span>
              </div>
              <div className={styles.listMeta}>
                <em>{item.due_date ? formatShortDate(item.due_date) : "-"}</em>
                <strong>{formatMoney(item.amount)}</strong>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="Sem pendências" message={empty} />
      )}
    </Card>
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
  const [showPeriodPopover, setShowPeriodPopover] = useState(false);
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
  const revenueSpark = dashboard?.revenue_comparison.points.map((point) => numeric(point.current_year_value)) ?? [];
  const previousRevenueSpark =
    dashboard?.revenue_comparison.points.map((point) => numeric(point.previous_year_value)) ?? [];
  const dreSpark = dashboard?.dre_chart.map((point) => numeric(point.value)) ?? [];
  const overduePayables = dashboard?.overdue_payables ?? [];
  const overdueReceivables = dashboard?.overdue_receivables ?? [];
  const birthdayPurchaseLookbackYears =
    dashboard?.week_birthdays.purchase_lookback_years ?? DEFAULT_BIRTHDAY_PURCHASE_LOOKBACK_YEARS;
  const hasDashboard = Boolean(dashboard);

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
          <span className={styles.periodBadge}>{dashboard?.period_label ?? "Leitura consolidada"}</span>
          <h2 className={styles.headline}>Dashboard executivo com caixa, resultado e prioridades operacionais.</h2>
          <div className={styles.toolbarMeta}>
            <StatusPill status={loading ? "idle" : "online"} pulse={loading}>
              {loading ? "Atualizando" : "Dados sincronizados"}
            </StatusPill>
            {dashboard?.today_sales ? (
              <span className={styles.metaItem}>
                Vendas hoje: <strong>{formatMoney(dashboard.today_sales.gross_revenue)}</strong>
              </span>
            ) : null}
            {dashboard?.today_sales?.updated_at ? (
              <span className={styles.metaItem}>Atualizado {formatDateTime(dashboard.today_sales.updated_at)}</span>
            ) : null}
          </div>
        </div>

        <div className={styles.toolbarControls}>
          <PeriodChips
            options={PERIOD_OPTIONS.map((option) => ({ key: option.key, label: option.label }))}
            value={selectedPeriod}
            onChange={handleQuickRange}
            customLabel="Personalizado"
            onCustomClick={() => setShowPeriodPopover((current) => !current)}
          />
          <Button iconLeft={<RefreshIcon />} loading={loading} onClick={() => void onRefreshData()} size="md" variant="secondary">
            Atualizar
          </Button>
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
        <section className={styles.heroGrid}>
        <Card className={styles.heroCard}>
          <div className={styles.heroHeader}>
            <div>
              <span className={styles.heroEyebrow}>Caixa consolidado</span>
              <h3>Saldo de leitura gerencial</h3>
            </div>
            <StatusPill status={numeric(dashboard?.kpis.projected_balance) >= 0 ? "online" : "idle"}>
              {numeric(dashboard?.kpis.projected_balance) >= 0 ? "Projetado saudável" : "Pressão no caixa"}
            </StatusPill>
          </div>
            <div className={styles.heroValue}>{formatMoney(String(totalAccountBalance || (dashboard?.kpis.current_balance ?? 0)))}</div>
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span>Saldo projetado</span>
              <strong>{formatMoney(dashboard?.kpis.projected_balance ?? 0)}</strong>
            </div>
            <div className={styles.heroStat}>
              <span>Lucro remanescente</span>
              <strong>{formatMoney(dashboard?.kpis.remaining_profit ?? 0)}</strong>
            </div>
            <div className={styles.heroStat}>
              <span>Conciliações pendentes</span>
              <strong>{dashboard?.pending_reconciliations ?? 0}</strong>
            </div>
          </div>
        </Card>

        <div className={styles.kpiGrid}>
          <KpiCard hero label="Receita bruta" sparkline={revenueSpark} value={formatMoney(dashboard?.kpis.gross_revenue ?? 0)} />
          <KpiCard label="Receita líquida" sparkline={revenueSpark} value={formatMoney(dashboard?.kpis.net_revenue ?? 0)} />
          <KpiCard goodTrend={numeric(dashboard?.kpis.net_profit) >= 0} label="Lucro líquido" sparkline={dreSpark} trend={numeric(dashboard?.kpis.net_profit) >= 0 ? "up" : "down"} value={formatMoney(dashboard?.kpis.net_profit ?? 0)} />
          <KpiCard goodTrend={false} label="CMV" sparkline={dreSpark.map((value) => Math.abs(value))} trend="down" value={formatMoney(dashboard?.kpis.cmv ?? 0)} />
          <KpiCard goodTrend={false} label="Despesas operacionais" sparkline={buildPendingSpark(overduePayables)} trend="down" value={formatMoney(dashboard?.kpis.operating_expenses ?? 0)} />
          <KpiCard label="Vendas hoje" sparkline={revenueSpark.length ? revenueSpark : previousRevenueSpark} value={formatMoney(dashboard?.today_sales?.gross_revenue ?? 0)} />
          <KpiCard goodTrend={false} label="A receber vencido" trend={overdueReceivables.length ? "down" : "flat"} value={String(dashboard?.kpis.overdue_receivables ?? 0)} />
          <KpiCard goodTrend={false} label="A pagar vencido" trend={overduePayables.length ? "down" : "flat"} value={String(dashboard?.kpis.overdue_payables ?? 0)} />
        </div>
        </section>
      ) : null}

      {dashboard ? (
        <>
          <section className={styles.chartGrid}>
            <RevenueComparisonChart title="Receita comparada mês a mês" comparison={dashboard.revenue_comparison} />
            <BarChart data={dashboard.dre_chart} title="Leitura do DRE no período" />
          </section>

          <section className={styles.opsGrid}>
            <Card className={styles.panelCard}>
              <div className={styles.panelHeader}>
                <div>
                  <h3>Saldos por conta</h3>
                  <p>{accountBalances.length} contas acompanhadas na leitura gerencial.</p>
                </div>
              </div>
              {accountBalances.length ? (
                <div className={styles.balanceList}>
                  {accountBalances.slice(0, 6).map((account) => (
                    <article key={account.account_id} className={styles.balanceItem}>
                      <div className={styles.balanceCopy}>
                        <strong>{account.account_name}</strong>
                        <span>{account.account_type}</span>
                      </div>
                      <div className={styles.balanceMeta}>
                        {account.exclude_from_balance ? <em>Fora do consolidado</em> : null}
                        <strong>{formatMoney(account.current_balance)}</strong>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="Sem contas consolidadas" message="Cadastre contas ou sincronize saldos para exibir este quadro." />
              )}
            </Card>

            <SummaryList empty="Não há recebíveis vencidos nesta leitura." items={overdueReceivables} title="Recebíveis vencidos" />
            <SummaryList empty="Não há pagamentos vencidos nesta leitura." items={overduePayables} title="Pagáveis vencidos" />

            <Card className={styles.panelCard}>
              <div className={styles.panelHeader}>
                <div>
                  <h3>Aniversariantes da semana</h3>
                  <p>
                    {dashboard.week_birthdays.week_label ?? "Semana atual"} com compra nos últimos{" "}
                    {birthdayPurchaseLookbackYears} anos.
                  </p>
                </div>
              </div>
              {dashboard.week_birthdays.items.length ? (
                <div className={styles.list}>
                  {dashboard.week_birthdays.items.slice(0, 5).map((item) => (
                    <article key={`${item.linx_code}-${item.birthday_date}`} className={styles.listItem}>
                      <div className={styles.listCopy}>
                        <strong>{item.customer_name}</strong>
                        <span>Última compra em {formatShortDate(item.last_purchase_date)}</span>
                      </div>
                      <div className={styles.listMeta}>
                        <em>{formatBirthdayDate(item.birthday_date)}</em>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="Sem aniversariantes" message="Nenhum cliente elegível aparece nesta semana." />
              )}
            </Card>
          </section>
        </>
      ) : null}
    </SectionChrome>
  );
}

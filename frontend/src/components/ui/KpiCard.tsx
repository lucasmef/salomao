import type { ReactNode } from "react";
import { Sparkline } from "./Sparkline";
import styles from "./KpiCard.module.css";

type Trend = "up" | "down" | "flat";

type Props = {
  label: ReactNode;
  value: ReactNode;
  delta?: ReactNode;
  /** Tendência semântica — não obrigatoriamente "boa" ou "ruim", isso fica com `goodTrend`. */
  trend?: Trend;
  /** Se a tendência é boa (verde) ou ruim (vermelha). Default: up=good, down=bad. */
  goodTrend?: boolean;
  sparkline?: number[];
  /** Variante destaque com gradiente primary→accent. */
  hero?: boolean;
};

function ArrowIcon({ trend }: { trend: Trend }) {
  if (trend === "flat") {
    return (
      <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
        <line x1="2" y1="6" x2="10" y2="6" />
      </svg>
    );
  }
  const points = trend === "up" ? "3,8 6,3 9,8" : "3,4 6,9 9,4";
  return (
    <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points={points} />
    </svg>
  );
}

export function KpiCard({ label, value, delta, trend = "up", goodTrend, sparkline, hero = false }: Props) {
  const isGood = goodTrend ?? trend === "up";
  const deltaColor = trend === "flat" ? "" : isGood ? styles.deltaUp : styles.deltaDown;
  const sparkColor = hero
    ? "rgba(255,255,255,0.85)"
    : trend === "flat"
      ? "var(--color-text-muted)"
      : isGood
        ? "var(--color-success)"
        : "var(--color-danger)";

  return (
    <div className={[styles.card, hero ? styles.hero : ""].filter(Boolean).join(" ")}>
      <div className={styles.label}>{label}</div>
      <div className={styles.row}>
        <div className={styles.valueWrap}>
          <div className={styles.value}>{value}</div>
          {delta && (
            <span className={[styles.delta, deltaColor].join(" ")}>
              <ArrowIcon trend={trend} />
              {delta}
            </span>
          )}
        </div>
        {sparkline && sparkline.length > 0 && (
          <div className={styles.spark}>
            <Sparkline data={sparkline} color={sparkColor} width={56} height={26} />
          </div>
        )}
      </div>
      {hero && <div className={styles.heroBlur} aria-hidden="true" />}
    </div>
  );
}

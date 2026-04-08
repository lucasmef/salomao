import { formatMoney } from "../lib/format";
import type { DashboardSeriesPoint } from "../types";

type Props = {
  title?: string;
  data: DashboardSeriesPoint[];
  tone?: "default" | "success" | "warning";
  formatValue?: (value: string | number | null | undefined) => string;
};

export function BarChart({ title, data, tone = "default", formatValue = formatMoney }: Props) {
  const values = data.map((item) => Math.abs(Number(item.value)));
  const maxValue = Math.max(...values, 1);

  return (
    <section className="chart-card">
      {title && <h4>{title}</h4>}
      <div className="chart-list">
        {data.map((item) => {
          const rawValue = Number(item.value);
          const width = `${(Math.abs(rawValue) / maxValue) * 100}%`;
          return (
            <div key={item.label} className="chart-row">
              <div className="chart-labels">
                <span>{item.label}</span>
                <strong>{formatValue(item.value)}</strong>
              </div>
              <div className="chart-track">
                <div className={`chart-bar ${tone} ${rawValue < 0 ? "negative" : ""}`} style={{ width }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

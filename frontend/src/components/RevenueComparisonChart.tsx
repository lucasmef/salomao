import { formatMoney } from "../lib/format";
import type { DashboardRevenueComparison } from "../types";

type Props = {
  title: string;
  comparison: DashboardRevenueComparison;
};

type ChartPoint = {
  x: number;
  currentY: number;
  previousY: number;
  label: string;
  currentValue: number;
  previousValue: number;
};

function formatAxisValue(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    notation: "compact",
    compactDisplay: "short",
    maximumFractionDigits: 1,
  }).format(value);
}

function buildLinePath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

export function RevenueComparisonChart({ title, comparison }: Props) {
  const points = comparison.points ?? [];
  const width = 620;
  const height = 240;
  const padding = { top: 28, right: 26, bottom: 34, left: 56 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const values = points.flatMap((point) => [
    Number(point.current_year_value ?? 0),
    Number(point.previous_year_value ?? 0),
  ]);
  const maxValue = Math.max(...values, 1);
  const gridSteps = 4;
  const chartPoints: ChartPoint[] = points.map((point, index) => {
    const currentValue = Number(point.current_year_value ?? 0);
    const previousValue = Number(point.previous_year_value ?? 0);
    const x = padding.left + (index / Math.max(points.length - 1, 1)) * chartWidth;
    const scaleY = (value: number) => padding.top + chartHeight - (value / maxValue) * chartHeight;

    return {
      x,
      currentY: scaleY(currentValue),
      previousY: scaleY(previousValue),
      label: point.label,
      currentValue,
      previousValue,
    };
  });

  const currentPath = buildLinePath(chartPoints.map((point) => ({ x: point.x, y: point.currentY })));
  const previousPath = buildLinePath(chartPoints.map((point) => ({ x: point.x, y: point.previousY })));

  return (
    <article className="panel revenue-comparison-card">
      <div className="panel-title revenue-comparison-title">
        <div>
          <h3>{title}</h3>
          <p className="panel-subtitle">Vendas mes a mes no ano atual contra o ano anterior.</p>
        </div>
        <div className="revenue-comparison-legend" aria-label="Legenda do grafico">
          <span className="current-year">
            <i />
            {comparison.current_year}
          </span>
          <span className="previous-year">
            <i />
            {comparison.previous_year}
          </span>
        </div>
      </div>

      <div className="revenue-comparison-canvas">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} preserveAspectRatio="none">
          {Array.from({ length: gridSteps + 1 }, (_, index) => {
            const value = (maxValue / gridSteps) * (gridSteps - index);
            const y = padding.top + (chartHeight / gridSteps) * index;
            return (
              <g key={`grid-${index}`}>
                <line
                  className="revenue-grid-line"
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={y}
                  y2={y}
                />
                <text className="revenue-axis-label" x={padding.left - 10} y={y + 4} textAnchor="end">
                  {formatAxisValue(value)}
                </text>
              </g>
            );
          })}

          {chartPoints.map((point) => (
            <text
              className="revenue-month-label"
              key={`label-${point.label}`}
              x={point.x}
              y={height - 12}
              textAnchor="middle"
            >
              {point.label}
            </text>
          ))}

          <path className="revenue-line current-year" d={currentPath} />
          <path className="revenue-line previous-year" d={previousPath} />

          {chartPoints.map((point) => (
            <g key={`point-${point.label}`}>
              <circle className="revenue-point current-year" cx={point.x} cy={point.currentY} r={4.5}>
                <title>{`${point.label} ${comparison.current_year}: ${formatMoney(String(point.currentValue))}`}</title>
              </circle>
              <circle className="revenue-point previous-year" cx={point.x} cy={point.previousY} r={4.5}>
                <title>{`${point.label} ${comparison.previous_year}: ${formatMoney(String(point.previousValue))}`}</title>
              </circle>
            </g>
          ))}
        </svg>
      </div>
    </article>
  );
}

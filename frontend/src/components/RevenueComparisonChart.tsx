import { useState } from "react";

import { formatMoney } from "../lib/format";
import type { DashboardRevenueComparison } from "../types";

type Props = {
  title: string;
  comparison: DashboardRevenueComparison;
  formatValue?: (value: string | number | null | undefined) => string;
};

type ChartPoint = {
  x: number;
  currentY: number;
  previousY: number;
  label: string;
  currentValue: number;
  previousValue: number;
};

function buildLinePath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

export function RevenueComparisonChart({ title, comparison, formatValue = formatMoney }: Props) {
  const [activePointIndex, setActivePointIndex] = useState<number | null>(null);
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
  const activePoint = activePointIndex === null ? null : chartPoints[activePointIndex];

  const getHoverZone = (index: number) => {
    const point = chartPoints[index];
    const previousPoint = chartPoints[index - 1];
    const nextPoint = chartPoints[index + 1];
    const left = previousPoint ? (previousPoint.x + point.x) / 2 : padding.left;
    const right = nextPoint ? (point.x + nextPoint.x) / 2 : width - padding.right;

    return {
      x: left,
      width: Math.max(right - left, 24),
    };
  };

  const tooltipClassName =
    activePointIndex === null
      ? "revenue-comparison-tooltip"
      : `revenue-comparison-tooltip${activePointIndex <= 1 ? " is-left" : ""}${activePointIndex >= chartPoints.length - 2 ? " is-right" : ""}`;

  return (
    <article className="panel revenue-comparison-card">
      <div className="panel-title revenue-comparison-title">
        <h3>{title}</h3>
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
        {activePoint ? (
          <div
            className={tooltipClassName}
            style={{ left: `${(activePoint.x / width) * 100}%` }}
          >
            <strong>{activePoint.label}</strong>
            <span className="current-year">
              <i />
              {comparison.current_year}: {formatValue(String(activePoint.currentValue))}
            </span>
            <span className="previous-year">
              <i />
              {comparison.previous_year}: {formatValue(String(activePoint.previousValue))}
            </span>
          </div>
        ) : null}

        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} preserveAspectRatio="none">
          {Array.from({ length: gridSteps + 1 }, (_, index) => {
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

          {activePoint ? (
            <line
              className="revenue-hover-line"
              x1={activePoint.x}
              x2={activePoint.x}
              y1={padding.top}
              y2={padding.top + chartHeight}
            />
          ) : null}

          {chartPoints.map((point) => (
            <g key={`point-${point.label}`}>
              <circle
                className={`revenue-point current-year${activePoint?.label === point.label ? " is-active" : ""}`}
                cx={point.x}
                cy={point.currentY}
                r={activePoint?.label === point.label ? 5.5 : 4.5}
              />
              <circle
                className={`revenue-point previous-year${activePoint?.label === point.label ? " is-active" : ""}`}
                cx={point.x}
                cy={point.previousY}
                r={activePoint?.label === point.label ? 5.5 : 4.5}
              />
            </g>
          ))}

          {chartPoints.map((point, index) => {
            const hoverZone = getHoverZone(index);
            return (
              <rect
                key={`hover-${point.label}`}
                aria-label={`Ver vendas de ${point.label}`}
                className="revenue-hover-target"
                fill="transparent"
                height={chartHeight + padding.bottom}
                onBlur={() => setActivePointIndex((current) => (current === index ? null : current))}
                onFocus={() => setActivePointIndex(index)}
                onMouseEnter={() => setActivePointIndex(index)}
                onMouseLeave={() => setActivePointIndex((current) => (current === index ? null : current))}
                rx={8}
                tabIndex={0}
                width={hoverZone.width}
                x={hoverZone.x}
                y={padding.top}
              />
            );
          })}
        </svg>
      </div>
    </article>
  );
}

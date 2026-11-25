import { useEffect, useRef, useState } from 'react';
import { niceTicks } from '../lib/ticks';

export interface Column {
  key: string;
  label: string;
  /** Shorter label for the axis when columns are narrow (e.g. "M" for March) */
  narrow?: string;
  value: number;
  /** Text shown on hover or tap */
  detail: string;
}

interface Props {
  columns: Column[];
  /** Describes the chart for screen readers; the table below it carries the numbers */
  label: string;
  tick: (value: number) => string;
}

const HEIGHT = 200;
const PAD = { top: 12, right: 8, bottom: 24, left: 56 };
const MAX_BAR = 24;
const RADIUS = 4;

/** A single series of columns: one colour, rounded tops, square at the baseline, tooltip on hover. */
export function ColumnChart({ columns, label, tick }: Props) {
  const [active, setActive] = useState<number | null>(null);
  // Drawn at the real width, so text keeps its size on phones and wide screens
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(360);
  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const ticks = niceTicks(Math.max(0, ...columns.map((c) => c.value)));
  const top = ticks[ticks.length - 1] || 1;
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const band = plotW / Math.max(columns.length, 1);
  const barW = Math.min(MAX_BAR, band * 0.6);
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const shown = active !== null ? columns[active] : null;

  return (
    <div className="chart" ref={box} onPointerLeave={() => setActive(null)}>
      <svg viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-label={label} width={width} height={HEIGHT}>
        {ticks.map((v) => (
          <g key={v}>
            <line className="chart-grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
            <text className="chart-axis" x={PAD.left - 6} y={y(v)} dy="0.32em" textAnchor="end">{tick(v)}</text>
          </g>
        ))}
        {columns.map((c, i) => {
          const x = PAD.left + band * i + (band - barW) / 2;
          const h = Math.max(0, y(0) - y(c.value));
          const r = Math.min(RADIUS, h, barW / 2);
          // Rounded at the data end only, square at the baseline
          const path = h > 0
            ? `M${x},${y(0)} V${y(c.value) + r} Q${x},${y(c.value)} ${x + r},${y(c.value)} H${x + barW - r} Q${x + barW},${y(c.value)} ${x + barW},${y(c.value) + r} V${y(0)} Z`
            : '';
          return (
            <g key={c.key}>
              {path && <path className={`chart-bar${active === i ? ' active' : ''}`} d={path} />}
              <text className="chart-axis" x={x + barW / 2} y={HEIGHT - 6} textAnchor="middle">{band < 36 && c.narrow ? c.narrow : c.label}</text>
              {/* Hit target: the whole band, larger than the bar */}
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} fill="transparent"
                onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)} />
            </g>
          );
        })}
      </svg>
      {shown && (
        <div className="chart-tooltip" role="status"
          style={{ left: `${((PAD.left + band * (active! + 0.5)) / width) * 100}%` }}>
          <strong>{shown.label}</strong> {shown.detail}
        </div>
      )}
    </div>
  );
}

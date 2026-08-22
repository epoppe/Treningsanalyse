/** Shared chart design tokens — cockpit, analyse, and legacy metric pages. */

export const CHART_COLORS = ["#0f766e", "#1d4ed8", "#c2410c", "#7c3aed", "#ca8a04", "#db2777"] as const;

/** @deprecated Use CHART_COLORS — kept for analyse imports during migration */
export const ANALYSIS_CHART_COLORS = CHART_COLORS;

export const CHART_GRID = {
  strokeDasharray: "3 3",
  stroke: "#e2e8f0",
} as const;

/** @deprecated Use CHART_GRID */
export const ANALYSIS_CHART_GRID = CHART_GRID;

export const CHART_AXIS = {
  tick: { fontSize: 10, fill: "#64748b" },
  stroke: "#cbd5e1",
} as const;

/** @deprecated Use CHART_AXIS */
export const ANALYSIS_CHART_AXIS = CHART_AXIS;

export const CHART_TOOLTIP = {
  contentStyle: {
    fontSize: 12,
    borderRadius: 8,
    borderColor: "#e2e8f0",
    boxShadow: "0 4px 12px rgba(15, 23, 42, 0.08)",
  },
  labelStyle: { color: "#0f172a", fontWeight: 600 },
  itemStyle: { color: "#475569" },
} as const;

/** @deprecated Use CHART_TOOLTIP */
export const ANALYSIS_CHART_TOOLTIP = CHART_TOOLTIP;

export const CHART_LEGEND = {
  wrapperStyle: { fontSize: 11, color: "#475569" },
} as const;

export const CHART_PRIMARY = CHART_COLORS[0];

/** @deprecated Use CHART_PRIMARY */
export const ANALYSIS_CHART_PRIMARY = CHART_PRIMARY;

export const CHART_MARGIN = {
  compact: { top: 8, right: 8, left: 0, bottom: 0 },
  default: { top: 8, right: 16, left: 8, bottom: 0 },
  labeled: { top: 12, right: 24, left: 12, bottom: 8 },
  legacy: { top: 5, right: 30, left: 20, bottom: 5 },
} as const;

export const CHART_LINE = {
  strokeWidth: 1.75,
  dot: false as const,
  activeDot: { r: 4 },
} as const;

export const CHART_BAR = {
  radius: [4, 4, 0, 0] as [number, number, number, number],
} as const;

/** Semantic series colors used by legacy health/training charts */
export const LEGACY_SERIES_COLORS = {
  ctl: "#1d4ed8",
  atl: "#c2410c",
  tss: "#7c3aed",
  form: "#059669",
  vo2: "#dc2626",
  trend: "#64748b",
  bodyBatteryHigh: "#059669",
  bodyBatteryLow: "#dc2626",
  bodyBatteryCharged: "#1d4ed8",
  bodyBatteryDrained: "#ca8a04",
  cadence: CHART_COLORS[0],
  hrvLine: CHART_COLORS[0],
} as const;

export function chartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length];
}

export function yearComparisonColors(count: number): string[] {
  return Array.from({ length: count }, (_, index) => chartColor(index));
}

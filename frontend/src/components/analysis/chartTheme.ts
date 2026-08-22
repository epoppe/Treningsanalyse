/** Shared Recharts styling for cockpit + analyse surfaces. */

export const ANALYSIS_CHART_COLORS = ["#0f766e", "#1d4ed8", "#c2410c", "#7c3aed"] as const;

export const ANALYSIS_CHART_GRID = {
  strokeDasharray: "3 3",
  stroke: "#e2e8f0",
} as const;

export const ANALYSIS_CHART_AXIS = {
  tick: { fontSize: 10, fill: "#64748b" },
} as const;

export const ANALYSIS_CHART_TOOLTIP = {
  contentStyle: { fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" },
} as const;

export const ANALYSIS_CHART_PRIMARY = ANALYSIS_CHART_COLORS[0];

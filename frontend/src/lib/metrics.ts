/** Training metric display metadata — verified against frontend data models. */

import { formatChartNumber, formatWithUnit } from "./chartFormatters";

export interface MetricDefinition {
  displayName: string;
  shortName?: string;
  unit: string;
  axisLabel: string;
  decimals?: number;
}

/** Known metrics used across charts and analysis views. */
export const METRIC_DEFINITIONS: Record<string, MetricDefinition> = {
  distance: {
    displayName: "Distanse",
    unit: "km",
    axisLabel: "Distanse (km)",
    decimals: 1,
  },
  duration: {
    displayName: "Varighet",
    unit: "min",
    axisLabel: "Tid (min)",
    decimals: 0,
  },
  calories: {
    displayName: "Kalorier",
    unit: "kcal",
    axisLabel: "Kalorier (kcal)",
    decimals: 0,
  },
  hrv: {
    displayName: "HRV",
    unit: "ms",
    axisLabel: "HRV (ms)",
    decimals: 0,
  },
  cadence: {
    displayName: "Kadens",
    unit: "skritt/min",
    axisLabel: "Kadens (skritt/min)",
    decimals: 0,
  },
  strideLength: {
    displayName: "Skrittlengde",
    unit: "m",
    axisLabel: "Skrittlengde (m)",
    decimals: 2,
  },
  vo2max: {
    displayName: "VO₂max",
    unit: "ml/kg/min",
    axisLabel: "VO₂max (ml/kg/min)",
    decimals: 1,
  },
  bodyBattery: {
    displayName: "Body Battery",
    unit: "poeng",
    axisLabel: "Body Battery (0–100)",
    decimals: 0,
  },
  sleepScore: {
    displayName: "Søvnscore",
    unit: "poeng",
    axisLabel: "Søvnscore (0–100)",
    decimals: 0,
  },
  heartRate: {
    displayName: "Puls",
    unit: "bpm",
    axisLabel: "Puls (bpm)",
    decimals: 0,
  },
  powerPerHr: {
    displayName: "Power/puls",
    unit: "W/bpm",
    axisLabel: "Power/puls (W/bpm)",
    decimals: 2,
  },
  runningEconomy: {
    displayName: "Løpsøkonomi",
    unit: "km/t per 100 bpm",
    axisLabel: "Løpsøkonomi (km/t per 100 bpm)",
    decimals: 2,
  },
  ctl: {
    displayName: "CTL",
    shortName: "Kronisk belastning (CTL)",
    unit: "poeng",
    axisLabel: "Belastning (poeng)",
    decimals: 1,
  },
  atl: {
    displayName: "ATL",
    shortName: "Akutt belastning (ATL)",
    unit: "poeng",
    axisLabel: "Belastning (poeng)",
    decimals: 1,
  },
  tss: {
    displayName: "TSS",
    shortName: "Dagsbelastning (TSS)",
    unit: "poeng",
    axisLabel: "Belastning (poeng)",
    decimals: 0,
  },
  form: {
    displayName: "Form",
    shortName: "Form (CTL − ATL)",
    unit: "poeng",
    axisLabel: "Form (poeng)",
    decimals: 1,
  },
  stressLevel: {
    displayName: "Stressnivå",
    unit: "poeng",
    axisLabel: "Stressnivå (0–100)",
    decimals: 0,
  },
  tssMonthly: {
    displayName: "TSS",
    unit: "TSS",
    axisLabel: "TSS",
    decimals: 0,
  },
};

/** Analysis workspace metric keys → human-readable labels. */
export const ANALYSIS_METRIC_LABELS: Record<string, string> = {
  "fitness.ctl": "CTL (kronisk belastning)",
  "fitness.atl": "ATL (akutt belastning)",
  "fitness.tsb": "Form (CTL − ATL)",
  "fitness.ef_30d": "Aerob effektivitet (30d)",
  "cardio.hrv_7d": "HRV (7d snitt)",
  "cardio.hrv": "HRV",
  "cardio.rhr_7d": "Hvilepuls (7d snitt)",
  "running.durability_score": "Durability",
  "running.critical_speed": "Critical speed",
  "sleep.score": "Søvnscore",
  "sleep.duration": "Søvntid",
};

/** Plotly trace keys → Norwegian display names. */
export const PLOTLY_TRACE_LABELS: Record<string, string> = {
  heart_rate: "Puls",
  speed: "Fart",
  altitude: "Høyde",
  steady_state_ef: "Steady-state EF",
  fatigue_resistance_score: "Utmattelsesmotstand",
};

export function getMetricDefinition(key: keyof typeof METRIC_DEFINITIONS): MetricDefinition {
  return METRIC_DEFINITIONS[key];
}

export function getAnalysisMetricLabel(
  key: string,
  meta?: { label?: string; unit?: string },
): string {
  if (meta?.label) return meta.label;
  if (ANALYSIS_METRIC_LABELS[key]) return ANALYSIS_METRIC_LABELS[key];
  return key
    .replace(/^coaching\./, "")
    .replace(/\./g, " · ")
    .replace(/_/g, " ");
}

export function formatMetricValue(
  def: MetricDefinition,
  value: number,
): string {
  return formatWithUnit(value, def.unit, def.decimals ?? 1);
}

export function formatMetricAxisTick(
  def: MetricDefinition,
  value: number,
): string {
  return formatChartNumber(value, def.decimals ?? 1);
}

/** Legend/series name for trend lines. */
export const SERIES_LABELS = {
  movingAverage: "Glidende snitt",
  rollingAvg7d: "7-dagers snitt",
  trend6m: "Trend (6 mnd snitt)",
  trend4p: "Trend (4 punkter)",
} as const;

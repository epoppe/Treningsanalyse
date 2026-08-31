/** Shared chart date/number formatting — presentation only. */

import { format, parseISO } from "date-fns";
import { nb } from "date-fns/locale";

/** Compact axis tick, e.g. "12. aug." */
export function formatChartAxisDate(
  value: string,
  style: "dayMonth" | "dayMonthYear" | "monthYear" = "dayMonth",
): string {
  try {
    const date = parseISO(String(value).slice(0, 10));
    if (style === "monthYear") return format(date, "MMM yy", { locale: nb });
    if (style === "dayMonthYear") return format(date, "d. MMM yyyy", { locale: nb });
    return format(date, "d. MMM", { locale: nb });
  } catch {
    return String(value);
  }
}

/** Tooltip date, e.g. "mandag 12. august 2025" */
export function formatChartTooltipDate(value: string): string {
  try {
    const date = parseISO(String(value).slice(0, 10));
    return format(date, "EEEE d. MMMM yyyy", { locale: nb });
  } catch {
    return String(value);
  }
}

/** Norwegian number formatting with sensible decimal precision. */
export function formatChartNumber(value: number, decimals = 1): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("nb-NO", {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatWithUnit(value: number, unit: string, decimals = 1): string {
  const formatted = formatChartNumber(value, decimals);
  if (!unit) return formatted;
  return `${formatted} ${unit}`;
}

/** Recharts Y-axis label props helper — needs ~52px left margin to stay visible. */
export function axisLabelProps(label: string) {
  return {
    value: label,
    angle: -90 as const,
    position: "insideLeft" as const,
    offset: 10,
    style: { textAnchor: "middle" as const, fill: "#64748b", fontSize: 11 },
  };
}

/** Format seconds as h:mm or minutes. */
export function formatDurationMinutes(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds)) return "—";
  const minutes = Math.round(totalSeconds / 60);
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h} t ${m} min` : `${h} t`;
  }
  return `${minutes} min`;
}

/** Format minutes (already in min) for stress charts etc. */
export function formatMinutesValue(minutes: number): string {
  if (!Number.isFinite(minutes)) return "—";
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return m > 0 ? `${h} t ${m} min` : `${h} t`;
  }
  return `${Math.round(minutes)} min`;
}

/** Responsive tick interval based on data length. */
export function responsiveTickInterval(dataLength: number, targetTicks = 8): number {
  return Math.max(1, Math.floor(dataLength / targetTicks));
}

import type { AnalysisPeriod } from "@/types/analysis";

/** Map an explicit brush range to the nearest period chip for API compatibility. */
export function rangeToPeriod(fromIso: string, toIso: string): AnalysisPeriod {
  const from = Date.parse(fromIso);
  const to = Date.parse(toIso);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return "90d";
  const days = Math.max(1, Math.round(Math.abs(to - from) / 86_400_000) + 1);
  if (days <= 35) return "28d";
  if (days <= 105) return "90d";
  if (days <= 200) return "6m";
  if (days <= 400) return "1y";
  if (days <= 800) return "2y";
  return "all";
}

export function isValidIsoDate(value: string | null | undefined): value is string {
  if (!value) return false;
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value));
}

export function normalizeRange(
  from?: string | null,
  to?: string | null,
): { from: string; to: string } | null {
  if (!isValidIsoDate(from) || !isValidIsoDate(to)) return null;
  if (from <= to) return { from, to };
  return { from: to, to: from };
}

export function formatRangeLabel(from: string, to: string): string {
  return `${from} – ${to}`;
}
